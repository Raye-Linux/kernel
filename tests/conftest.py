"""Where the kernel source the tests read comes from.

RAYE_KERNEL_TREE if it is set; otherwise ~/.cache/raye/kernel-src,
where
./fetch-sources.sh puts it, so that fetching once is enough and every
later run -- including iso/tools/raye-tests -- picks it up by itself.

⚠️ It counts only when it carries the stamp fetch-sources.sh
writes. A half-copied directory would otherwise be taken for a source
tree, and the test that needed the missing file would fail somewhere
else entirely.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# NOT inside the repository: /srv is a virtiofs share and a file written
# there from the build VM is born root:root, while the services that
# read /srv run as uid 1000.
_cache = os.environ.get("XDG_CACHE_HOME") or (
    os.path.join(os.environ["HOME"], ".cache") if os.environ.get("HOME")
    else "/var/tmp/raye-src")
DEFAULT = Path(_cache) / "raye" / "kernel-src"

HOW = ("no kernel source. ./fetch-sources.sh <ubuntu version> fetches the"
       " eleven files these tests read (~230 kB, no build); or point"
       " RAYE_KERNEL_TREE at a linux source you have")


def kernel_tree():
    """The source to read, or None -- then HOW says how to get one."""
    env = os.environ.get("RAYE_KERNEL_TREE")
    if env:
        return env
    if (DEFAULT / ".raye-kernel-source").is_file():
        return str(DEFAULT)
    return None
