#!/bin/sh
# Builds linux-image-<version>-raye: Ubuntu's kernel, same version and
# same configuration, with the Raye crash screen and the BORE scheduler,
# built with Clang and LLD (ThinLTO). Signed with the Raye MOK key so it
# boots with Secure Boot once that key is enrolled.
#
# Runs as root in a resolute system (a chroot is fine) with deb-src:
#
#   KEYS=/var/lib/raye-release ./build.sh 7.0.0-43.43
#
# KEYS holds two key pairs (never in this repository):
#   raye-mok.key/.pem    signs the modules, built into the kernel
#   raye-boot.key/.pem   signs the kernel image; this is the one enrolled
#                        in MokManager. It must not carry the module-only
#                        key usage (1.3.6.1.4.1.2312.16.1.2): shim refuses
#                        such a key for kernels.
#
# For test builds, never for the release:
#   EXTRA_PATCHES="a.patch b.patch"  applied after patches/*.patch
#   EXTRA_CONFIG="x.config"          config fragments merged after raye.config
#   FLAVOUR=name                     version suffix, linux-image-<v>-<name>
#                                    (default raye; lower case and digits)
# Paths in the two lists are separated by spaces.
#
# REV is the Raye build of a given Ubuntu version, the N in +rayeN. Raise
# it when the kernel changes on the same Ubuntu version, or apt sees
# nothing new to install. 1 was the GCC build without BORE, 3 the first
# with the AMD RGBA8888 fix (raye-base's raye-amd-cursor knows that number).
#
# Output: ./out/*.deb

set -eu
here=$(cd "$(dirname "$0")" && pwd)
version=${1:?"usage: build.sh <ubuntu kernel version, e.g. 7.0.0-43.43>"}
keys=${KEYS:?"KEYS: folder with the raye-mok and raye-boot key pairs"}
jobs=${JOBS:-$(nproc)}
work=${WORK:-$here/work}
flavour=${FLAVOUR:-raye}
rev=${REV:-3}
out=$here/out
abi=${version%.*}                 # 7.0.0-42
picture=$here/assets/raye-crash.pbm
# where the picture goes in the source tree; Kconfig paths are relative to it
logo_file=drivers/video/logo/logo_raye_crash_mono.pbm

say() { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
die() { echo "build.sh: $*" >&2; exit 1; }
# the clang-<n> a source package builds with, one number per line
clang_of() { sed -n 's/.*[ ,]clang-\([0-9][0-9]*\):native.*/\1/p' "$1" | sort -u; }

case $version in
    *[!0-9a-z.+~-]*|'') die "odd version: $version" ;;
esac
case $flavour in
    *[!a-z0-9]*|'') die "FLAVOUR: lower case letters and digits only" ;;
esac
case $rev in
    *[!0-9]*|'') die "REV: a number" ;;
esac
[ -r "$keys/raye-mok.key" ] && [ -r "$keys/raye-mok.pem" ] &&
    [ -r "$keys/raye-boot.key" ] && [ -r "$keys/raye-boot.pem" ] ||
    die "missing key files in $keys"

# absolute paths of a space-separated list, each one a readable file
files() {
    set -f
    for f in $1; do
        [ -f "$f" ] && [ -r "$f" ] || die "not a readable file: $f"
        printf '%s\n' "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
    done
    set +f
}
extra_patches=$(files "${EXTRA_PATCHES:-}")
extra_config=$(files "${EXTRA_CONFIG:-}")

# the kernel's logo tool reads plain PBM only
[ "$(head -c 2 "$picture")" = P1 ] || die "$picture is not a plain PBM (run art/crash.py)"

say "Getting Ubuntu's kernel source $version and its build tools"
mkdir -p "$work" "$out"
cd "$work"
# the exact compilers Ubuntu built it with, Rust and bindgen included
DEBIAN_FRONTEND=noninteractive apt-get build-dep -y -q "linux=$version" >/dev/null

