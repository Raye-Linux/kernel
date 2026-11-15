#!/usr/bin/env python3
# fetch-sources.sh must DERIVE the list of kernel files the tests read, not
# carry it written down. A list typed into the script goes stale the first
# time a patch touches a new file or run.sh reads another one, and the tree
# it builds is then quietly incomplete: the test that needed the missing
# file fails somewhere else entirely, or -- worse -- passes on a stub.
#
#   python3 -m pytest tests/test_fetch_sources.py
#
# This needs nothing: no kernel source, no network.

import os
import re
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FETCH = os.path.join(REPO, "fetch-sources.sh")
RUN_SH = os.path.join(HERE, "panic-sim", "run.sh")
PATCHES = sorted(
    os.path.join(REPO, "patches", f)
    for f in os.listdir(os.path.join(REPO, "patches")) if f.endswith(".patch"))


def from_the_patches():
    """Every file a patch changes, minus the ones it creates: those do not
    exist upstream, and asking for them would be a 404 on every fetch."""
    out = set()
    for patch in PATCHES:
        new = False
        with open(patch, encoding="utf-8") as f:
            for line in f:
                if line.startswith("--- "):
                    new = line.split()[1] == "/dev/null"
                elif line.startswith("+++ b/") and not new:
                    out.add(line[6:].split("\t")[0].strip())
    return out


def from_panic_sim():
    with open(RUN_SH, encoding="utf-8") as f:
        return set(re.findall(r"\$tree/([A-Za-z0-9_/.+-]+)", f.read()))


def listed():
    p = subprocess.run(["sh", FETCH, "--list"], capture_output=True, text=True,
                       cwd=REPO, check=True)
    return set(p.stdout.split())


def test_fetch_sources_lists_what_the_tests_read():
    assert listed() == from_the_patches() | from_panic_sim()


def test_the_list_is_derived_and_not_written_down():
    with open(FETCH, encoding="utf-8") as f:
        script = f.read()
    typed = sorted(p for p in listed() if p in script)
    assert not typed, (
        "fetch-sources.sh has these paths written into it: %s. The list must"
        " be derived from patches/*.patch and tests/panic-sim/run.sh, or it"
        " goes stale without a word and builds an incomplete tree."
        % ", ".join(typed))


def test_a_patch_that_creates_a_file_is_not_asked_for():
    created = set()
    for patch in PATCHES:
        new = False
        with open(patch, encoding="utf-8") as f:
            for line in f:
                if line.startswith("--- "):
                    new = line.split()[1] == "/dev/null"
                elif line.startswith("+++ b/") and new:
                    created.add(line[6:].split("\t")[0].strip())
    if not created:
        pytest.skip("no patch here creates a file")
    assert not (created & listed()), (
        "asking upstream for a file a patch creates is a 404 on every run: %s"
        % ", ".join(sorted(created & listed())))
