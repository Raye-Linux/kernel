#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""The XanMod LTS tracker: select the series, and refuse rather than degrade.

Raye's kernel stays Ubuntu's -- `build.sh` keeps fetching
`apt-get source linux=<version>`. What this file tracks is XanMod's LTS
*series*, so the patches Raye carries on top can follow it without anyone
watching, and so the day XanMod adds a patch the chain stops instead of
shipping a kernel nobody read.

    ./xanmod_lts.py --have              exit 0 when the manifest is usable
    ./xanmod_lts.py tag                 the newest XanMod LTS tag (network)
    ./xanmod_lts.py ubuntu              the newest Ubuntu kernel (network)
    ./xanmod_lts.py series TAG --into D extract the live series as patches
    ./xanmod_lts.py review TAG          what changed since the manifest
    ./xanmod_lts.py check TAG --tree T  apply-test the series on a tree

🚨 THE TWO SILENCES THIS FILE EXISTS FOR.

1. Picking the series wrong. XanMod's LTS branch is not a tidy list: it
   merges every upstream release, and it applies a patch, reverts it, and
   applies it again later under another name. Measured on `6.18.60-xanmod1`
   (2026-11-06): 115 commits since `Linux 6.18`, of which 66 are version
   bumps, CI commits, reverts or the commits those reverts cancel. BBRv3
   alone appears three times and is reverted twice. Take the commits
   naively and the series carries both a patch and its own revert, or a
   stale copy of one. That builds, boots, and misbehaves.

   ⚠️ And reachability cannot be used to find the series either: a shallow
   clone grafts the history, so `git log <upstream>..<tip>` answered 12849
   commits where the real number is 115. The branch has to be walked by
   FIRST PARENT, stopping at the upstream release it was forked from.

2. A patch nobody reviewed riding along. That is the whole point of an
   automatic chain and the whole risk of one. `xanmod/manifest.txt` records
   a measured verdict per patch; a patch absent from it stops the chain,
   by name.

🚨 WHAT THIS FILE DELIBERATELY DOES NOT DO. It never applies a patch with
fuzz, never drops a hunk to make one fit, and never builds a kernel from a
series that did not apply whole. Half a kernel patch is the worst case
there is, because nothing reports it. And it does not publish: signing a
release is the owner's, with the owner's key.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFESTE = os.path.join(HERE, "xanmod", "manifest.txt")

DEPOT = os.environ.get("RAYE_XANMOD_GIT", "https://gitlab.com/xanmod/linux.git")
# XanMod has no branch called "lts": the LTS line is whichever upstream
# longterm release they carry, and their Debian package names it. Read from
# the EPYC host on 2026-11-06: linux-xanmod-lts-x64v3 = 6.18.60-xanmod1.
LIGNE_LTS = os.environ.get("RAYE_XANMOD_LTS_LINE", "6.18")

VERDICTS = frozenset({"applique", "deja-en-amont", "conflit"})

# A XanMod version bump, e.g. "Linux 6.18.60-xanmod1": not a kernel change.
_MONTEE = re.compile(r"Linux \d+\.\d+(?:\.\d+)?-xanmod\d+")
# The upstream release the branch was forked from, e.g. "Linux 6.18". The
# fullmatch is what keeps it from catching "Linux 6.18.60-xanmod1" or
# "Linux 6.18-rc7".
_AMONT = re.compile(r"Linux \d+\.\d+")
_ANNULATION = re.compile(r'Revert "(.*)"', re.DOTALL)
# XanMod re-applies a patch under the same subject plus the release it was
# rebased for: "... BBRv3 [v6.18.33+]". Two subjects that differ only by
# that suffix are the same patch.
_SUFFIXE_VERSION = re.compile(r"\s*\[v[\d.]+\+\]$")


class SerieIncoherente(Exception):
    """The branch walk lost track: a revert with no patch to cancel."""


class RevueManquante(Exception):
    """The series holds a patch that has no recorded verdict."""


class SerieNonApplicable(Exception):
    """A patch of the series did not apply. The build does not happen."""