patches=$(ls "$here"/patches/*.patch; [ -z "$extra_patches" ] || printf '%s\n' "$extra_patches")
# a tree of another version, patched with another set (an experiment), or
# left half patched by a run that stopped on a patch, is unpacked again
src=linux-${abi%-*}
# both 7.0.0-42.42 and 7.0.0-43.43 unpack to linux-7.0.0: the version is
# part of what the tree records, or a newer build quietly reuses an old source
want=$( { echo "linux $version"; printf '%s\n' "$patches" | while read -r p; do sha256sum "$p"; done; } )
if [ -d "$src" ] && [ -f "$src/.raye-patching" ]; then
    say "Unpacking the source again: a patch run stopped half way"
    rm -rf "$src"
elif [ -d "$src" ] && [ "$(cat "$src/.raye-patches" 2>/dev/null)" != "$want" ]; then
    say "Unpacking the source again: it is another version, or another set of patches"
    rm -rf "$src"
fi
[ -d "$src" ] || apt-get source -q "linux=$version"
[ -d "$src" ] || die "no $src after apt-get source"
cd "$src"

if [ ! -f .raye-patches ]; then
    say "Applying the Raye patches"
    # --fuzz=0: a hunk goes where its context says, or not at all. Without it
    # patch puts the code about the right place and exits 0 without a word; a
    # fuzzy hunk is how a change lands twice, or in the wrong function, and
    # nothing says so until the compiler or the running kernel does.
    # --forward: a patch already in the tree is refused instead of being
    # applied backwards. The source comes straight out of apt-get source, so
    # "already applied" is not a normal case: it means the change reached
    # Ubuntu and the patch has to go, which is a decision, not something to
    # work around. Either way the build stops and names the patch.
    # The marker is what makes the next run unpack the source again instead of
    # patching a tree that already holds the first half of the series.
    : > .raye-patching
    IFS='
'
    set -f
    for p in $patches; do
        echo "  $(basename "$p")"
        patch -p1 --fuzz=0 --forward --batch < "$p" ||
            die "$(basename "$p") does not apply to $version: it needs fuzz, or it is already in the tree"
    done
    set +f
    unset IFS
    printf '%s\n' "$want" > .raye-patches
    rm -f .raye-patching
fi

# the crash screen picture, as the mono logo
cp "$picture" "$logo_file"

# Clang, LLD and the LLVM tools, all of the version Ubuntu's own source
# already uses for its Rust bindings. LLVM=-<n> goes on every make: a
# make without it would quietly configure, or build, with GCC.
# Read from the .dsc: bindeb-pkg writes its own debian/control over
# Ubuntu's, so in a tree built once that file no longer says.
dsc=$work/linux_$version.dsc
clang=$(clang_of "$dsc")
case $clang in
    *[!0-9]*|'') die "cannot tell which clang $dsc asks for: '$clang'" ;;
esac
# sbsign is not a build dependency of the source: it signs the image below
DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
    "clang-$clang" "lld-$clang" "llvm-$clang" sbsigntool >/dev/null
llvm=LLVM=-$clang

say "Configuration: Ubuntu generic + Raye"
apt-get download -q "linux-modules-$abi-generic"
dpkg-deb --fsys-tarfile linux-modules-"$abi"-generic_*.deb |
    tar -xO "./boot/config-$abi-generic" > .config
rm -f linux-modules-"$abi"-generic_*.deb
# the Raye key signs the modules and is trusted next to Ubuntu's
cp "$keys/raye-mok.pem" certs/raye-mok.pem
cat "$keys/raye-mok.key" "$keys/raye-mok.pem" > certs/raye-signing.pem
chmod 600 certs/raye-signing.pem
# shellcheck disable=SC2086
scripts/kconfig/merge_config.sh -m .config "$here/config/raye.config" $extra_config
scripts/config --set-str MODULE_SIG_KEY certs/raye-signing.pem \
               --set-str SYSTEM_TRUSTED_KEYS certs/raye-mok.pem \
               --set-str SYSTEM_REVOCATION_KEYS "" \
               --set-str LOGO_LINUX_MONO_FILE "$logo_file"
make -s "$llvm" olddefconfig

# olddefconfig drops an option whose dependencies are missing, quietly;
# check every option the fragments set (the last fragment wins)
# shellcheck disable=SC2086
missing=$(cat "$here/config/raye.config" $extra_config | awk '
    /^CONFIG_[A-Za-z0-9_]+=/ { n = $0; sub(/=.*/, "", n); w[n] = $0; next }
    /^# CONFIG_[A-Za-z0-9_]+ is not set/ { w[$2] = $0 }
    END { for (n in w) print w[n] }' | while IFS= read -r line; do
    case $line in
        CONFIG_*=*)
            grep -qxF -- "$line" .config || echo "$line" ;;
        "# CONFIG_"*" is not set")
            opt=${line#\# }; opt=${opt%% *}
            ! grep -q "^$opt=" .config || echo "$line" ;;
    esac
done)
grep -qxF "CONFIG_LOGO_LINUX_MONO_FILE=\"$logo_file\"" .config ||
    missing="$missing CONFIG_LOGO_LINUX_MONO_FILE"
