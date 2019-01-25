#!/usr/bin/env python
from __future__ import with_statement
import os, re, sys, subprocess

# When passed `--release`, this script sets up Coq to support three
# `-compat` flag arguments.  If executed manually, this would consist
# of doing the following steps:
#
# - Delete the file `theories/Compat/CoqUU.v`, where U.U is four
#   versions prior to the new version X.X.  After this, there
#   should be exactly three `theories/Compat/CoqNN.v` files.
# - Update
#   [`doc/stdlib/index-list.html.template`](/doc/stdlib/index-list.html.template)
#   with the deleted file.
# - Remove any notations in the standard library which have `compat "U.U"`.
# - Update the type `compat_version` in [`lib/flags.ml`](/lib/flags.ml) by
#   bumping all the version numbers by one, and update the interpretations
#   of those flags in [`toplevel/coqargs.ml`](/toplevel/coqargs.ml) and
#   [`vernac/g_vernac.mlg`](/vernac/g_vernac.mlg).
#
# - Remove the file
#   [`test-suite/success/CompatOldOldFlag.v`](/test-suite/success/CompatOldOldFlag.v).
# - Update
#   [`test-suite/tools/update-compat/run.sh`](/test-suite/tools/update-compat/run.sh)
#   to ensure that it passes `--release` to the `update-compat.py`
#   script.

# When passed the `--master` flag, this script sets up Coq to support
# four `-compat` flag arguments.  If executed manually, this would
# consist of doing the following steps:
#
# - Add a file `theories/Compat/CoqXX.v` which contains just the header
#   from [`dev/header.ml`](/dev/header.ml)
# - Add the line `Require Export Coq.Compat.CoqXX.` at the top of
#   `theories/Compat/CoqYY.v`, where Y.Y is the version prior to X.X.
# - Update
#   [`doc/stdlib/index-list.html.template`](/doc/stdlib/index-list.html.template)
#   with the added file.
# - Update the type `compat_version` in [`lib/flags.ml`](/lib/flags.ml) by
#   bumping all the version numbers by one, and update the interpretations
#   of those flags in [`toplevel/coqargs.ml`](/toplevel/coqargs.ml) and
#   [`vernac/g_vernac.mlg`](/vernac/g_vernac.mlg).
# - Update the files
#   [`test-suite/success/CompatCurrentFlag.v`](/test-suite/success/CompatCurrentFlag.v),
#   [`test-suite/success/CompatPreviousFlag.v`](/test-suite/success/CompatPreviousFlag.v),
#   and
#   [`test-suite/success/CompatOldFlag.v`](/test-suite/success/CompatOldFlag.v)
#   by bumping all version numbers by 1.  Re-create the file
#   [`test-suite/success/CompatOldOldFlag.v`](/test-suite/success/CompatOldOldFlag.v)
#   with its version numbers also bumped by 1 (file should have
#   been removed before branching; see above).
# - Update
#   [`test-suite/tools/update-compat/run.sh`](/test-suite/tools/update-compat/run.sh)
#   to ensure that it passes `--master` to the `update-compat.py`
#   script.



