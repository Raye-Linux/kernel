#!/usr/bin/env python3
# Checks how build.sh applies the patch series. Needs nothing but patch(1):
# the control source and the series are made here, so this runs on any
# machine, after every change to build.sh.
#
#   python3 -m pytest tests/test_build_patching.py
#
# The point: patch(1) can place a hunk "about right" and say nothing. With
# --silent and no --fuzz=0 it answers 0 on a hunk whose context did not
# match, so a change lands twice, or in the wrong function, and the build
# carries on. These tests run build.sh's own patch stage, lifted out of the
# file, and insist that it stops and names the patch instead.

import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BUILD = os.path.join(REPO, "build.sh")

pytestmark = pytest.mark.skipif(not shutil.which("patch"), reason="patch(1) needed")

with open(BUILD, encoding="utf-8") as f:
    BUILD_SH = f.read()


def one_liner(name):
    """build.sh's say() and die() are written on one line each, so the usual
    sed -n '/^f() {/,/^}/p' would run past them to the next function's brace.
    Take the line itself."""
    for line in BUILD_SH.splitlines():
        if line.startswith(name + "() {"):
            return line
    raise AssertionError(name + "() not found in build.sh")


def block(first_line):
    """The if ... fi block starting with first_line, closed by an fi in the
    first column. Taken from build.sh so these tests cannot pass against a
    copy of the code that is no longer the one shipped."""
    lines = BUILD_SH.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(first_line):
            for j in range(i + 1, len(lines)):
                if lines[j] == "fi":
                    return "\n".join(lines[i:j + 1])
            raise AssertionError("no closing fi after: " + first_line)
    raise AssertionError("not found in build.sh: " + first_line)


PATCH_STAGE = block("if [ ! -f .raye-patches ]; then")
UNPACK_GUARD = block('if [ -d "$src" ] && [ -f "$src/.raye-patching" ]; then')
DONE = "RAYE_PATCH_STAGE_DONE"

# Everything the lifted block reads, and nothing else. The list of patches is
# build.sh's business and is not what these tests are about; applying them is.
HARNESS = """set -eu
%(die)s
%(say)s
version=${VERSION:?}
patches=$(ls "${SERIES:?}"/*.patch)
want=$(printf '%%s\\n' "$patches" | while read -r p; do sha256sum "$p"; done)
%(stage)s
echo %(done)s
""" % {"die": one_liner("die"), "say": one_liner("say"),
       "stage": PATCH_STAGE, "done": DONE}

ALPHA = "int a;\nint b;\nint c;\nint d;\nint e;\nint f;\nint g;\nint h;\n"
BETA = "long p;\nlong q;\nlong r;\nlong s;\nlong t;\nlong u;\nlong v;\nlong w;\n"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_patch(series, name, filename, before, after):
    """A unified diff of one file, the shape build.sh's patches have."""
    a = os.path.join(series, "a", filename)
    b = os.path.join(series, "b", filename)
    write(a, before)
    write(b, after)
    diff = subprocess.run(["diff", "-u", "--label", "a/" + filename,
                           "--label", "b/" + filename, a, b],
                          capture_output=True, text=True).stdout
    assert diff, "diff produced nothing: the fixture does not differ"
    write(os.path.join(series, name), diff)
    shutil.rmtree(os.path.join(series, "a"))
    shutil.rmtree(os.path.join(series, "b"))


def fixture(tmp_path, alpha=ALPHA, beta=BETA):
    """A control source of two files, and a series of two patches: 0001
    changes alpha.c, 0002 changes beta.c. Returns (tree, series, run)."""
    tree = str(tmp_path / "linux-7.0.0")
    series = str(tmp_path / "series")
    os.makedirs(series, exist_ok=True)
    write(os.path.join(tree, "alpha.c"), alpha)
    write(os.path.join(tree, "beta.c"), beta)
    make_patch(series, "0001-alpha.patch", "alpha.c",
               ALPHA, ALPHA.replace("int e;", "int e_patched;"))
    make_patch(series, "0002-beta.patch", "beta.c",
               BETA, BETA.replace("long t;", "long t_patched;"))
    run = str(tmp_path / "stage.sh")
    write(run, HARNESS)

    def apply():
        return subprocess.run(["sh", run], cwd=tree, capture_output=True, text=True,
                              env=dict(os.environ, SERIES=series, VERSION="7.0.0-42.42"))

    return tree, series, apply


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# --- what build.sh asks patch(1) for -----------------------------------------

def test_patch_is_called_once_and_refuses_fuzz():
    calls = re.findall(r"^\s*patch .*$", BUILD_SH, re.M)
    assert len(calls) == 1, "expected one patch invocation in build.sh: " + repr(calls)
    call = calls[0]
    assert "--fuzz=0" in call, "a fuzzy hunk is accepted in silence: " + call
    assert "--forward" in call, "an already applied patch is applied backwards: " + call
    assert "--silent" not in call, "--silent hides which patch did what: " + call


def test_a_failed_patch_stops_the_build():
    assert "die " in PATCH_STAGE, "patch's exit status is not acted on"
    assert ": > .raye-patching" in PATCH_STAGE, "no marker for a run that stops half way"
    assert "rm -f .raye-patching" in PATCH_STAGE, "the marker is never cleared"