[ -z "$missing" ] || die "the configuration did not take: $missing"

say "Building (this takes a while)"
rm -f "$work"/linux-image-*-"$flavour"_*.deb "$work"/linux-image-*-"$flavour"-dbg_*.deb \
      "$work"/linux-headers-*-"$flavour"_*.deb
# HAVE_XXHASH=n: objtool builds its livepatch commands when libxxhash-dev
# happens to be installed, and Ubuntu's klp-checksum.c does not compile
# then (it is not in the source's build-depends); nothing here needs them
make -s -j"$jobs" "$llvm" HAVE_XXHASH=n bindeb-pkg LOCALVERSION="-$flavour" KDEB_PKGVERSION="$version+$flavour$rev"

# what /proc/version will say; the .config could read Clang while the
# objects came from GCC if LLVM= got lost on the way to debian/rules
compiler=$(sed -n 's/^#define LINUX_COMPILER[[:space:]]*"\(.*\)"$/\1/p' include/generated/compile.h)
case $compiler in
    *"clang version $clang."*LLD*) say "Built with $compiler" ;;
    *) die "not built with clang $clang and LLD: '$compiler'" ;;
esac

say "Signing the kernel and its modules for Secure Boot"
# Ubuntu's modules_install signs a module only if debian/scripts/sign-module
# says yes, and bindeb-pkg starts from an empty debian/, so the modules come
# out unsigned: sign them here. Unsigned, Secure Boot refuses them (dm-crypt
# first, so an encrypted disk never opens).
tree=$work/$src
hash=$(sed -n 's/^CONFIG_MODULE_SIG_HASH="\(.*\)"$/\1/p' "$tree/.config")
[ -n "$hash" ] || die "no CONFIG_MODULE_SIG_HASH in .config"
cd "$work"
for deb in linux-image-*-"$flavour"_*.deb; do
    case "$deb" in *dbg*) continue ;; esac
    rm -rf pkg && mkdir pkg
    dpkg-deb -R "$deb" pkg
    find pkg/lib/modules -name '*.ko' | while read -r m; do
        tail -c 28 "$m" | grep -q 'Module signature appended' ||
            "$tree/scripts/sign-file" "$hash" "$tree/certs/raye-signing.pem" \
                "$tree/certs/signing_key.x509" "$m"
    done
    unsigned=$(find pkg/lib/modules -name '*.ko' | while read -r m; do
        tail -c 28 "$m" | grep -q 'Module signature appended' || echo "$m"
    done | wc -l)
    [ "$unsigned" -eq 0 ] || die "$unsigned modules are not signed"
    # compressed after signing, as Ubuntu ships them: a third of the space
    find pkg/lib/modules -name '*.ko' -print0 | xargs -0 -P "$jobs" -n 64 zstd -q -19 --rm
    # modules.dep still names the .ko files
    for m in pkg/lib/modules/*; do depmod -b pkg "${m##*/}"; done
    for k in pkg/boot/vmlinuz-*; do
        sbsign --key "$keys/raye-boot.key" --cert "$keys/raye-boot.pem" --output "$k.signed" "$k"
        mv "$k.signed" "$k"
    done
    # what changed above (signatures, compression) must show in the package
    (cd pkg && find . -path ./DEBIAN -prune -o -type f -printf '%P\0' |
        sort -z | xargs -0 md5sum) > pkg/DEBIAN/md5sums
    size=$(du -sk --exclude=DEBIAN pkg | cut -f1)
    sed -i "s/^Installed-Size: .*/Installed-Size: $size/" pkg/DEBIAN/control
    dpkg-deb -b pkg "$out/$deb" >/dev/null
done
cp linux-headers-*-"$flavour"_*.deb "$out/" 2>/dev/null || true
rm -rf pkg
say "Done:"
ls -l "$out"
