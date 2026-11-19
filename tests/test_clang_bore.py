#!/usr/bin/env python3
# The kernel is built with Clang and LLD (ThinLTO) and carries BORE.
# These read build.sh and the config fragment; nothing is built.
#
#   python3 -m pytest tests/test_clang_bore.py

import os
import re
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BUILD = os.path.join(REPO, "build.sh")
CONFIG = os.path.join(REPO, "config", "raye.config")
BORE = os.path.join(REPO, "patches", "0005-sched-add-the-BORE-scheduler.patch")

with open(BUILD, encoding="utf-8") as f:
    BUILD_SH = f.read()


def one_liner(name):
    for line in BUILD_SH.splitlines():
        if line.startswith(name + "() {"):
            return line
    raise AssertionError(name + "() not found in build.sh")


def case_block(first_line):
    lines = BUILD_SH.splitlines()
    i = lines.index(first_line)
    j = next(k for k in range(i, len(lines)) if lines[k] == "esac")
    return "\n".join(lines[i:j + 1])


def run(script, cwd):
    return subprocess.run(["sh", "-c", script], cwd=cwd,
                          capture_output=True, text=True)


def test_config_asks_for_bore_and_thinlto():
    with open(CONFIG, encoding="utf-8") as f:
        text = f.read()
    for line in ("CONFIG_SCHED_BORE=y", "CONFIG_CC_IS_CLANG=y",
                 "CONFIG_LD_IS_LLD=y", "CONFIG_LTO_CLANG_THIN=y",
                 "# CONFIG_LTO_NONE is not set"):
        assert line in text.splitlines(), line


def test_every_make_gets_llvm():
    makes = [l for l in BUILD_SH.splitlines()
             if re.match(r"\s*make\s", l)]
    assert len(makes) >= 2, makes
    for line in makes:
        assert '"$llvm"' in line, "make without LLVM=: " + line


def test_clang_version_from_dsc(tmp_path):
    # a .dsc keeps Build-Depends on one line
    control = tmp_path / "control"
    control.write_text(
        "Format: 3.0 (quilt)\nSource: linux\n"
        "Build-Depends: gcc:native, bindgen:native [amd64], clang-21:native"
        " [amd64 arm64 armhf ppc64el riscv64 s390x], cpio, llvm-21-dev,"
        " zstd <!stage1>\nBuild-Depends-Indep: asciidoc <!stage1>\n")
    script = "%s\n%s\nclang=$(clang_of control)\n%s\necho \"$clang\"" % (
        one_liner("die"), one_liner("clang_of"),
        case_block("case $clang in"))
    r = run(script, tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "21"


@pytest.mark.parametrize("text", [
    "Build-Depends: gcc:native, bindgen:native\n",
    " clang-21:native [amd64],\n clang-22:native [arm64],\n",
], ids=["none", "two"])
def test_unclear_clang_version_stops(tmp_path, text):
    (tmp_path / "control").write_text(text)
    script = "%s\n%s\nclang=$(clang_of control)\n%s\necho ok" % (
        one_liner("die"), one_liner("clang_of"),
        case_block("case $clang in"))
    r = run(script, tmp_path)
    assert r.returncode != 0 and "ok" not in r.stdout
    assert "clang" in r.stderr


def compiler_check(tmp_path, compiler):
    gen = tmp_path / "include" / "generated"
    gen.mkdir(parents=True)
    (gen / "compile.h").write_text(
        '#define UTS_MACHINE\t\t"x86_64"\n'
        '#define LINUX_COMPILER\t\t"%s"\n' % compiler)
    lines = BUILD_SH.splitlines()
    first = next(l for l in lines if l.startswith("compiler=$("))
    script = "%s\n%s\nclang=21\n%s\n%s\necho ok" % (
        one_liner("say"), one_liner("die"), first,
        case_block("case $compiler in"))
    return run(script, tmp_path)


def test_clang_build_passes(tmp_path):
    r = compiler_check(tmp_path, "Ubuntu clang version 21.1.8 (6ubuntu1),"
                                 " Ubuntu LLD 21.1.8")
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


def test_gcc_build_stops(tmp_path):
    r = compiler_check(tmp_path, "x86_64-linux-gnu-gcc (Ubuntu 15.2.0) 15.2.0,"
                                 " GNU ld (GNU Binutils for Ubuntu) 2.45")
    assert r.returncode != 0
    assert "not built with clang" in r.stderr


def test_package_revision_above_the_gcc_build():
    m = re.search(r"^rev=\$\{REV:-(\d+)\}$", BUILD_SH, re.M)
    assert m and int(m.group(1)) >= 2
    assert 'KDEB_PKGVERSION="$version+$flavour$rev"' in BUILD_SH


def test_bore_patch_names_its_source():
    with open(BORE, encoding="utf-8") as f:
        head = f.read().split("\n--- a/", 1)[0]
    assert "firelzrd/bore-scheduler" in head
    assert re.search(r"sha256 [0-9a-f]{64}", head)
    with open(BORE, encoding="utf-8") as f:
        body = f.read()
    assert '#define SCHED_BORE_VERSION  "7.0.0"' in body
    assert "+++ b/kernel/sched/bore.c" in body
