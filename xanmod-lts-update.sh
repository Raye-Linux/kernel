#!/bin/sh
# Replay XanMod's LTS series on each new Ubuntu kernel, without anyone
# watching -- and stop, loudly, the moment that would mean shipping
# something nobody read.
#
#   ./xanmod-lts-update.sh            check (the DEFAULT): says what moved,
#                                     builds NOTHING
#   ./xanmod-lts-update.sh apply      the whole chain, as far as a built and
#                                     tested package, then stops
#
# Raye's kernel is Ubuntu's. What follows XanMod is the SERIES, their LTS
# patches on top, the way patches/0001 and 0002 already are. docs/xanmod-lts.md
# is the measurement behind that; xanmod/manifest.txt is the reviewed verdict
# per patch, and this script refuses to build without it.
#
# check IS THE DEFAULT, and that is not a style choice. The thing not to
# start by accident here is a kernel build: it wants tens of gigabytes and an
# hour, on a machine that is also somebody's desktop.
#
# WHERE THIS STOPS. It goes as far as a package built, signed for Secure
# Boot by build.sh, and put through the tests. It never publishes and never
# signs a release: that key is the owner's and nothing leaves without the
# owner saying so. "I want nothing to do" ends there, on purpose.
#
# AND THE FALLBACK NEVER GOES AWAY. Ubuntu's signed kernel stays the
# default in the boot menu, the Raye kernel gets one trial boot, and a disk
# the TPM opens gets a second binding. Nothing here touches the boot default
# and nothing here removes Ubuntu's kernel.
#
# Environment, all with sane defaults (the tests use them to doctor a run):
#   KEYS                   the raye-mok / raye-boot pairs, as build.sh wants
#   RAYE_CHAIN_MIN_GO      free space demanded before a build (default 50)
#   RAYE_XANMOD_MANIFEST   the reviewed verdicts (default xanmod/manifest.txt)
#   RAYE_CHAIN_OFFLINE=1   skip the two network lookups and say so
#   RAYE_CHAIN_WORK        where the build would happen (default ./work)

set -eu
here=$(cd "$(dirname "$0")" && pwd)
mode=${1:-check}
keys=${KEYS:-/var/lib/raye-release}
min_go=${RAYE_CHAIN_MIN_GO:-50}
manifeste=${RAYE_XANMOD_MANIFEST:-$here/xanmod/manifest.txt}
work=${RAYE_CHAIN_WORK:-$here/work}
etat=$here/xanmod/etat.txt

case $mode in
    check|apply) ;;
    *) echo "usage: $0 [check|apply]   (check is the default)" >&2; exit 2 ;;
esac

say() { printf '==> %s\n' "$*"; }

# Every missing precondition is named, and the refusal comes at the end.
# Stopping at the first one makes a run tell you a third of what is wrong,
# so the next run tells you another third.
manques=""
manque() { manques="$manques
  - $1"; }

say "mode: $mode (check is the default; it builds nothing)"

# ---------------------------------------------------------------- what moved
etiquette=""
version_ubuntu=""
if [ "${RAYE_CHAIN_OFFLINE:-}" = 1 ]; then
    say "offline: the XanMod tag and the Ubuntu version were not looked up"
else
    etiquette=$(python3 "$here/xanmod_lts.py" tag 2>/dev/null || true)
    version_ubuntu=$(python3 "$here/xanmod_lts.py" ubuntu 2>/dev/null || true)
    [ -n "$etiquette" ] || manque "cannot read XanMod's newest LTS tag (network?)"
    [ -n "$version_ubuntu" ] || manque "cannot read Ubuntu's newest kernel (network?)"
    say "XanMod LTS: ${etiquette:-unknown}   Ubuntu kernel: ${version_ubuntu:-unknown}"
    if [ -f "$etat" ]; then
        connu=$(cat "$etat")
        if [ "$connu" = "$etiquette $version_ubuntu" ]; then
            say "unchanged since the last run ($connu): there is nothing to do"
        else
            say "MOVED: was '$connu', now '$etiquette $version_ubuntu'"
        fi
    else
        say "no $etat yet: this is the first run"
    fi
fi

# ------------------------------------------------------------- preconditions
# The series must be reviewed patch by patch. This is the central guard: a
# patch XanMod added that nobody looked at stops the chain, by name.
if ! python3 "$here/xanmod_lts.py" --have >/dev/null 2>&1; then
    manque "no usable manifest of reviewed verdicts; ./xanmod_lts.py review <tag>"
fi
[ -r "$manifeste" ] || manque "RAYE_XANMOD_MANIFEST: cannot read $manifeste"

# The modules are signed with the Raye key. Without it the build ends with a
# kernel whose modules Secure Boot refuses -- dm-crypt first, so an encrypted
# disk never opens. That has to be refused before the hour of compiling, not
# after.
for f in raye-mok.key raye-mok.pem raye-boot.key raye-boot.pem; do
    [ -r "$keys/$f" ] || manque "KEYS: $keys/$f is missing or unreadable"
done

# A kernel build wants tens of gigabytes. Started on a disk that cannot hold
# it, it fills the disk shared with everything else and then fails in the
# middle of a link, looking like a compiler bug.
libre_go=$(df -BG --output=avail "$(dirname "$work")" 2>/dev/null |
           tail -1 | tr -dc '0-9')
libre_go=${libre_go:-0}
if [ "$libre_go" -lt "$min_go" ]; then
    manque "disk: ${libre_go} GB free where the build goes, ${min_go} GB demanded"
fi

# Ubuntu's own source and build tools, which only a resolute host has.
if [ ! -r /etc/os-release ] || ! grep -q 'VERSION_CODENAME=resolute' /etc/os-release 2>/dev/null; then
    manque "host: build.sh wants a resolute system with deb-src enabled"
fi

# -------------------------------------------------------------------- verdict
if [ -n "$manques" ]; then
    printf '\n%s\n' "these preconditions are not met:$manques"
    echo
    echo "nothing was built."
    [ "$mode" = apply ] && exit 1
    say "check only reports; run it again on a machine that meets them"
    exit 0
fi

if [ "$mode" = check ]; then
    say "every precondition is met; apply would build. nothing was built."
    exit 0
fi

# ----------------------------------------------------------------- the chain
# The order is the point. The series is proved to apply WHOLE before a
# single object file is compiled: one patch that does not apply means no
# build at all. A series applied in part gives a kernel that compiles, boots,
# and behaves badly under load, and nothing anywhere reports it.
say "proving the whole XanMod LTS series applies to linux=$version_ubuntu"
python3 "$here/xanmod_lts.py" check "$etiquette" --tree "$work/linux-${version_ubuntu%%-*}"

say "building (build.sh: Ubuntu's source, the Raye series, modules signed)"
KEYS="$keys" "$here/build.sh" "$version_ubuntu"

say "the repository's own tests"
/srv/raye/iso/tools/raye-tests --repo kernel --no-iso

say "the bench (docs/bench.md is what turns any of this into a verdict)"
echo "    run the two programs of tests/bench/ against the new kernel and"
echo "    write the numbers into docs/bench.md -- that step is a measurement,"
echo "    not something a script should claim it did."

printf '%s %s\n' "$etiquette" "$version_ubuntu" > "$etat"
cat <<MSG

An update is ready, and it stops here.

    XanMod LTS   $etiquette
    Ubuntu       $version_ubuntu
    packages     $here/out

What it changes is docs/xanmod-lts.md; the bench numbers go in
docs/bench.md. Signing and publishing the release are yours, with your
key -- this chain does not do it and is not able to.
MSG
