#!/bin/sh
# Draws the Raye crash screen without crashing anything: builds the
# drawing half of the patched drm_panic.c as a normal program (with the
# kernel's own fonts and logo tool) and writes the screen as a picture
# for each size.
#
#   tests/panic-sim/run.sh <kernel tree> <out dir> [WxH[:nologo] ...]
#
# The kernel tree is a linux source, patched by build.sh or not (the
# Raye patch is then applied to a copy). Needs gcc with ASan/UBSan.
# Writes <out dir>/<W>x<H>[-nologo].ppm. DESCRIPTION sets the panic
# description (default "sysrq triggered crash").

set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
tree=$(cd "${1:?usage: run.sh <kernel tree> <out dir> [WxH[:nologo] ...]}" && pwd)
out=${2:?usage: run.sh <kernel tree> <out dir> [WxH[:nologo] ...]}
shift 2
[ $# -gt 0 ] || set -- 1024x768 1280x800 1920x1080 800x600 640x480 1920x1080:nologo

description=${DESCRIPTION:-sysrq triggered crash}
patchfile=$repo/patches/0001-drm-panic-raye-crash-screen.patch
picture=$repo/assets/raye-crash.pbm
mkdir -p "$out"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# a copy of the two patched files, patched here if the tree is not
src=$tmp/src
mkdir -p "$src/drivers/gpu/drm" "$src/drivers/video/fbdev/core"
cp "$tree/drivers/gpu/drm/drm_panic.c" "$src/drivers/gpu/drm/"
cp "$tree/drivers/video/fbdev/core/fb_logo.c" "$src/drivers/video/fbdev/core/"
if ! patch -d "$src" -p1 -R --dry-run --silent < "$patchfile" >/dev/null 2>&1; then
    patch -d "$src" -p1 --silent < "$patchfile"
fi

# the drawing half: up to draw_panic_screen_user(), and the stop code
b=$tmp/build
mkdir -p "$b/inc/linux"
awk '{ print } /^static void draw_panic_screen_user\(/ { f = 1 } f && /^}/ { exit }' \
    "$src/drivers/gpu/drm/drm_panic.c" > "$b/drm_panic_cut.c"
awk '/^static char panic_stop_code/ { f = 1 } f { print }
     /^static void drm_panic_set_description\(/ { g = 1 } g && /^}/ { exit }' \
    "$src/drivers/gpu/drm/drm_panic.c" >> "$b/drm_panic_cut.c"
grep -q 'draw_panic_screen_user' "$b/drm_panic_cut.c" &&
    grep -q 'Stop code: ' "$b/drm_panic_cut.c" ||
    { echo "run.sh: drm_panic.c does not look like the Raye one" >&2; exit 1; }

# every kernel header it includes is the stub, except the three read as they are
grep -hoE '^#include <[^>]+>' "$b/drm_panic_cut.c" | sed 's/^#include <//; s/>$//' |
while read -r h; do
    case $h in linux/font.h|linux/linux_logo.h) continue ;; esac
    mkdir -p "$b/inc/$(dirname "$h")"
    printf '#include "%s/kstub.h"\n' "$here" > "$b/inc/$h"
done
printf '#include "%s/kstub.h"\n' "$here" > "$b/drm_crtc_internal.h"
cp "$tree/include/linux/font.h" "$tree/include/linux/linux_logo.h" "$b/inc/linux/"
cp "$tree/drivers/gpu/drm/drm_draw_internal.h" "$b/"
cp "$tree/lib/fonts/font_8x16.c" "$tree/lib/fonts/font_ter16x32.c" "$b/"

# the picture, through the kernel's own logo tool
gcc -O1 -o "$b/pnmtologo" "$tree/drivers/video/logo/pnmtologo.c"
"$b/pnmtologo" -t mono -n logo_linux_mono -o "$b/logo_linux_mono.c" "$picture"

# the kernel builds with unsigned char: code page 437 bytes index the font
cflags="-std=gnu11 -funsigned-char -O1 -g -Wall -Wno-unused-function
        -fsanitize=address,undefined -fno-sanitize-recover=all -I$b/inc -I$b"
# shellcheck disable=SC2086
gcc $cflags -o "$b/sim" "$here/sim.c" "$b/font_8x16.c" "$b/font_ter16x32.c" \
    "$b/logo_linux_mono.c"

for size in "$@"; do
    wh=${size%%:*}
    w=${wh%x*}
    h=${wh#*x}
    case $size in
        *:nologo) "$b/sim" "$w" "$h" "$out/$wh-nologo.ppm" nologo "$description" ;;
        *) "$b/sim" "$w" "$h" "$out/$wh.ppm" logo "$description" ;;
    esac
done
echo "screens in $out"