# Obtain the absolute path of the script being run.  By assuming that
# the script lives in dev/tools/, and basing all calls on the path of
# the script, rather than the current working directory, we can be
# robust to users who choose to run the script from any location.
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
ROOT_PATH = os.path.realpath(os.path.join(SCRIPT_PATH, '..', '..'))
CONFIGURE_PATH = os.path.join(ROOT_PATH, 'configure.ml')
HEADER_PATH = os.path.join(ROOT_PATH, 'dev', 'header.ml')
DEFAULT_NUMBER_OF_OLD_VERSIONS = 2
RELEASE_NUMBER_OF_OLD_VERSIONS = 2
MASTER_NUMBER_OF_OLD_VERSIONS = 3
EXTRA_HEADER = '\n(** Compatibility file for making Coq act similar to Coq v%s *)\n'
FLAGS_MLI_PATH = os.path.join(ROOT_PATH, 'lib', 'flags.mli')
FLAGS_ML_PATH = os.path.join(ROOT_PATH, 'lib', 'flags.ml')
COQARGS_ML_PATH = os.path.join(ROOT_PATH, 'toplevel', 'coqargs.ml')
G_VERNAC_PATH = os.path.join(ROOT_PATH, 'vernac', 'g_vernac.mlg')
DOC_INDEX_PATH = os.path.join(ROOT_PATH, 'doc', 'stdlib', 'index-list.html.template')
BUG_4798_PATH = os.path.join(ROOT_PATH, 'test-suite', 'bugs', 'closed', 'bug_4798.v')
TEST_SUITE_RUN_PATH = os.path.join(ROOT_PATH, 'test-suite', 'tools', 'update-compat', 'run.sh')
TEST_SUITE_PATHS = tuple(os.path.join(ROOT_PATH, 'test-suite', 'success', i)
                         for i in ('CompatOldOldFlag.v', 'CompatOldFlag.v', 'CompatPreviousFlag.v', 'CompatCurrentFlag.v'))
TEST_SUITE_DESCRIPTIONS = ('current-minus-three', 'current-minus-two', 'current-minus-one', 'current')
# sanity check that we are where we think we are
assert(os.path.normpath(os.path.realpath(SCRIPT_PATH)) == os.path.normpath(os.path.realpath(os.path.join(ROOT_PATH, 'dev', 'tools'))))
assert(os.path.exists(CONFIGURE_PATH))

def get_header():
    with open(HEADER_PATH, 'r') as f: return f.read()

HEADER = get_header()

def break_or_continue():
    msg = 'Press ENTER to continue, or Ctrl+C to break...'
    try:
        raw_input(msg)
    except NameError: # we must be running python3
        input(msg)

def maybe_git_add(local_path, suggest_add=True, **args):
    if args['git_add']:
        print("Running 'git add %s'..." % local_path)
        retc = subprocess.call(['git', 'add', local_path], cwd=ROOT_PATH)
        if retc is not None and retc != 0:
            print('!!! Process returned code %d' % retc)
    elif suggest_add:
        print(r"!!! Don't forget to 'git add %s'!" % local_path)

def maybe_git_rm(local_path, **args):
    if args['git_add']:
        print("Running 'git rm %s'..." % local_path)
        retc = subprocess.call(['git', 'rm', local_path], cwd=ROOT_PATH)
        if retc is not None and retc != 0:
            print('!!! Process returned code %d' % retc)

def get_version(cur_version=None):
    if cur_version is not None: return cur_version
    with open(CONFIGURE_PATH, 'r') as f:
        for line in f.readlines():
            found = re.findall(r'let coq_version = "([0-9]+\.[0-9]+)', line)
            if len(found) > 0:
                return found[0]
    raise Exception("No line 'let coq_version = \"X.X' found in %s" % os.path.relpath(CONFIGURE_PATH, ROOT_PATH))

def compat_name_to_version_name(compat_file_name):
    assert(compat_file_name.startswith('Coq') and compat_file_name.endswith('.v'))
    v = compat_file_name[len('Coq'):][:-len('.v')]
    assert(len(v) == 2 or (len(v) >= 2 and v[0] in ('8', '9'))) # we'll have to change this scheme when we hit Coq 10.*
    return '%s.%s' % (v[0], v[1:])

def version_name_to_compat_name(v, ext='.v'):
    return 'Coq%s%s%s' % tuple(v.split('.') + [ext])

# returns (lines of compat files, lines of not compat files
def get_doc_index_lines():
    with open(DOC_INDEX_PATH, 'r') as f:
        lines = f.readlines()
    return (tuple(line for line in lines if 'theories/Compat/Coq' in line),
            tuple(line for line in lines if 'theories/Compat/Coq' not in line))

COMPAT_INDEX_LINES, DOC_INDEX_LINES = get_doc_index_lines()

def version_to_int_pair(v):
    return tuple(map(int, v.split('.')))

