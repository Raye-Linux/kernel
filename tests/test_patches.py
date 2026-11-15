#!/usr/bin/env python3
# Checks the patches and the config fragment without building anything.
# With RAYE_KERNEL_TREE (an unpatched source of the version build.sh
# builds) it also checks that every patch still applies, in order: the
# first thing to look at after an Ubuntu kernel update.
#
#   python3 -m pytest tests/test_patches.py
#   RAYE_KERNEL_TREE=/path/to/linux python3 -m pytest tests/test_patches.py

import os
import re
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PATCHES = sorted(
    os.path.join(REPO, "patches", f)
    for f in os.listdir(os.path.join(REPO, "patches"))
    if f.endswith(".patch"))
CONFIG = os.path.join(REPO, "config", "raye.config")
from conftest import HOW, kernel_tree

TREE = kernel_tree()


def touched_files(patch, created=False):
    """The files `patch` changes. created=True gives the ones it CREATES
    instead (its "--- " line is /dev/null) -- they do not exist upstream,
    so nothing can fetch them and nothing should copy them."""
    out = []
    new_file = False
    with open(patch, encoding="utf-8") as f:
        for line in f:
            if line.startswith("--- "):
                new_file = line.split()[1] == "/dev/null"
            elif line.startswith("+++ b/") and new_file is created:
                out.append(line[6:].split("\t")[0].strip())
    return out


@pytest.mark.parametrize("patch", PATCHES, ids=os.path.basename)
def test_patch_says_what_it_does(patch):
    with open(patch, encoding="utf-8") as f:
        head = f.read().split("\n--- a/", 1)[0].splitlines()
    assert head and head[0].strip(), "first line is the subject"
    assert len(head) > 2 and not head[1].strip(), "blank line after the subject"
    assert any(line.strip() for line in head[2:]), "a description follows"
    assert touched_files(patch), "no file changed"


def test_patches_numbered_without_gaps():
    numbers = [int(os.path.basename(p)[:4]) for p in PATCHES]
    assert numbers == list(range(1, len(numbers) + 1))


def test_config_fragment_is_well_formed():
    seen = {}
    with open(CONFIG, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            m = (re.fullmatch(r"(CONFIG_[A-Za-z0-9_]+)=(.+)", line) or
                 re.fullmatch(r"# (CONFIG_[A-Za-z0-9_]+) is not set", line))
            if m:
                assert m.group(1) not in seen, f"{m.group(1)} set twice (line {n})"
                seen[m.group(1)] = n
            else:
                assert not line or line.startswith("# "), f"odd line {n}: {line}"
    # one preemption model only
    models = [o for o in ("CONFIG_PREEMPT", "CONFIG_PREEMPT_LAZY",
                          "CONFIG_PREEMPT_VOLUNTARY", "CONFIG_PREEMPT_NONE")
              if o in seen]
    assert len(models) <= 1, models


@pytest.mark.skipif(not TREE or not shutil.which("patch"),
                    reason=HOW)
def test_patches_apply_in_order():
    files = sorted({f for p in PATCHES for f in touched_files(p)})
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            src = os.path.join(TREE, f)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(os.path.join(tmp, f)), exist_ok=True)
                shutil.copy(src, os.path.join(tmp, f))
        for p in PATCHES:
            with open(p, "rb") as f:
                # the same flags build.sh uses: a hunk that only fits with
                # fuzz is a hunk in about the right place, so it fails here too
                r = subprocess.run(["patch", "-p1", "--fuzz=0",
                                    "--forward", "--batch"],
                                   cwd=tmp, stdin=f, capture_output=True)
            assert r.returncode == 0, os.path.basename(p) + "\n" + r.stdout.decode()
