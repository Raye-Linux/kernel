#!/usr/bin/env python3
# The EFI stub measures the kernel command line into the TPM before it
# reads "quiet". When the firmware's event log is full, HashLogExtendEvent
# answers EFI_VOLUME_FULL (0x800000000000000b): the PCR is extended, only
# the log entry is missing. That used to print a WARNING over the firmware
# logo on every boot of such a machine. It must stay quiet, and every other
# failure must still warn.
#
#   ./fetch-sources.sh 7.0.0-43.43 && python3 -m pytest tests/test_efi_stub_quiet.py

import os
import re
import shutil
import subprocess
import tempfile

import pytest

from conftest import HOW, kernel_tree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
STUB = "drivers/firmware/efi/libstub/efi-stub-helper.c"
TREE = kernel_tree()


def patches_for(path):
    out = []
    for name in sorted(os.listdir(os.path.join(REPO, "patches"))):
        if not name.endswith(".patch"):
            continue
        with open(os.path.join(REPO, "patches", name), encoding="utf-8") as f:
            if ("+++ b/" + path) in f.read():
                out.append(os.path.join(REPO, "patches", name))
    return out


def test_a_patch_touches_the_stub():
    assert patches_for(STUB), "no patch changes " + STUB


@pytest.fixture(scope="module")
def patched():
    if not TREE or not shutil.which("patch"):
        pytest.skip(HOW)
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, STUB)
        os.makedirs(os.path.dirname(dst))
        shutil.copy(os.path.join(TREE, STUB), dst)
        for p in patches_for(STUB):
            with open(p, "rb") as f:
                r = subprocess.run(["patch", "-p1", "--fuzz=0", "--forward",
                                    "--batch"], cwd=tmp, stdin=f,
                                   capture_output=True)
            assert r.returncode == 0, r.stdout.decode()
        with open(dst, encoding="utf-8") as f:
            yield f.read()


def measure_body(src):
    m = re.search(r"\nstatic efi_status_t efi_measure_tagged_event\(.*?\n}\n",
                  src, re.S)
    assert m, "efi_measure_tagged_event() not found"
    return m.group(0)


def test_volume_full_is_the_status_the_firmware_gave(patched):
    m = re.search(r"#define EFI_VOLUME_FULL\s+\((\d+) \| \(1UL << "
                  r"\(BITS_PER_LONG-1\)\)\)", patched)
    assert m and int(m.group(1)) == 0xb


def test_full_log_is_not_printed_by_default(patched):
    body = measure_body(patched)
    before_fail = body.split("\nfail:")[0]
    m = re.search(r"if \(status == EFI_VOLUME_FULL\) \{(.*?)\n\t\}",
                  before_fail, re.S)
    assert m, "no EFI_VOLUME_FULL case before fail:"
    branch = m.group(1)
    assert "efi_debug(" in branch
    assert "efi_warn(" not in branch and "efi_err(" not in branch
    assert "return status;" in branch, "falls through to the warning"


def test_other_failures_still_warn(patched):
    after_fail = measure_body(patched).split("\nfail:")[1]
    assert re.search(r'efi_warn\("Failed to measure data for event %d: '
                     r'0x%lx\\n", event, status\);', after_fail)