def get_known_versions():
    # We could either get the files from the doc index, or from the
    # directory list.  We assume that the doc index is more
    # representative.  If we wanted to use the directory list, we
    # would do:
    # compat_files = os.listdir(os.path.join(ROOT_PATH, 'theories', 'Compat'))
    compat_files = re.findall(r'Coq[^\.]+\.v', '\n'.join(COMPAT_INDEX_LINES))
    return tuple(sorted((compat_name_to_version_name(i) for i in compat_files if i.startswith('Coq') and i.endswith('.v')), key=version_to_int_pair))

def get_new_versions(known_versions, **args):
    if args['cur_version'] in known_versions:
        assert(known_versions[-1] == args['cur_version'])
        known_versions = known_versions[:-1]
    assert(len(known_versions) >= args['number_of_old_versions'])
    return tuple(list(known_versions[-args['number_of_old_versions']:]) + [args['cur_version']])

def print_diff(olds, news, numch=30):
    for ch in range(min(len(olds), len(news))):
        if olds[ch] != news[ch]:
            print('Character %d differs:\nOld: %s\nNew: %s' % (ch, repr(olds[ch:][:numch]), repr(news[ch:][numch])))
            return
    ch = min(len(olds), len(news))
    assert(len(olds) != len(news))
    print('Strings are different lengths:\nOld tail: %s\nNew tail: %s' % (repr(olds[ch:]), repr(news[ch:])))

def update_shebang_to_match(contents, new_contents, path):
    contents_lines = contents.split('\n')
    new_contents_lines = new_contents.split('\n')
    if not (contents_lines[0].startswith('#!/') and contents_lines[0].endswith('bash')):
        raise Exception('Unrecognized #! line in existing %s: %s' % (os.path.relpath(path, ROOT_PATH), repr(contents_lines[0])))
    if not (new_contents_lines[0].startswith('#!/') and new_contents_lines[0].endswith('bash')):
        raise Exception('Unrecognized #! line in new %s: %s' % (os.path.relpath(path, ROOT_PATH), repr(new_contents_lines[0])))
    new_contents_lines[0] = contents_lines[0]
    return '\n'.join(new_contents_lines)

def update_if_changed(contents, new_contents, path, exn_string='%s changed!', suggest_add=False, pass_through_shebang=False, assert_unchanged=False, **args):
    if contents is not None and pass_through_shebang:
        new_contents = update_shebang_to_match(contents, new_contents, path)
    if contents is None or contents != new_contents:
        if not assert_unchanged:
            print('Updating %s...' % os.path.relpath(path, ROOT_PATH))
            with open(path, 'w') as f:
                f.write(new_contents)
            maybe_git_add(os.path.relpath(path, ROOT_PATH), suggest_add=suggest_add, **args)
        else:
            if contents is not None:
                print('Unexpected change:\nOld contents:\n%s\n\nNew contents:\n%s\n' % (contents, new_contents))
                print_diff(contents, new_contents)
            raise Exception(exn_string % os.path.relpath(path, ROOT_PATH))

def update_file(new_contents, path, **args):
    update_if_changed(None, new_contents, path, **args)

