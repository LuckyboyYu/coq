
(* $Id$ *)

open Pp
open Util

(* The lexer of Coq *)

(* Note: removing a token.
   We do nothing because remove_token is called only when removing a grammar
   rule with Grammar.delete_rule. The latter command is called only when
   unfreezing the state of the grammar entries (see GRAMMAR summary, file
   env/metasyntax.ml). Therefore, instead of removing tokens one by one,
   we unfreeze the state of the lexer. This restores the behaviour of the
   lexer. B.B. *)

let lexer = {
  Token.func = Lexer.func;
  Token.using = Lexer.add_token;
  Token.removing = (fun _ -> ());
  Token.tparse = Lexer.tparse;
  Token.text = Lexer.token_text }

module L =
  struct
    let lexer = lexer
  end


(* The parser of Coq *)
module G = Grammar.Make(L)

let grammar_delete e rls =
  List.iter
    (fun (_,_,lev) ->
       List.iter (fun (pil,_) -> G.delete_rule e pil) (List.rev lev))
    (List.rev rls)

type typed_entry =
  | Ast of Coqast.t G.Entry.e
  | ListAst of Coqast.t list G.Entry.e


type ext_kind =
  | ByGrammar of
      typed_entry * Gramext.position option *
      (string option * Gramext.g_assoc option *
       (Gramext.g_symbol list * Gramext.g_action) list) list
  | ByGEXTEND of (unit -> unit) * (unit -> unit)


let camlp4_state = ref []

(* The apparent parser of Coq; encapsulate G to keep track of the
   extensions. *)
