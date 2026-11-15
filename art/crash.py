#!/usr/bin/env python3
#
# The picture of the crash screen: the Raye eye and the two sentences,
# in English and in French, set in Inter. The kernel draws it in one
# colour (the crash screen foreground) on the night violet background,
# so it is a 1-bit image, a plain PBM the kernel's logo tool reads.
#
# Run it by hand when the words or the eye change, and commit the
# result:
#
#   art/crash.py                    writes assets/raye-crash.pbm
#   art/crash.py --preview x.png    also a colour preview at 1:1
#   art/crash.py --check            fails if the committed file is stale
#
# Needs python3-pil and fonts-inter, and the theme repo next to this one
# for the eye (../theme/assets/logo/raye-eye.png).
#
# No antialiasing on a 1-bit screen, so the text is rendered with
# FreeType's monochrome hinting at its real size, never scaled.

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_EYE = os.path.normpath(
    os.path.join(REPO, "..", "theme", "assets", "logo", "raye-eye.png"))
DEFAULT_OUT = os.path.join(REPO, "assets", "raye-crash.pbm")

FONT_DIRS = [
    "/usr/share/fonts/opentype/inter",
    "/usr/share/fonts/truetype/inter",
]

# the crash screen colours (config/raye.config), only for the preview
BACKGROUND = (0x2a, 0x10, 0x52)
FOREGROUND = (0xf3, 0xea, 0xff)

WIDTH = 760          # fits 1024x768 with room on both sides
MARGIN = 24
EYE_WIDTH = 240
EYE_THRESHOLD = 90   # luminance over black: the rim and the iris stay
EYE_GAP = 28         # eye to the first sentence
LINE_GAP = 8         # a sentence to the line under it
BLOCK_GAP = 24       # English to French

STYLES = {
    "title": ("Inter-Medium", 28),
    "body": ("Inter-Regular", 20),
}

LINES = [
    ("Raye ran into a problem and needs to restart.", "title"),
    ("Your files are safe. It restarts by itself.", "body"),
    ("Raye a rencontré un problème et doit redémarrer.", "title"),
    ("Vos fichiers sont en sécurité. L'ordinateur redémarre tout seul.",
     "body"),
]


def find_fonts():
    """The two Inter faces, as {style: FreeTypeFont}."""
    dirs = list(FONT_DIRS)
    if os.environ.get("RAYE_FONTS"):
        dirs.insert(0, os.environ["RAYE_FONTS"])
    fonts = {}
    for style, (name, size) in STYLES.items():
        for d in dirs:
            for ext in (".otf", ".ttf"):
                path = os.path.join(d, name + ext)
                if os.path.exists(path):
                    fonts[style] = ImageFont.truetype(path, size)
                    break
            if style in fonts:
                break
        else:
            raise FileNotFoundError(
                f"{name} not found in {', '.join(dirs)} (fonts-inter)")
    return fonts


def _mono_draw(img):
    d = ImageDraw.Draw(img)
    d.fontmode = "1"        # FreeType monochrome rendering, hinted
    return d


def text_box(text, font):
    """Ink box of the text drawn at the origin, baseline at y = 0."""
    return _mono_draw(Image.new("1", (1, 1))).textbbox(
        (0, 0), text, font=font, anchor="ls")


def text_width(text, font):
    left, _, right, _ = text_box(text, font)
    return right - left


def _almond_columns(alpha):
    """Columns of the eye itself: the first run of painted columns.
    The scanline trails start after a gap, to the right."""
    w, h = alpha.size
    painted = [alpha.crop((x, 0, x + 1, h)).getbbox() is not None
               for x in range(w)]
    start = painted.index(True)
    end = start
    while end < w and painted[end]:
        end += 1
    return start, end


def eye_mask(path, width):
    """The eye as a 1-bit mask `width` pixels wide: on where the logo is
    light (rim, iris, highlights), off on the dark inside and the pupil."""
    src = Image.open(path).convert("RGBA")
    alpha = src.getchannel("A").point(lambda v: 255 if v > 8 else 0)
    x0, x1 = _almond_columns(alpha)
    _, y0, _, y1 = alpha.crop((x0, 0, x1, src.height)).getbbox()

    over_black = Image.new("RGBA", src.size, (0, 0, 0, 255))
    over_black.alpha_composite(src)
    lum = over_black.convert("L").crop((x0, y0, x1, y1))

    height = round(lum.height * width / lum.width)
    small = lum.resize((width, height), Image.LANCZOS)
    return small.point(lambda v: 255 if v >= EYE_THRESHOLD else 0).convert("1")


def render(eye_path=DEFAULT_EYE):
    """The whole picture, 1-bit, WIDTH wide, cropped to its content."""
    fonts = find_fonts()
    eye = eye_mask(eye_path, EYE_WIDTH)

    canvas = Image.new("1", (WIDTH, 600), 0)
    canvas.paste(1, ((WIDTH - eye.width) // 2, 0), eye)
    d = _mono_draw(canvas)

    y = eye.height + EYE_GAP
    previous = None
    for text, style in LINES:
        font = fonts[style]
        ascent, descent = font.getmetrics()
        if previous == "body" and style == "title":
            y += BLOCK_GAP
        elif previous is not None:
            y += LINE_GAP
        baseline = y + ascent
        left, _, right, _ = text_box(text, font)
        x = (WIDTH - (right - left)) // 2 - left
        d.text((x, baseline), text, font=font, fill=1, anchor="ls")
        y = baseline + descent
        previous = style

    bottom = canvas.getbbox()[3]
    return canvas.crop((0, 0, WIDTH, bottom))


def to_pbm(img):
    """Plain (ASCII) PBM, the only kind the kernel's logo tool reads.
    The kernel draws the white pixels, so a drawn pixel is a '0'."""
    img = img.convert("1")
    w, h = img.size
    px = img.load()
    out = [f"P1\n# Raye crash screen, made by art/crash.py\n{w} {h}\n"]
    line = []
    for y in range(h):
        for x in range(w):
            line.append("0" if px[x, y] else "1")
            if len(line) == 70:
                out.append("".join(line) + "\n")
                line = []
    if line:
        out.append("".join(line) + "\n")
    return "".join(out).encode("ascii")


def preview(img):
    """The picture in the crash screen colours, 1:1."""
    out = Image.new("RGB", img.size, BACKGROUND)
    out.paste(FOREGROUND, (0, 0), img.convert("L"))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--eye", default=DEFAULT_EYE, help="the Raye eye PNG")
    p.add_argument("--out", default=DEFAULT_OUT, help="the PBM to write")
    p.add_argument("--preview", help="also write a colour preview PNG")
    p.add_argument("--check", action="store_true",
                   help="only compare with --out, exit 1 if it differs")
    args = p.parse_args(argv)

    img = render(args.eye)
    data = to_pbm(img)
    if args.check:
        try:
            with open(args.out, "rb") as f:
                same = f.read() == data
        except FileNotFoundError:
            same = False
        if not same:
            print(f"{args.out} is out of date, run art/crash.py",
                  file=sys.stderr)
            return 1
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, args.out)
    if args.preview:
        preview(img).save(args.preview)
    print(f"{args.out}: {img.width}x{img.height}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