def update_compat_files(old_versions, new_versions, assert_unchanged=False, **args):
    for v in old_versions:
        if v not in new_versions:
            compat_file = os.path.join('theories', 'Compat', version_name_to_compat_name(v))
            if not assert_unchanged:
                print('Removing %s...' % compat_file)
                compat_path = os.path.join(ROOT_PATH, compat_file)
                os.rename(compat_path, compat_path + '.bak')
                maybe_git_rm(compat_file, **args)
            else:
                raise Exception('%s exists!' % compat_file)
    for v, next_v in zip(new_versions, list(new_versions[1:]) + [None]):
        compat_file = os.path.join('theories', 'Compat', version_name_to_compat_name(v))
        compat_path = os.path.join(ROOT_PATH, compat_file)
        if not os.path.exists(compat_path):
            print('Creating %s...' % compat_file)
            contents = HEADER + (EXTRA_HEADER % v)
            if next_v is not None:
                contents += '\nRequire Export Coq.Compat.%s.\n' % version_name_to_compat_name(next_v, ext='')
            update_file(contents, compat_path, exn_string='%s does not exist!', assert_unchanged=assert_unchanged, **args)
        else:
            # print('Checking %s...' % compat_file)
            with open(compat_path, 'r') as f:
                contents = f.read()
            header = HEADER + (EXTRA_HEADER % v)
            if not contents.startswith(HEADER):
                raise Exception("Invalid header in %s; does not match %s" % (compat_file, os.path.relpath(HEADER_PATH, ROOT_PATH)))
            if not contents.startswith(header):
                raise Exception("Invalid header in %s; missing line %s" % (compat_file, EXTRA_HEADER.strip('\n') % v))
            if next_v is not None:
                line = 'Require Export Coq.Compat.%s.' % version_name_to_compat_name(next_v, ext='')
                if ('\n%s\n' % line) not in contents:
                    if not contents.startswith(header + '\n'):
                        contents = contents.replace(header, header + '\n')
                    contents = contents.replace(header, '%s\n%s' % (header, line))
                    update_file(contents, compat_path, exn_string=('Compat file %%s is missing line %s' % line), assert_unchanged=assert_unchanged, **args)

def update_compat_versions_type_line(new_versions, contents, relpath):
    compat_version_string = ' | '.join(['V%s_%s' % tuple(v.split('.')) for v in new_versions[:-1]] + ['Current'])
    new_compat_line = 'type compat_version = %s' % compat_version_string
    new_contents = re.sub(r'^type compat_version = .*$', new_compat_line, contents, flags=re.MULTILINE)
    if new_compat_line not in new_contents:
        raise Exception("Could not find 'type compat_version =' in %s" % relpath)
    return new_contents

def update_version_compare(new_versions, contents, relpath):
    first_line = 'let version_compare v1 v2 = match v1, v2 with'
    new_lines = [first_line]
    for v in new_versions[:-1]:
        V = 'V%s_%s' % tuple(v.split('.'))
        new_lines.append('  | %s, %s -> 0' % (V, V))
        new_lines.append('  | %s, _ -> -1' % V)
        new_lines.append('  | _, %s -> 1' % V)
    new_lines.append('  | Current, Current -> 0')
    new_lines = '\n'.join(new_lines)
    new_contents = re.sub(first_line + '.*' + 'Current, Current -> 0', new_lines, contents, flags=re.DOTALL|re.MULTILINE)
    if new_lines not in new_contents:
        raise Exception('Could not find version_compare in %s' % relpath)
    return new_contents

def update_pr_version(new_versions, contents, relpath):
    first_line = 'let pr_version = function'
    new_lines = [first_line]
    for v in new_versions[:-1]:
        V = 'V%s_%s' % tuple(v.split('.'))
        new_lines.append('  | %s -> "%s"' % (V, v))
    new_lines.append('  | Current -> "current"')
    new_lines = '\n'.join(new_lines)
    new_contents = re.sub(first_line + '.*' + 'Current -> "current"', new_lines, contents, flags=re.DOTALL|re.MULTILINE)
    if new_lines not in new_contents:
        raise Exception('Could not find pr_version in %s' % relpath)
    return new_contents

def update_add_compat_require(new_versions, contents, relpath):
    first_line = 'let add_compat_require opts v ='
    new_lines = [first_line, '  match v with']
    for v in new_versions[:-1]:
        V = 'V%s_%s' % tuple(v.split('.'))
        new_lines.append('  | Flags.%s -> add_vo_require opts "Coq.Compat.%s" None (Some false)' % (V, version_name_to_compat_name(v, ext='')))
    new_lines.append('  | Flags.Current -> add_vo_require opts "Coq.Compat.%s" None (Some false)' % version_name_to_compat_name(new_versions[-1], ext=''))
    new_lines = '\n'.join(new_lines)
    new_contents = re.sub(first_line + '.*' + 'Flags.Current -> add_vo_require opts "Coq.Compat.[^"]+" None .Some false.', new_lines, contents, flags=re.DOTALL|re.MULTILINE)
    if new_lines not in new_contents:
        raise Exception('Could not find add_compat_require in %s' % relpath)
    return new_contents