def sujet_nu(sujet: str) -> str:
    """The subject without the `[vX.Y.Z+]` XanMod adds when it re-applies."""
    return _SUFFIXE_VERSION.sub("", sujet).strip()


def serie_vivante(
    commits: list[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    """XanMod's own patches, oldest first, reverts resolved.

    `commits` is the branch walked by first parent, newest first, with the
    merges left out -- exactly what
    `git log --first-parent --no-merges --format='%h|%an|%s'` prints.

    Dropped: the version bumps, the CI commits, and every revert together
    with the commit it cancels. Kept, in application order, is what the
    branch tip actually holds.
    """
    serie: list[tuple[str, str, str]] = []
    for sha, auteur, sujet in commits:
        if _AMONT.fullmatch(sujet):
            break                                   # upstream starts here
        serie.append((sha, auteur, sujet))
    serie.reverse()                                 # chronological

    vivants: list[tuple[str, str, str]] = []
    for sha, auteur, sujet in serie:
        if _MONTEE.fullmatch(sujet) or ".gitlab-ci" in sujet:
            continue
        annulation = _ANNULATION.fullmatch(sujet)
        if annulation:
            cible = sujet_nu(annulation.group(1))
            for i in range(len(vivants) - 1, -1, -1):
                if sujet_nu(vivants[i][2]) == cible:
                    del vivants[i]
                    break
            else:
                # Not droppable. A revert with nothing to cancel means the
                # walk is not the branch: dropping the line would hand back a
                # plausible series that is not the one XanMod ships.
                raise SerieIncoherente(
                    f"{sha} reverts {annulation.group(1)!r}, which is not in"
                    " the series. The branch walk is wrong -- check that it"
                    " follows first parents and stops at the upstream"
                    " release.")
            continue
        vivants.append((sha, auteur, sujet))
    return vivants


def lire_manifeste(chemin: str = MANIFESTE) -> dict[str, str]:
    """subject (without the version suffix) -> measured verdict."""
    manifeste: dict[str, str] = {}
    with open(chemin, encoding="utf-8") as f:
        for n, ligne in enumerate(f, 1):
            ligne = ligne.rstrip("\n")
            if not ligne or ligne.startswith("#"):
                continue
            verdict, _, sujet = ligne.partition("|")
            verdict, sujet = verdict.strip(), sujet.strip()
            if verdict not in VERDICTS:
                raise ValueError(
                    f"{chemin}:{n}: verdict {verdict!r} inconnu; attendus:"
                    f" {', '.join(sorted(VERDICTS))}")
            if not sujet:
                raise ValueError(f"{chemin}:{n}: ligne sans sujet")
            manifeste[sujet_nu(sujet)] = verdict
    return manifeste


def rustines_non_revues(
    serie: list[tuple[str, str, str]], manifeste: dict[str, str]
) -> list[str]:
    """The subjects of the series that carry no recorded verdict."""
    return [sujet for _, _, sujet in serie
            if sujet_nu(sujet) not in manifeste]


def exiger_serie_revue(
    serie: list[tuple[str, str, str]], manifeste: dict[str, str]
) -> None:
    """Stop, naming them, if the series holds an unreviewed patch."""
    manquantes = rustines_non_revues(serie, manifeste)
    if manquantes:
        raise RevueManquante(
            "XanMod LTS carries %d patch(es) with no recorded verdict, so"
            " nobody has looked at them:\n  - %s\nRead each one, add a line"
            " to xanmod/manifest.txt, and run this again. The chain does not"
            " build a kernel that holds an unreviewed patch."
            % (len(manquantes), "\n  - ".join(manquantes)))


def exiger_serie_applicable(resultats: list[tuple[str, int]]) -> None:
    """Stop, naming them, if any patch of the series failed to apply.

    🚨 This is the guard the whole chain turns on. A patch that does not
    apply is not applied approximately: `build.sh` uses `--fuzz=0
    --forward` for the same reason. A series applied in part gives a kernel
    that compiles, boots, and behaves badly under load, and nothing
    anywhere reports it.
    """
    echouees = [nom for nom, code in resultats if code != 0]
    if echouees:
        raise SerieNonApplicable(
            "%d patch(es) of the XanMod LTS series do not apply to this"
            " Ubuntu kernel:\n  - %s\nThe build does not happen. Either the"
            " patch is already upstream -- then it leaves the series, which"
            " is a decision -- or it needs a real rewrite. Nothing is forced"
            " and no hunk is dropped."
            % (len(echouees), "\n  - ".join(echouees)))


# --------------------------------------------------------------- network


def derniere_etiquette_lts(ligne: str = LIGNE_LTS, depot: str = DEPOT) -> str:
    """The newest `<ligne>.N-xanmodM` tag, read from the remote."""
    p = subprocess.run(["git", "ls-remote", "--tags", depot],
                       capture_output=True, text=True, check=True)
    motif = re.compile(rf"refs/tags/({re.escape(ligne)}\.(\d+)-xanmod(\d+))$")
    trouvees = [(int(m.group(2)), int(m.group(3)), m.group(1))
                for m in (motif.search(l) for l in p.stdout.splitlines()) if m]
    if not trouvees:
        raise SystemExit(
            f"aucune etiquette {ligne}.*-xanmod* dans {depot}. La ligne LTS"
            " a peut-etre change: RAYE_XANMOD_LTS_LINE la fixe.")
    return max(trouvees)[2]


def derniere_version_ubuntu(
    poche: str = "resolute-updates",
    miroir: str = "http://archive.ubuntu.com/ubuntu",
) -> str:
    """Ubuntu's newest `linux` source version in that pocket.

    ⚠️ The pocket matters and it is not obvious. Measured 2026-11-06:
    `resolute` holds 7.0.0-14.14, `resolute-security` 7.0.0-42.42 and
    `resolute-updates` 7.0.0-43.43. A chain that reads the release pocket
    would track a kernel months behind and never say so.
    """
    url = f"{miroir}/dists/{poche}/main/source/Sources.gz"
    brut = subprocess.run(["curl", "-fsS", url], capture_output=True,
                          check=True).stdout
    texte = subprocess.run(["zcat"], input=brut, capture_output=True,
                           check=True).stdout.decode("utf-8", "replace")
    dans_linux = False
    for ligne in texte.splitlines():
        if ligne == "Package: linux":
            dans_linux = True
        elif dans_linux and ligne.startswith("Version: "):
            return ligne.split(None, 1)[1].strip()
    raise SystemExit(f"pas de source 'linux' dans {poche}")


def _depot_local(etiquette: str, cache: str) -> str:
    """A shallow clone of that tag, deep enough to hold XanMod's series."""
    arbre = os.path.join(cache, f"xanmod-{etiquette}")
    if not os.path.isdir(os.path.join(arbre, ".git")):
        os.makedirs(cache, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", etiquette,
                        "--single-branch", DEPOT, arbre], check=True)
    # --deepen on a tag clone does nothing (measured: the clone stayed at
    # depth 1 and the walk then saw no series at all). The ref has to be named.
    subprocess.run(["git", "fetch", "--depth", "200", "origin", etiquette],
                   cwd=arbre, check=True)
    return arbre


def commits_de_la_branche(arbre: str) -> list[tuple[str, str, str]]:
    p = subprocess.run(
        ["git", "log", "--first-parent", "--no-merges", "--format=%h|%an|%s",
         "HEAD"], cwd=arbre, capture_output=True, text=True, check=True)
    commits = []
    for ligne in p.stdout.splitlines():
        sha, _, reste = ligne.partition("|")
        auteur, _, sujet = reste.partition("|")
        commits.append((sha, auteur, sujet))
    return commits


def extraire_serie(arbre: str, serie: list[tuple[str, str, str]],
                   vers: str) -> list[str]:
    """One patch file per live commit, numbered in application order."""
    os.makedirs(vers, exist_ok=True)
    for vieux in sorted(f for f in os.listdir(vers) if f.endswith(".patch")):
        os.remove(os.path.join(vers, vieux))
    for i, (sha, _, _) in enumerate(serie, 1):
        subprocess.run(
            ["git", "format-patch", "-1", "--no-signature", "--zero-commit",
             "--no-numbered", "--start-number", str(i), "-o", vers, sha],
            cwd=arbre, check=True, stdout=subprocess.DEVNULL)
    return sorted(os.path.join(vers, f) for f in os.listdir(vers)
                  if f.endswith(".patch"))


def essayer_serie(rustines: list[str], arbre: str) -> list[tuple[str, int]]:
    """Dry-run each patch on `arbre`, with build.sh's exact flags."""
    resultats = []
    for p in rustines:
        with open(p, "rb") as f:
            r = subprocess.run(
                ["patch", "-p1", "--dry-run", "--fuzz=0", "--forward",
                 "--batch"], cwd=arbre, stdin=f, capture_output=True)
        resultats.append((os.path.basename(p), r.returncode))
    return resultats


# ------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(
        description="Track XanMod's LTS series for Raye's Ubuntu-based kernel.")
    a.add_argument("--have", action="store_true",
                   help="exit 0 when the manifest is usable, else say what to run")
    a.add_argument("commande", nargs="?",
                   choices=["tag", "ubuntu", "series", "review", "check"])
    a.add_argument("etiquette", nargs="?")
    a.add_argument("--into", default=os.path.join(HERE, "xanmod", "serie"))
    a.add_argument("--tree", help="an unpatched Ubuntu kernel source")
    a.add_argument("--cache", default=os.path.join(
        os.environ.get("XDG_CACHE_HOME") or
        os.path.join(os.environ.get("HOME", "/var/tmp"), ".cache"), "raye"))
    o = a.parse_args(argv)

    # One line on failure, like fetch-sources.sh --have: the launcher
    # lifts it into its report, so the remedy comes from the side that knows
    # it instead of being typed into a table and left to go stale.
    if o.have:
        try:
            lire_manifeste()
        except (OSError, ValueError) as e:
            print(f"xanmod_lts.py: no usable xanmod/manifest.txt ({e});"
                  " ./xanmod_lts.py review <tag> rebuilds it", file=sys.stderr)
            return 1
        return 0

    if not o.commande:
        a.print_help()
        return 2
    if o.commande == "tag":
        print(derniere_etiquette_lts())
        return 0
    if o.commande == "ubuntu":
        print(derniere_version_ubuntu())
        return 0

    etiquette = o.etiquette or derniere_etiquette_lts()
    arbre = _depot_local(etiquette, o.cache)
    serie = serie_vivante(commits_de_la_branche(arbre))
    print(f"{etiquette}: {len(serie)} patches in the live series")

    if o.commande == "review":
        manifeste = lire_manifeste()
        manquantes = rustines_non_revues(serie, manifeste)
        for sujet in manquantes:
            print(f"  NOT REVIEWED  {sujet}")
        connues = {sujet_nu(s) for _, _, s in serie}
        for sujet in sorted(set(manifeste) - connues):
            print(f"  GONE FROM XANMOD  {sujet}")
        exiger_serie_revue(serie, manifeste)
        print("every patch of the series has a recorded verdict")
        return 0

    rustines = extraire_serie(arbre, serie, o.into)
    print(f"{len(rustines)} patch files in {o.into}")
    if o.commande == "check":
        if not o.tree:
            raise SystemExit("check needs --tree <unpatched Ubuntu source>")
        exiger_serie_revue(serie, lire_manifeste())
        resultats = essayer_serie(rustines, o.tree)
        for nom, code in resultats:
            print(f"  {'ok  ' if code == 0 else 'FAIL'} {nom}")
        exiger_serie_applicable(resultats)
        print("the whole series applies; the build may proceed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SerieIncoherente, RevueManquante, SerieNonApplicable) as e:
        print(f"xanmod_lts.py: {e}", file=sys.stderr)
        sys.exit(1)