module Gram =
  struct
    type parsable = G.parsable
    let parsable = G.parsable
    let tokens = G.tokens
    module Entry = G.Entry
    module Unsafe = G.Unsafe

    let extend e pos rls =
      camlp4_state :=
      (ByGEXTEND ((fun () -> grammar_delete e rls),
                  (fun () -> G.extend e pos rls)))
      :: !camlp4_state;
      G.extend e pos rls
    let delete_rule e pil =
      errorlabstrm "Pcoq.delete_rule"
        [< 'sTR "GDELETE_RULE forbidden." >]
  end


(* This extension command is used by the Grammar command *)
let grammar_extend te pos rls =
  camlp4_state := ByGrammar (te,pos,rls) :: !camlp4_state;
  match te with
      Ast e ->  G.extend e pos rls
    | ListAst e -> G.extend e pos rls

(* n is the number of extended entries (not the number of Grammar commands!)
   to remove. *)
let rec remove_grammars n =
  if n>0 then
    (match !camlp4_state with
         [] -> anomaly "Pcoq.remove_grammars: too many rules to remove"
       | ByGrammar(Ast e,_,rls)::t ->
           grammar_delete e rls;
           camlp4_state := t;
           remove_grammars (n-1)
       | ByGrammar(ListAst e,_,rls)::t ->
           grammar_delete e rls;
           camlp4_state := t;
           remove_grammars (n-1)
       | ByGEXTEND (undo,redo)::t ->
           undo();
           camlp4_state := t;
           remove_grammars n;
           redo();
           camlp4_state := ByGEXTEND (undo,redo) :: !camlp4_state)



(* An entry that checks we reached the end of the input. *)
let eoi_entry en =
  let e = Gram.Entry.create ((Gram.Entry.name en) ^ "_eoi") in
  GEXTEND Gram
    e: [ [ x = en; EOI -> x ] ]
    ;
  END;
  e

let map_entry f en =
  let e = Gram.Entry.create ((Gram.Entry.name en) ^ "_map") in
  GEXTEND Gram
    e: [ [ x = en -> f x ] ]
    ;
  END;
  e


(* Parse a string, does NOT check if the entire string was read
   (use eoi_entry) *)
let parse_string f x =
  let strm = Stream.of_string x in Gram.Entry.parse f (Gram.parsable strm)



let slam_ast loc id ast =
  match id with
    Coqast.Nvar (_, s) -> Coqast.Slam (loc, Some s, ast)
  | _ -> invalid_arg "Ast.slam_ast"


type entry_type = ETast | ETastl

let entry_type ast =
  match ast with
    Coqast.Id (_, "LIST") -> ETastl
  | Coqast.Id (_, "AST") -> ETast
  | _ -> invalid_arg "Ast.entry_type"


let type_of_entry e =
  match e with
    Ast _ -> ETast
  | ListAst _ -> ETastl


type gram_universe = (string, typed_entry) Hashtbl.t


let trace = ref false

(*
trace.val := True;
*)

(* The univ_tab is not part of the state. It contains all the grammar that
   exist or have existed before in the session. *)
let univ_tab = Hashtbl.create 7
let get_univ s =
  try Hashtbl.find univ_tab s with
    Not_found ->
      if !trace then
        begin Printf.eprintf "[Creating univ %s]\n" s; flush stderr; () end;
      let u = s, Hashtbl.create 29 in Hashtbl.add univ_tab s u; u


let get_entry (u, utab) s =
  try Hashtbl.find utab s with
    Not_found -> errorlabstrm "Pcoq.get_entry"
        [< 'sTR"unknown grammar entry "; 'sTR u; 'sTR":"; 'sTR s >]


let new_entry etyp (u, utab) s =
  let ename = u ^ ":" ^ s in
  let e =
    match etyp with
      ETast -> Ast (Gram.Entry.create ename)
    | ETastl -> ListAst (Gram.Entry.create ename)
  in
  Hashtbl.add utab s e; e


let create_entry (u, utab) s etyp =
  try
    let e = Hashtbl.find utab s in
    if type_of_entry e <> etyp then
      failwith ("Entry " ^ u ^ ":" ^ s ^ " already exists with another type")
    else e
  with
    Not_found ->
      if !trace then
        begin
          Printf.eprintf "[Creating entry %s:%s]\n" u s; flush stderr; ()
        end;
      new_entry etyp (u, utab) s


let force_entry_type (u, utab) s etyp =
  try
    let entry = Hashtbl.find utab s in
    let extyp = type_of_entry entry in
    if etyp = extyp then entry
    else
      begin
        prerr_endline
          ("Grammar entry " ^ u ^ ":" ^ s ^
             " redefined with another type;\n older entry hidden.");
        Hashtbl.remove utab s;
        new_entry etyp (u, utab) s
      end
  with
    Not_found -> new_entry etyp (u, utab) s





(* Grammar entries *)

module Command =
  struct
    let ucommand = snd (get_univ "command")
    let gec s =
      let e = Gram.Entry.create ("Command." ^ s) in
      Hashtbl.add ucommand s (Ast e); e
    
    let gec_list s =
      let e = Gram.Entry.create ("Command." ^ s) in
      Hashtbl.add ucommand s (ListAst e); e

    let abstraction_tail = gec "abstraction_tail"
    let binder = gec "binder"
    let cofixbinder = gec "cofixbinder"
    let cofixbinders = gec_list "cofixbinders"
    let command = gec "command"
    let command0 = gec "command0"
    let command1 = gec "command1"
    let command10 = gec "command10"
    let command2 = gec "command2"
    let command3 = gec "command3"
    let command5 = gec "command5"
    let command6 = gec "command6"
    let command7 = gec "command7"
    let command8 = gec "command8"
    let command9 = gec "command9"
    let command91 = gec "command91"
    let command_eoi = eoi_entry command
    let equation = gec "equation"
    let fixbinder = gec "fixbinder"
    let fixbinders = gec_list "fixbinders"
    let ident = gec "ident"
    let lassoc_command4 = gec "lassoc_command4"
    let lcommand = gec "lcommand"
    let lsimple_pattern = Gram.Entry.create "Command.lsimple_pattern"
    let ne_binder_list = gec_list "ne_binder_list"
    let ne_command91_list = gec_list "ne_command91_list"
    let ne_command9_list = gec_list "ne_command9_list"
    let ne_command_list = gec_list "ne_command_list"
    let ne_eqn_list = gec_list "ne_eqn_list"
    let ne_ident_comma_list = gec_list "ne_ident_comma_list"
    let ne_pattern_list = Gram.Entry.create "Command.ne_pattern_list"
    let pattern = Gram.Entry.create "Command.pattern"
    let pattern_list = Gram.Entry.create "Command.pattern_list"
    let product_tail = gec "product_tail"
    let raw_command = gec "raw_command"
    let simple_pattern = Gram.Entry.create "Command.simple_pattern"
    let simple_pattern2 = Gram.Entry.create "Command.simple_pattern2"
    let simple_pattern_list =
	 Gram.Entry.create "Command.simple_pattern_list"
    let ucommand = snd (get_univ "command")
  end


module Tactic =
  struct
    let utactic = snd (get_univ "tactic")
    let gec s =
      let e = Gram.Entry.create ("Tactic." ^ s) in
      Hashtbl.add utactic s (Ast e); e
    
    let gec_list s =
      let e = Gram.Entry.create ("Tactic." ^ s) in
      Hashtbl.add utactic s (ListAst e); e
    
    let binding_list = gec "binding_list"
    let com_binding_list = gec_list "com_binding_list"
    let comarg = gec "comarg"
    let comarg_binding_list = gec_list "comarg_binding_list"
    let numarg_binding_list = gec_list "numarg_binding_list"
    let lcomarg_binding_list = gec_list "lcomarg_binding_list"
    let comarg_list = gec_list "comarg_list"
    let identarg = gec "identarg"
    let lcomarg = gec "lcomarg"
    let clausearg = gec "clausearg"
    let ne_identarg_list = gec_list "ne_identarg_list"
    let ne_num_list = gec_list "ne_num_list"
    let ne_pattern_list = gec_list "ne_pattern_list"
    let ne_pattern_hyp_list = gec_list "ne_pattern_hyp_list"
    let one_intropattern = gec "one_intropattern"
    let intropattern = gec "intropattern"
    let ne_intropattern = gec "ne_intropattern"
    let simple_intropattern = gec "simple_intropattern"
    let ne_unfold_occ_list = gec_list "ne_unfold_occ_list"
    let red_tactic = gec "red_tactic"
    let red_flag = gec "red_flag"
    let autoarg_depth = gec "autoarg_depth"
    let autoarg_excluding = gec "autoarg_excluding"
    let autoarg_adding = gec "autoarg_adding"
    let autoarg_destructing = gec "autoarg_destructing"
    let autoarg_usingTDB = gec "autoarg_usingTDB"
    let numarg = gec "numarg"
    let pattern_occ = gec "pattern_occ"
    let pattern_occ_hyp = gec "pattern_occ_hyp"
    let simple_binding = gec "simple_binding"
    let simple_binding_list = gec_list "simple_binding_list"
    let simple_tactic = gec "simple_tactic"
    let tactic = gec "tactic"
    let tactic_com = gec "tactic_com"
    let tactic_com_list = gec "tactic_com_list"
    let tactic_com_tail = gec "tactic_com_tail"
    let unfold_occ = gec "unfold_occ"
    let with_binding_list = gec "with_binding_list"
    let fixdecl = gec_list "fixdecl"
    let cofixdecl = gec_list "cofixdecl"
    let tacarg_list = gec_list "tacarg_list"
    let tactic_eoi = eoi_entry tactic
  end


module Vernac =
  struct
    let uvernac = snd (get_univ "vernac")
    let gec s =
      let e = Gram.Entry.create ("Vernac." ^ s) in
      Hashtbl.add uvernac s (Ast e); e
    
    let gec_list s =
      let e = Gram.Entry.create ("Vernac." ^ s) in
      Hashtbl.add uvernac s (ListAst e); e
    
    let binder = gec "binder"
    let block = gec_list "block"
    let block_old_style = gec_list "block_old_style"
    let comarg = gec "comarg"
    let def_tok = gec "def_tok"
    let definition_tail  = gec "definition_tail"
    let dep = gec "dep"
    let destruct_location = gec "destruct_location"
    let check_tok = gec "check_tok"
    let extracoindblock = gec_list "extracoindblock"
    let extraindblock = gec_list "extraindblock"
    let field = gec "field"
    let nefields = gec_list "nefields"
    let fields = gec "fields"
    let destruct_location = gec "destruct_location"
    let finite_tok = gec "finite_tok"
    let grammar_entry_arg = gec "grammar_entry_arg"
    let hyp_tok = gec "hyp_tok"
    let hyps_tok = gec "hyps_tok"
    let idcom = gec "idcom"
    let identarg = gec "identarg"
    let import_tok = gec "import_tok"
    let indpar = gec "indpar"
    let lcomarg = gec "lcomarg"
    let lidcom = gec "lidcom"
    let orient=gec "orient"
    let lvernac = gec_list "lvernac"
    let meta_binding = gec "meta_binding"
    let meta_binding_list = gec_list "meta_binding_list"
    let ne_binder_semi_list = gec_list "ne_binder_semi_list"
    let ne_comarg_list = gec_list "ne_comarg_list"
    let ne_identarg_comma_list = gec_list "ne_identarg_comma_list"
    let identarg_list = gec_list "identarg_list"
    let ne_identarg_list = gec_list "ne_identarg_list"
    let ne_lidcom = gec_list "ne_lidcom"
    let ne_numarg_list = gec_list "ne_numarg_list"
    let ne_stringarg_list = gec_list "ne_stringarg_list"
    let numarg = gec "numarg"
    let numarg_list = gec_list "numarg_list"
    let onecorec = gec "onecorec"
    let oneind = gec "oneind"
    let oneind_old_style = gec "oneind_old_style"
    let onerec = gec "onerec"
    let onescheme = gec "onescheme"
    let opt_identarg_list = gec_list "opt_identarg_list"
    let rec_constr = gec "rec_constr"
    let record_tok = gec "record_tok"
    let option_value = gec "option_value"
    let param_tok = gec "param_tok"
    let params_tok = gec "params_tok"
    let sortdef = gec "sortdef"
    let specif_tok = gec "specif_tok"
    let specifcorec = gec_list "specifcorec"
    let specifrec = gec_list "specifrec"
    let specifscheme = gec_list "specifscheme"
    let stringarg = gec "stringarg"
    let tacarg = gec "tacarg"
    let theorem_body = gec "theorem_body"
    let theorem_body_line = gec "theorem_body_line"
    let theorem_body_line_list = gec_list "theorem_body_line_list"
    let thm_tok = gec "thm_tok"
    let varg_ne_stringarg_list = gec "varg_ne_stringarg_list"
    let vernac = gec "vernac"
    let vernac_eoi = eoi_entry vernac
  end


module Prim =
  struct
    let uprim = snd (get_univ "prim")
    let gec s =
      let e = Gram.Entry.create ("Prim." ^ s) in
      	Hashtbl.add uprim s (Ast e); e
    let ast = gec "ast"
    let ast_eoi = eoi_entry ast
    let astact = gec "astact"
    let astpat = gec "astpat"
    let entry_type = gec "entry_type"
    let grammar_entry = gec "grammar_entry"
    let grammar_entry_eoi = eoi_entry grammar_entry
    let ident = gec "ident"
    let number = gec "number"
    let path = gec "path"
    let string = gec "string"
    let syntax_entry = gec "syntax_entry"
    let syntax_entry_eoi = eoi_entry syntax_entry
    let uprim = snd (get_univ "prim")
    let var = gec "var"
  end


let main_entry = Gram.Entry.create "vernac"

GEXTEND Gram
  main_entry:
    [ [ a = Vernac.vernac -> Some a | EOI -> None ] ]
  ;
END

(* Quotations *)

open Prim
let define_quotation default s e =
  (if default then
    GEXTEND Gram
      ast: [ [ "<<"; c = e; ">>" -> c ] ];
   END);
  (GEXTEND Gram
     ast:
       [ [ "<"; ":"; LIDENT $s$; ":"; "<"; c = e; ">>" -> c ] ];
   END)