def update_parse_compat_version(new_versions, contents, relpath, **args):
    line_count = 3 # 1 for the first line, 1 for the invalid flags, and 1 for Current
    first_line = 'let parse_compat_version = let open Flags in function'
    split_contents = contents[contents.index(first_line):].split('\n')
    while True:
        cur_line = split_contents[:line_count][-1]
        if re.match(r'^  \| \([0-9 "\.\|]*\) as s ->$', cur_line) is not None:
            break
        elif re.match(r'^  \| "[0-9\.]*" -> V[0-9_]*$', cur_line) is not None:
            line_count += 1
        else:
            raise Exception('Could not recognize line %d of parse_compat_version in %s as a list of invalid versions (line was %s)' % (line_count, relpath, repr(cur_line)))
    old_function_lines = split_contents[:line_count]
    all_versions = re.findall(r'"([0-9\.]+)"', ''.join(old_function_lines))
    invalid_versions = tuple(i for i in all_versions if i not in new_versions)
    new_function_lines = [first_line]
    for v, V in reversed(list(zip(new_versions, ['V%s_%s' % tuple(v.split('.')) for v in new_versions[:-1]] + ['Current']))):
        new_function_lines.append('  | "%s" -> %s' % (v, V))
    new_function_lines.append('  | (%s) as s ->' % ' | '.join('"%s"' % v for v in invalid_versions))
    new_lines = '\n'.join(new_function_lines)
    new_contents = contents.replace('\n'.join(old_function_lines), new_lines)
    if new_lines not in new_contents:
        raise Exception('Could not find parse_compat_version in %s' % relpath)
    return new_contents

def check_no_old_versions(old_versions, new_versions, contents, relpath):
    for v in old_versions:
        if v not in new_versions:
            V = 'V%s_%s' % tuple(v.split('.'))
            if V in contents:
                raise Exception('Unreplaced usage of %s remaining in %s' % (V, relpath))

def update_flags_mli(old_versions, new_versions, **args):
    with open(FLAGS_MLI_PATH, 'r') as f: contents = f.read()
    new_contents = update_compat_versions_type_line(new_versions, contents, os.path.relpath(FLAGS_MLI_PATH, ROOT_PATH))
    check_no_old_versions(old_versions, new_versions, new_contents, os.path.relpath(FLAGS_MLI_PATH, ROOT_PATH))
    update_if_changed(contents, new_contents, FLAGS_MLI_PATH, **args)

def update_flags_ml(old_versions, new_versions, **args):
    with open(FLAGS_ML_PATH, 'r') as f: contents = f.read()
    new_contents = update_compat_versions_type_line(new_versions, contents, os.path.relpath(FLAGS_ML_PATH, ROOT_PATH))
    new_contents = update_version_compare(new_versions, new_contents, os.path.relpath(FLAGS_ML_PATH, ROOT_PATH))
    new_contents = update_pr_version(new_versions, new_contents, os.path.relpath(FLAGS_ML_PATH, ROOT_PATH))
    check_no_old_versions(old_versions, new_versions, new_contents, os.path.relpath(FLAGS_ML_PATH, ROOT_PATH))
    update_if_changed(contents, new_contents, FLAGS_ML_PATH, **args)

def update_coqargs_ml(old_versions, new_versions, **args):
    with open(COQARGS_ML_PATH, 'r') as f: contents = f.read()
    new_contents = update_add_compat_require(new_versions, contents, os.path.relpath(COQARGS_ML_PATH, ROOT_PATH))
    check_no_old_versions(old_versions, new_versions, new_contents, os.path.relpath(COQARGS_ML_PATH, ROOT_PATH))
    update_if_changed(contents, new_contents, COQARGS_ML_PATH, **args)

def update_g_vernac(old_versions, new_versions, **args):
    with open(G_VERNAC_PATH, 'r') as f: contents = f.read()
    new_contents = update_parse_compat_version(new_versions, contents, os.path.relpath(G_VERNAC_PATH, ROOT_PATH), **args)
    check_no_old_versions(old_versions, new_versions, new_contents, os.path.relpath(G_VERNAC_PATH, ROOT_PATH))
    update_if_changed(contents, new_contents, G_VERNAC_PATH, **args)