# --- applying the series -----------------------------------------------------

def test_series_applies_once(tmp_path):
    tree, _, apply = fixture(tmp_path)
    r = apply()
    assert r.returncode == 0, r.stdout + r.stderr
    assert DONE in r.stdout
    assert "int e_patched;" in read(os.path.join(tree, "alpha.c"))
    assert "long t_patched;" in read(os.path.join(tree, "beta.c"))
    assert os.path.exists(os.path.join(tree, ".raye-patches"))
    assert not os.path.exists(os.path.join(tree, ".raye-patching")), \
        "the marker must be gone once the series is in"


def test_second_application_of_the_same_series_is_refused(tmp_path):
    """A source straight out of apt-get source that already holds a patch
    means the change reached Ubuntu. The build must stop and name it, not
    apply it backwards and not apply it twice."""
    tree, _, apply = fixture(tmp_path)
    assert apply().returncode == 0
    # the markers are what tell build.sh the series is in; without them the
    # tree looks fresh, which is exactly how an upstreamed patch looks
    os.remove(os.path.join(tree, ".raye-patches"))
    r = apply()
    assert r.returncode != 0, "a second application was accepted:\n" + r.stdout + r.stderr
    out = r.stdout + r.stderr
    assert "0001-alpha.patch" in out, "the failing patch is not named:\n" + out
    assert DONE not in r.stdout, "the stage reported success"
    assert os.path.exists(os.path.join(tree, ".raye-patching")), \
        "the marker must stay so the next run unpacks the source again"


def test_a_hunk_that_needs_fuzz_is_refused(tmp_path):
    """The dangerous one: patch finds the context about the right place and,
    with --silent and no --fuzz=0, answers 0 without a word."""
    # as if Ubuntu had touched a line next to the one 0002 changes
    tree, _, apply = fixture(tmp_path, beta=BETA.replace("long q;", "long q_ubuntu;"))
    r = apply()
    assert r.returncode != 0, "a fuzzy hunk was accepted:\n" + r.stdout + r.stderr
    out = r.stdout + r.stderr
    assert "0002-beta.patch" in out, "the failing patch is not named:\n" + out
    assert DONE not in r.stdout, "the stage reported success"
    # 0001 did go in, so the run really reached 0002
    assert "int e_patched;" in read(os.path.join(tree, "alpha.c"))
    assert "long t_patched;" not in read(os.path.join(tree, "beta.c")), \
        "the fuzzy hunk was written anyway"


# --- the half patched tree ---------------------------------------------------

def test_a_half_patched_tree_is_unpacked_again(tmp_path):
    """build.sh keeps an already unpacked source to save time. It must not
    keep one a stopped run left half patched: applying the series on top of
    it is the double application the flags above refuse."""
    want = "the wanted series"
    guard = str(tmp_path / "guard.sh")
    write(guard, "set -eu\n%s\nsrc=${SRC:?}\nwant='%s'\n%s\necho GUARD_DONE\n"
          % (one_liner("say"), want, UNPACK_GUARD))

    def guard_run(src):
        r = subprocess.run(["sh", guard], cwd=str(tmp_path), capture_output=True,
                           text=True, env=dict(os.environ, SRC=src))
        assert r.returncode == 0 and "GUARD_DONE" in r.stdout, r.stdout + r.stderr
        return r

    def tree(name, marker, applied):
        path = str(tmp_path / name)
        write(os.path.join(path, "Makefile"), "")
        if applied is not None:
            write(os.path.join(path, ".raye-patches"), applied)
        if marker:
            write(os.path.join(path, ".raye-patching"), "")
        return path

    # a run that stopped half way: the marker decides, even though the series
    # recorded in .raye-patches is the one asked for
    half = tree("half", marker=True, applied=want)
    guard_run("half")
    assert not os.path.exists(half), "a tree left half patched was kept"

    # the series already in, and whole: keeping it is the point of the cache
    done = tree("done", marker=False, applied=want)
    guard_run("done")
    assert os.path.exists(done), "a finished tree must be reused"

    # another series, an experiment with EXTRA_PATCHES: unpacked again
    other = tree("other", marker=False, applied="some other series")
    guard_run("other")
    assert not os.path.exists(other), "a tree with another series was kept"


def test_a_tree_of_another_kernel_version_is_not_reused(tmp_path):
    """7.0.0-42.42 and 7.0.0-43.43 both unpack to linux-7.0.0. If the
    record of the tree does not hold the version, a build for 43.43 takes
    the 42.42 source it finds there and ships it under the new number."""
    line = [l for l in BUILD_SH.splitlines() if l.startswith("want=")]
    assert len(line) == 1, "expected one want= line in build.sh"
    patch = tmp_path / "0001-x.patch"
    patch.write_text("--- a/x\n+++ b/x\n")
    script = tmp_path / "want.sh"
    script.write_text("set -eu\npatches=%s\n%s\nprintf '%%s' \"$want\"\n" % (patch, line[0]))

    def want(version):
        r = subprocess.run(["sh", str(script)], capture_output=True, text=True,
                           env=dict(os.environ, version=version))
        assert r.returncode == 0, r.stderr
        return r.stdout

    assert want("7.0.0-42.42") != want("7.0.0-43.43")
    assert want("7.0.0-43.43") == want("7.0.0-43.43")
