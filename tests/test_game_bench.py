#!/usr/bin/env python3
# Bits of tests/bench/game-bench that decide what a run is labelled with.
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "bench", "game-bench")


def on_ac_function():
    with open(SCRIPT, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("on_ac() {"))
    end = next(i for i in range(start, len(lines)) if lines[i] == "}")
    return "\n".join(lines[start:end + 1])


def on_ac(tmp_path, supplies):
    root = tmp_path / "power_supply"
    root.mkdir()
    for name, kind, online in supplies:
        d = root / name
        d.mkdir()
        (d / "type").write_text(kind + "\n")
        if online is not None:
            (d / "online").write_text(online + "\n")
    script = tmp_path / "t.sh"
    script.write_text("set -eu\n%s\non_ac\n" % on_ac_function())
    r = subprocess.run(["sh", str(script)], env=dict(os.environ, POWER_SUPPLY=str(root)))
    return r.returncode == 0


def test_a_desktop_without_battery_is_on_mains(tmp_path):
    assert on_ac(tmp_path, [])


def test_a_laptop_on_battery_is_not(tmp_path):
    assert not on_ac(tmp_path, [("AC", "Mains", "0"), ("BAT0", "Battery", None)])


def test_a_laptop_plugged_in_is(tmp_path):
    assert on_ac(tmp_path, [("AC", "Mains", "1"), ("BAT0", "Battery", None)])


def test_a_usb_charger_alone_does_not_count(tmp_path):
    # a phone charging from the laptop shows up as an online USB supply
    assert not on_ac(tmp_path, [("AC", "Mains", "0"), ("BAT0", "Battery", None),
                                ("ucsi-source-psy-USBC000:001", "USB", "1")])