def update_flags(old_versions, new_versions, **args):
    update_flags_mli(old_versions, new_versions, **args)
    update_flags_ml(old_versions, new_versions, **args)
    update_coqargs_ml(old_versions, new_versions, **args)
    update_g_vernac(old_versions, new_versions, **args)

def update_test_suite(new_versions, assert_unchanged=False, test_suite_paths=TEST_SUITE_PATHS, test_suite_descriptions=TEST_SUITE_DESCRIPTIONS, **args):
    assert(len(new_versions) == len(test_suite_paths))
    assert(len(new_versions) == len(test_suite_descriptions))
    for i, (v, path, descr) in enumerate(zip(new_versions, test_suite_paths, test_suite_descriptions)):
        contents = None
        suggest_add = False
        if os.path.exists(path):
            with open(path, 'r') as f: contents = f.read()
        else:
            suggest_add = True
        if '%s' in descr: descr = descr % v
        lines = ['(* -*- coq-prog-args: ("-compat" "%s") -*- *)' % v,
                 '(** Check that the %s compatibility flag actually requires the relevant modules. *)' % descr]
        for imp_v in reversed(new_versions[i:]):
            lines.append('Import Coq.Compat.%s.' % version_name_to_compat_name(imp_v, ext=''))
        lines.append('')
        new_contents = '\n'.join(lines)
        update_if_changed(contents, new_contents, path, suggest_add=suggest_add, **args)

def update_doc_index(new_versions, **args):
    with open(DOC_INDEX_PATH, 'r') as f: contents = f.read()
    firstline = '    theories/Compat/AdmitAxiom.v'
    new_contents = ''.join(DOC_INDEX_LINES)
    if firstline not in new_contents:
        raise Exception("Could not find line '%s' in %s" % (firstline, os.path.relpath(DOC_INDEX_PATH, ROOT_PATH)))
    extra_lines = ['    theories/Compat/%s' % version_name_to_compat_name(v) for v in new_versions]
    new_contents = new_contents.replace(firstline, '\n'.join([firstline] + extra_lines))
    update_if_changed(contents, new_contents, DOC_INDEX_PATH, **args)

def update_test_suite_run(**args):
    with open(TEST_SUITE_RUN_PATH, 'r') as f: contents = f.read()
    new_contents = r'''#!/usr/bin/env bash

# allow running this script from any directory by basing things on where the script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

# we assume that the script lives in test-suite/tools/update-compat/,
# and that update-compat.py lives in dev/tools/
cd "${SCRIPT_DIR}/../../.."
dev/tools/update-compat.py --assert-unchanged %s || exit $?
''' % ' '.join([('--master' if args['master'] else ''), ('--release' if args['release'] else '')]).strip()
    update_if_changed(contents, new_contents, TEST_SUITE_RUN_PATH, pass_through_shebang=True, **args)

def update_bug_4789(new_versions, **args):
    # we always update this compat notation to oldest
    # currently-supported compat version, which should never be the
    # current version
    with open(BUG_4798_PATH, 'r') as f: contents = f.read()
    new_contents = r"""Check match 2 with 0 => 0 | S n => n end.
Notation "|" := 1 (compat "%s").
Check match 2 with 0 => 0 | S n => n end. (* fails *)
""" % new_versions[0]
    update_if_changed(contents, new_contents, BUG_4798_PATH, **args)

def update_compat_notations_in(old_versions, new_versions, contents):
    for v in old_versions:
        if v not in new_versions:
            reg = re.compile(r'^[ \t]*(?:Notation|Infix)[^\n]*?compat "%s"[^\n]*?\n' % v, flags=re.MULTILINE)
            contents = re.sub(r'^[ \t]*(?:Notation|Infix)[^\n]*?compat "%s"[^\n]*?\n' % v, '', contents, flags=re.MULTILINE)
    return contents

