#!/usr/bin/env python3
# Draws the crash screen with tests/panic-sim at several sizes and checks
# what lands on the screen. Needs a linux source tree of the version
# build.sh builds (patched or not) and gcc:
#
#   RAYE_KERNEL_TREE=/path/to/linux python3 -m pytest tests/
#
# Skipped without RAYE_KERNEL_TREE.

import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUN = os.path.join(HERE, "panic-sim", "run.sh")
PICTURE = os.path.join(REPO, "assets", "raye-crash.pbm")
from conftest import HOW, kernel_tree

TREE = kernel_tree()

BG = (0x2a, 0x10, 0x52)
FG = (0xf3, 0xea, 0xff)
DIM = (0xb9, 0xa8, 0xd6)

pytestmark = pytest.mark.skipif(
    not TREE or not shutil.which("gcc"), reason=HOW + " (and gcc)")

sys.path.insert(0, os.path.join(REPO, "art"))


def read_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    head = data.split(b"\n", 3)
    assert head[0] == b"P6" and head[2] == b"255"
    w, h = map(int, head[1].split())
    px = head[3]
    assert len(px) == w * h * 3
    return w, h, px


def pixel(px, w, x, y):
    i = (y * w + x) * 3
    return tuple(px[i:i + 3])


def picture_rows():
    from test_crash import parse_pbm  # noqa: E402 (art/ is on the path)
    with open(PICTURE, "rb") as f:
        return parse_pbm(f.read())


def draw(tmp_path, sizes, description=None):
    env = dict(os.environ)
    if description is not None:
        env["DESCRIPTION"] = description
    subprocess.run([RUN, TREE, str(tmp_path)] + sizes, check=True, env=env,
                   stdout=subprocess.DEVNULL)


def ink_rows(px, w, h):
    """y of the first and last row that has anything but background."""
    rows = [y for y in range(h)
            if any(pixel(px, w, x, y) != BG for x in range(0, w, 1))]
    return rows[0], rows[-1]


def find_picture(px, w, h, pw, ph, rows):
    """y where the picture sits, centred left to right, or None."""
    x0 = (w - pw) // 2
    for y0 in range(0, h - ph + 1):
        ok = True
        for y in range(0, ph, 7):
            for x in range(0, pw, 5):
                want = FG if rows[y][x] else BG
                if pixel(px, w, x0 + x, y0 + y) != want:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return y0
    return None


@pytest.mark.parametrize("size", ["1024x768", "1280x800", "1920x1080",
                                  "800x600"])
def test_picture_is_drawn_centred_with_the_small_print_under_it(
        tmp_path, size):
    draw(tmp_path, [size])
    w, h, px = read_ppm(tmp_path / f"{size}.ppm")
    pw, ph, rows = picture_rows()

    colours = {pixel(px, w, x, y) for y in range(0, h, 3)
               for x in range(0, w, 3)}
    assert colours <= {BG, FG, DIM}, "a pixel was left unpainted"

    y0 = find_picture(px, w, h, pw, ph, rows)
    assert y0 is not None, "the picture is not where it should be"

    top, bottom = ink_rows(px, w, h)
    assert 0 <= top - y0 <= 2
    # the block is centred top to bottom, within a line of the font
    assert abs(top - (h - 1 - bottom)) <= 16
    # the help line and the stop code are under the picture, dimmer
    under = {pixel(px, w, x, y) for y in range(y0 + ph, h)
             for x in range(w)}
    assert DIM in under and FG not in under


@pytest.mark.parametrize("size", ["640x480", "1920x1080:nologo"])
def test_without_room_the_sentences_are_drawn_in_the_console_font(
        tmp_path, size):
    draw(tmp_path, [size])
    name = size.replace(":", "-")
    w, h, px = read_ppm(tmp_path / f"{name}.ppm")
    pw, ph, rows = picture_rows()
    if pw <= w and ph <= h:
        assert find_picture(px, w, h, pw, ph, rows) is None
    colours = {pixel(px, w, x, y) for y in range(h) for x in range(w)}
    assert colours == {BG, FG, DIM}
    top, bottom = ink_rows(px, w, h)
    assert abs(top - (h - 1 - bottom)) <= 32


def test_tiny_screen_and_long_stop_code_stay_inside(tmp_path):
    # the sim aborts on a pixel outside the screen; ASan on a read
    # outside the font or the picture
    draw(tmp_path, ["320x200", "760x300", "1280x400", "4096x2160"],
         description="x" * 400)
    for name in ("320x200", "760x300", "1280x400", "4096x2160"):
        w, h, px = read_ppm(tmp_path / f"{name}.ppm")
        assert (0x00, 0xff, 0x00) not in {
            pixel(px, w, x, y) for y in range(0, h, 2)
            for x in range(0, w, 2)}


def test_stop_code_line_is_drawn(tmp_path):
    draw(tmp_path, ["1024x768"], description="a")
    a = read_ppm(tmp_path / "1024x768.ppm")[2]
    draw(tmp_path, ["1024x768"], description="sysrq triggered crash")
    b = read_ppm(tmp_path / "1024x768.ppm")[2]
    assert a != b
