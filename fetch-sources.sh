#!/bin/sh
# Get the few kernel files tests/ reads, WITHOUT a kernel source tree.
#
#   ./fetch-sources.sh --list                 what the tests read, one per line
#   ./fetch-sources.sh --have                 exit 0 when they are fetched
#   ./fetch-sources.sh 7.0.0-42.42            fetch them at that Ubuntu tag
#   ./fetch-sources.sh --from /path/to/linux  copy them from a tree you have
#   ./fetch-sources.sh --into DIR             where to put them
#                                             (default ~/.cache/raye/kernel-src)
#
# Then:
#   RAYE_KERNEL_TREE=<dir> python3 -m pytest tests/
#
# Why this exists. Nine tests here read the kernel source, and their
# gate asked for "a linux source" -- a 1.5 GB tree, a 230 MB download and
# a resolute machine with deb-src. Nobody pays that to read a patch, so
# the nine skipped on every run, inside a green suite, for months.
#
# They do not need a tree. Measured: between them they read ELEVEN files,
# about 230 kB. That is the whole requirement, and it fits in a curl.
#
# The list is DERIVED, never written down here: from the "+++ b/" lines
# of patches/*.patch (minus the files a patch creates, which do not exist
# upstream) and from the $tree/... paths of tests/panic-sim/run.sh. A list
# typed into this script would go stale the first time a patch touched a
# new file, and the tree would be quietly incomplete.
# tests/test_fetch_sources.py checks the derivation against both sources.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
from=
# NOT inside the repository. /srv is a virtiofs share and a file written
# there from the build VM is born root:root, while the services that
# read /srv run as uid 1000. The desktop repo has a test that fails on
# anything landing in work/ for exactly this reason.
cache=${XDG_CACHE_HOME:-${HOME:+$HOME/.cache}}
into=${cache:-/var/tmp/raye-src}/raye/kernel-src
version=
GIT=${RAYE_KERNEL_GIT:-https://git.launchpad.net/~ubuntu-kernel/ubuntu/+source/linux/+git/resolute/plain}

die() { echo "$0: $*" >&2; exit 1; }
say() { printf '==> %s\n' "$*"; }

# The files the tests read. Derived, see the note above.
wanted_files() {
    # patches: every "+++ b/F" whose "--- " line is not /dev/null
    awk '
        /^--- / { new = ($2 == "/dev/null") }
        /^\+\+\+ b\// { sub(/^\+\+\+ b\//, ""); sub(/\t.*/, ""); if (!new) print }
    ' "$here"/patches/*.patch
    # panic-sim: the paths it copies out of the tree
    grep -oE '\$tree/[A-Za-z0-9_/.+-]+' "$here/tests/panic-sim/run.sh" |
        sed 's|^\$tree/||'
}

list() { wanted_files | sed 's/[[:space:]]*$//' | sort -u; }

while [ $# -gt 0 ]; do
    case $1 in
    --list) list; exit 0 ;;
    # For iso/tools/raye-tests: exit 0 when the files are there, and
    # otherwise say in ONE line what to run. The launcher lifts that line
    # into its report, so the remedy comes from the side that knows it
    # instead of being typed into the suite table and left to go stale.
    --have)
        if [ -f "${into}/.raye-kernel-source" ]; then
            exit 0
        fi
        echo "nine tests read the kernel source: kernel/fetch-sources.sh" \
             "<ubuntu version> fetches the eleven files they need (~230 kB," \
             "no build)" >&2
        exit 1 ;;
    --from) from=${2:?--from needs a directory}; shift 2 ;;
    --into) into=${2:?--into needs a directory}; shift 2 ;;
    --help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) version=$1; shift ;;
    esac
done

[ -n "$from" ] || [ -n "$version" ] ||
    die "give the Ubuntu kernel version build.sh builds (e.g. 7.0.0-42.42),
    or --from a source tree you already have. --list says what is read."

if [ -n "$version" ]; then stamp_want=Ubuntu-$version; else stamp_want=from:$from; fi
mkdir -p "$into"
into=$(cd "$into" && pwd)
stamp=$into/.raye-kernel-source

# A tree fetched for ANOTHER version is the one trap that matters here:
# the patches would apply, or not, against the wrong kernel, and the run
# would be green for the wrong reason. The stamp is checked, not trusted.
if [ -f "$stamp" ] && [ "$(cat "$stamp")" != "$stamp_want" ]; then
    say "the tree in $into is $(cat "$stamp"), emptying it for $stamp_want"
    find "$into" -mindepth 1 -depth -delete
fi

files=$(list)
[ -n "$files" ] || die "derived no file to fetch; patches/ or tests/panic-sim/run.sh moved"

if [ -n "$from" ]; then
    from=$(cd "$from" && pwd)
    say "copying $(printf '%s\n' "$files" | wc -l) files out of $from"
    printf '%s\n' "$files" | while read -r f; do
        [ -f "$from/$f" ] || die "$from has no $f -- is it a linux source tree?"
        mkdir -p "$into/$(dirname "$f")"
        cp "$from/$f" "$into/$f"
    done
else
    command -v curl >/dev/null || die "curl is missing"
    say "fetching $(printf '%s\n' "$files" | wc -l) files at tag Ubuntu-$version"
    printf '%s\n' "$files" | while read -r f; do
        mkdir -p "$into/$(dirname "$f")"
        # --fail: a 404 must stop the run. A missing file would otherwise be
        # an empty one, and an empty drm_panic.c fails much later, elsewhere.
        curl -fsS --retry 3 --retry-delay 2 \
             -o "$into/$f" "$GIT/$f?h=Ubuntu-$version" ||
            die "cannot fetch $f at tag Ubuntu-$version.
    Is that the version build.sh builds? $GIT
    (RAYE_KERNEL_GIT points elsewhere; --from uses a tree you have.)"
        [ -s "$into/$f" ] || die "$f came back empty"
        printf '    %s\n' "$f"
    done
fi

printf '%s\n' "$stamp_want" > "$stamp"

cat <<MSG

$(printf '%s\n' "$files" | wc -l) files in $into ($stamp_want). Now:

    RAYE_KERNEL_TREE=$into python3 -m pytest tests/
MSG