def update_compat_notations(old_versions, new_versions, **args):
    for root, dirs, files in os.walk(os.path.join(ROOT_PATH, 'theories')):
        for fname in files:
            if not fname.endswith('.v'): continue
            with open(os.path.join(root, fname), 'r') as f: contents = f.read()
            new_contents = update_compat_notations_in(old_versions, new_versions, contents)
            update_if_changed(contents, new_contents, os.path.join(root, fname), **args)

def display_git_grep(old_versions, new_versions):
    Vs = ['V%s_%s' % tuple(v.split('.')) for v in old_versions if v not in new_versions]
    compat_vs = ['compat "%s"' % v for v in old_versions if v not in new_versions]
    all_options = tuple(Vs + compat_vs)
    options = (['"-compat" "%s"' % v for v in old_versions if v not in new_versions] +
               [version_name_to_compat_name(v, ext='') for v in old_versions if v not in new_versions])
    if len(options) > 0 or len(all_options) > 0:
        print('To discover what files require manual updating, run:')
        if len(options) > 0: print("git grep -- '%s' test-suite/" % r'\|'.join(options))
        if len(all_options) > 0: print("git grep -- '%s'" % r'\|'.join(all_options))

def parse_args(argv):
    args = {
        'assert_unchanged': False,
        'cur_version': None,
        'number_of_old_versions': None,
        'master': False,
        'release': False,
        'git_add': False,
    }
    if '--master' not in argv and '--release' not in argv:
        print(r'''WARNING: You should pass either --release (sometime before branching)
  or --master (right after branching and updating the version number in version.ml)''')
        if '--assert-unchanged' not in args: break_or_continue()
    for arg in argv[1:]:
        if arg == '--assert-unchanged':
            args['assert_unchanged'] = True
        elif arg == '--git-add':
            args['git_add'] = True
        elif arg == '--master':
            args['master'] = True
            if args['number_of_old_versions'] is None: args['number_of_old_versions'] = MASTER_NUMBER_OF_OLD_VERSIONS
        elif arg == '--release':
            args['release'] = True
            if args['number_of_old_versions'] is None: args['number_of_old_versions'] = RELEASE_NUMBER_OF_OLD_VERSIONS
        elif arg.startswith('--cur-version='):
            args['cur_version'] = arg[len('--cur-version='):]
            assert(len(args['cur_version'].split('.')) == 2)
            assert(all(map(str.isdigit, args['cur_version'].split('.'))))
        elif arg.startswith('--number-of-old-versions='):
            args['number_of_old_versions'] = int(arg[len('--number-of-old-versions='):])
        else:
            print('USAGE: %s [--assert-unchanged] [--cur-version=NN.NN] [--number-of-old-versions=NN] [--git-add]' % argv[0])
            print('')
            print('ERROR: Unrecognized argument: %s' % arg)
            sys.exit(1)
    if args['number_of_old_versions'] is None: args['number_of_old_versions'] = DEFAULT_NUMBER_OF_OLD_VERSIONS
    return args

if __name__ == '__main__':
    args = parse_args(sys.argv)
    args['cur_version'] = get_version(args['cur_version'])
    args['number_of_compat_versions'] = args['number_of_old_versions'] + 1
    known_versions = get_known_versions()
    new_versions = get_new_versions(known_versions, **args)
    assert(len(TEST_SUITE_PATHS) >= args['number_of_compat_versions'])
    args['test_suite_paths'] = tuple(TEST_SUITE_PATHS[-args['number_of_compat_versions']:])
    args['test_suite_descriptions'] = tuple(TEST_SUITE_DESCRIPTIONS[-args['number_of_compat_versions']:])
    update_compat_files(known_versions, new_versions, **args)
    update_flags(known_versions, new_versions, **args)
    update_test_suite(new_versions, **args)
    update_test_suite_run(**args)
    update_doc_index(new_versions, **args)
    update_bug_4789(new_versions, **args)
    update_compat_notations(known_versions, new_versions, **args)
    display_git_grep(known_versions, new_versions)
