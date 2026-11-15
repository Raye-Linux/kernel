#!/usr/bin/env python3
# The options games rely on are written in config/raye.config, and build.sh
# refuses a configuration that lost one of them.
#
#   python3 -m pytest tests/test_gaming_config.py

import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CONFIG = os.path.join(REPO, "config", "raye.config")
BUILD = os.path.join(REPO, "build.sh")

# option -> value, as Ubuntu's generic 7.0.0-43.43 has it
GAMING = {
    "CONFIG_HZ_1000": "y",
    "CONFIG_HZ": "1000",
    "CONFIG_PREEMPT_DYNAMIC": "y",
    "CONFIG_PREEMPT_LAZY": "y",
    "CONFIG_SCHED_CLASS_EXT": "y",
    "CONFIG_DEBUG_INFO_BTF": "y",
    "CONFIG_BPF_JIT": "y",
    "CONFIG_NTSYNC": "m",
    "CONFIG_FUTEX": "y",
    "CONFIG_TRANSPARENT_HUGEPAGE_MADVISE": "y",
    "CONFIG_X86_BUS_LOCK_DETECT": "y",
    "CONFIG_X86_AMD_PSTATE_DEFAULT_MODE": "3",
    "CONFIG_X86_INTEL_PSTATE": "y",
    "CONFIG_MQ_IOSCHED_DEADLINE": "y",
    "CONFIG_IOSCHED_BFQ": "m",
    "CONFIG_USER_NS": "y",
    "CONFIG_INPUT_UINPUT": "y",
    "CONFIG_HIDRAW": "y",
}


def options(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def test_config_holds_the_gaming_options():
    with open(CONFIG, encoding="utf-8") as f:
        have = options(f.read())
    wrong = {k: have.get(k) for k, v in GAMING.items() if have.get(k) != v}
    assert not wrong, "missing or changed in config/raye.config: %r" % wrong


def config_check():
    """build.sh's own check of the merged .config, lifted out of the file."""
    with open(BUILD, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("missing=$("))
    end = next(i for i in range(start, len(lines)) if lines[i] == "done)")
    return "\n".join(lines[start:end + 1])


def run_check(tmp_path, merged):
    os.makedirs(tmp_path / "config")
    with open(CONFIG, encoding="utf-8") as f:
        (tmp_path / "config" / "raye.config").write_text(f.read())
    (tmp_path / ".config").write_text(merged)
    script = tmp_path / "check.sh"
    script.write_text("set -eu\nhere=%s\nextra_config=\n%s\nprintf '%%s' \"$missing\"\n"
                      % (tmp_path, config_check()))
    r = subprocess.run(["sh", str(script)], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_build_stops_when_ubuntu_drops_one(tmp_path):
    with open(CONFIG, encoding="utf-8") as f:
        merged = f.read()
    assert run_check(tmp_path / "same", merged) == ""
    dropped = merged.replace("CONFIG_NTSYNC=m\n", "# CONFIG_NTSYNC is not set\n")
    assert "CONFIG_NTSYNC=m" in run_check(tmp_path / "dropped", dropped)
    changed = merged.replace("CONFIG_HZ=1000\n", "CONFIG_HZ=250\n")
    assert "CONFIG_HZ=1000" in run_check(tmp_path / "changed", changed)
