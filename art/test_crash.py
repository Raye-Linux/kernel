#!/usr/bin/env python3
# Tests for crash.py, the picture drawn on the crash screen.
#
#   python3 -m pytest art/
#
# The rendering tests need python3-pil, fonts-inter and the theme repo
# next to this one (../theme); they are skipped when one is missing.

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crash  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET = os.path.join(REPO, "assets", "raye-crash.pbm")

have_pil = True
try:
    from PIL import Image
except ImportError:
    have_pil = False

needs_pil = pytest.mark.skipif(not have_pil, reason="python3-pil missing")


def can_render():
    if not have_pil:
        return False
    try:
        crash.find_fonts()
    except FileNotFoundError:
        return False
    return os.path.exists(crash.DEFAULT_EYE)


needs_render = pytest.mark.skipif(
    not can_render(), reason="fonts-inter or ../theme missing")


def parse_pbm(data):
    """Plain PBM to (width, height, rows of 0/1 where 1 = drawn)."""
    words = []
    for line in data.decode("ascii").splitlines():
        words.append(line.split("#", 1)[0])
    text = " ".join(words).split()
    assert text[0] == "P1"
    w, h = int(text[1]), int(text[2])
    bits = "".join(text[3:])
    assert len(bits) == w * h
    # in a PBM '1' is black; the kernel draws the white ('0') pixels
    rows = [[1 if bits[y * w + x] == "0" else 0 for x in range(w)]
            for y in range(h)]
    return w, h, rows


# -- the words ----------------------------------------------------------

def test_words_are_the_agreed_sentences_with_accents():
    lines = [text for text, _ in crash.LINES]
    assert lines == [
        "Raye ran into a problem and needs to restart.",
        "Your files are safe. It restarts by itself.",
        "Raye a rencontré un problème et doit redémarrer.",
        "Vos fichiers sont en sécurité. L'ordinateur redémarre tout seul.",
    ]


def test_titles_are_medium_and_the_rest_regular():
    styles = [style for _, style in crash.LINES]
    assert styles == ["title", "body", "title", "body"]
    assert crash.STYLES["title"] == ("Inter-Medium", 28)
    assert crash.STYLES["body"] == ("Inter-Regular", 20)


def test_no_word_names_anything_but_raye():
    text = " ".join(t for t, _ in crash.LINES).lower()
    for word in ("linux", "kernel", "panic", "windows", "tux"):
        assert word not in text


# -- the PBM writer ------------------------------------------------------

@needs_pil
def test_pbm_is_plain_and_white_means_drawn():
    img = Image.new("1", (10, 3), 0)
    img.putpixel((0, 0), 1)
    img.putpixel((9, 2), 1)
    data = crash.to_pbm(img)
    assert data.startswith(b"P1\n")
    w, h, rows = parse_pbm(data)
    assert (w, h) == (10, 3)
    assert rows[0][0] == 1 and rows[2][9] == 1
    assert sum(map(sum, rows)) == 2


@needs_pil
def test_pbm_lines_stay_short_and_ascii():
    img = Image.new("1", (333, 7), 1)
    data = crash.to_pbm(img)
    for line in data.split(b"\n"):
        assert len(line) <= 70
        assert set(line) <= set(b"P0123456789 #abcdefghijklmnopqrstuvwxyz"
                                b"ABCDEFGHIJKLMNOPQRSTUVWXYZ.,:/-_()'")


@needs_pil
def test_pbm_round_trip_keeps_every_pixel():
    img = Image.new("1", (17, 5), 0)
    for x, y in ((0, 0), (16, 4), (8, 2), (3, 1)):
        img.putpixel((x, y), 1)
    w, h, rows = parse_pbm(crash.to_pbm(img))
    for y in range(h):
        for x in range(w):
            assert rows[y][x] == (1 if img.getpixel((x, y)) else 0)


# -- the eye -------------------------------------------------------------

@needs_render
def test_eye_is_centred_and_has_no_trails():
    eye = crash.eye_mask(crash.DEFAULT_EYE, crash.EYE_WIDTH)
    assert eye.mode == "1"
    assert eye.width == crash.EYE_WIDTH
    box = eye.getbbox()
    assert box is not None
    left, top, right, bottom = box
    # the almond fills the width: its two tips touch both sides
    assert left <= 2 and right >= eye.width - 2
    # the left half and the right half carry about the same ink
    half = eye.width // 2
    lw = sum(1 for x in range(half) for y in range(eye.height)
             if eye.getpixel((x, y)))
    rw = sum(1 for x in range(half, eye.width) for y in range(eye.height)
             if eye.getpixel((x, y)))
    assert abs(lw - rw) < 0.15 * (lw + rw)


@needs_render
def test_eye_keeps_the_pupil_open():
    eye = crash.eye_mask(crash.DEFAULT_EYE, crash.EYE_WIDTH)
    # the pupil is a hole in the middle of the iris
    cx, cy = eye.width // 2, eye.height // 2
    assert not eye.getpixel((cx, cy))


# -- the picture ---------------------------------------------------------

@needs_render
def test_picture_size_fits_the_smallest_screen_with_room_for_text():
    img = crash.render()
    assert img.mode == "1"
    assert img.width == crash.WIDTH
    assert img.width % 8 == 0
    assert img.height <= 300
    # 1024x768 with VGA 8x16: picture + two lines of space + three lines
    assert img.width <= 1024 - 2 * 64
    assert img.height + 2 * 16 + 3 * 16 <= 768


@needs_render
def test_every_line_fits_inside_the_margins():
    fonts = crash.find_fonts()
    for text, style in crash.LINES:
        w = crash.text_width(text, fonts[style])
        assert w <= crash.WIDTH - 2 * crash.MARGIN, text


@needs_render
def test_picture_is_centred_left_to_right():
    img = crash.render()
    left, top, right, bottom = img.getbbox()
    assert abs(left - (img.width - right)) <= 2
    assert top <= 2 and img.height - bottom <= 2


@needs_render
def test_render_is_reproducible():
    a = crash.to_pbm(crash.render())
    b = crash.to_pbm(crash.render())
    assert a == b


@needs_render
def test_committed_picture_is_the_current_render():
    with open(ASSET, "rb") as f:
        committed = f.read()
    assert committed == crash.to_pbm(crash.render()), (
        "assets/raye-crash.pbm is out of date: run art/crash.py")


def test_committed_picture_is_a_plain_pbm_the_kernel_takes():
    with open(ASSET, "rb") as f:
        data = f.read()
    w, h, rows = parse_pbm(data)
    assert (w, h) == (crash.WIDTH, len(rows))
    assert h <= 300
    assert any(any(r) for r in rows)
