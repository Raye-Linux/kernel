#!/usr/bin/env python3
# The XanMod LTS tracker: what it selects, and what it refuses.
#
#   python3 -m pytest tests/test_xanmod_lts.py
#
# This needs nothing: no kernel source, no network, no build.
#
# Why these three properties and not others. The owner asked for the
# XanMod LTS patches on top of Ubuntu's kernel, updating by themselves. The
# two ways that goes wrong in silence are both frozen here:
#
#   - the series is picked WRONG. XanMod's LTS branch applies a patch,
#     reverts it, and applies it again later under another name
#     ([v6.18.33+]). Measured on 6.18.60-xanmod1: BBRv3 appears three
#     times and is reverted twice. Take the commits naively and the series
#     carries a patch and its own revert, or the stale copy of one -- and
#     a kernel built from that compiles, boots, and misbehaves.
#   - a patch XanMod ADDED since the last review slips in unseen. That is
#     the whole point of an automatic chain, and the whole risk of one:
#     an unreviewed kernel patch must stop the build, not ride along.
#
# The third is the plain bug class: a revert whose target is not in the
# series means the selection has lost track, so it raises instead of
# quietly dropping a line.

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

# A plain import, never pytest.importorskip. The module is IN this
# repository: if it is missing these tests must go red, not skip. This repo
# has already paid for that silence once -- nine correct tests skipping on
# every run inside a green suite, for months (see the README).
import xanmod_lts  # noqa: E402

MANIFESTE = os.path.join(REPO, "xanmod", "manifest.txt")

# A cut of the real branch, 6.18.60-xanmod1, newest first -- exactly the
# shape of `git log --first-parent --no-merges`. It holds all three traps:
# a version bump, a CI commit, and BBRv3 applied/reverted/re-applied.
BRANCHE = [
    ("7d1d067054", "Alexandre Frade", "Linux 6.18.60-xanmod1"),
    ("b1dc0d8922", "Oleksandr Natalenko",
     "tcp_bbr: v3: update TCP 'bbr' congestion control module to BBRv3 [v6.18.33+]"),
    ("ac95f57c40", "Alexandre Frade",
     'Revert "tcp_bbr: v3: update TCP \'bbr\' congestion control module to BBRv3 [v6.18.14+]"'),
    ("4f4158992d", "Oleksandr Natalenko",
     "tcp_bbr: v3: update TCP 'bbr' congestion control module to BBRv3 [v6.18.14+]"),
    ("b08c1bc8e6", "Alexandre Frade", "XANMOD: .gitlab-ci: Add x64v1 build job"),
    ("69f71f8196", "Alexandre Frade",
     'Revert "tcp_bbr: v3: update TCP \'bbr\' congestion control module to BBRv3"'),
    ("eb57a72edc", "Oleksandr Natalenko",
     "tcp_bbr: v3: update TCP 'bbr' congestion control module to BBRv3"),
    ("e9b99b14be", "Alexandre Frade", "Linux 6.18.0-xanmod1"),
    ("0404c989ab", "Arjan van de Ven", "locking: rwsem: spin faster"),
    ("7d0a66e4bb", "Linus Torvalds", "Linux 6.18"),
    ("19eef1d98e", "David Howells", "afs: Fix uninit var in afs_alloc_anon_key()"),
]


def test_la_serie_s_arrete_a_la_version_amont():
    """Beyond `Linux 6.18` the commits are upstream's, not XanMod's. A walk
    that does not stop there carries thousands of upstream commits -- 12849
    measured on a shallow clone, where reachability cannot be trusted."""
    serie = xanmod_lts.serie_vivante(BRANCHE)
    sujets = [s for _, _, s in serie]
    assert "afs: Fix uninit var in afs_alloc_anon_key()" not in sujets
    assert "Linux 6.18" not in sujets


def test_une_rustine_annulee_puis_reappliquee_ne_sort_qu_une_fois():
    """BBRv3: applied, reverted, applied, reverted, applied. Exactly one
    copy survives, and it is the newest -- the one the branch tip holds."""
    serie = xanmod_lts.serie_vivante(BRANCHE)
    bbr = [s for _, _, s in serie if "BBRv3" in s]
    assert bbr == [
        "tcp_bbr: v3: update TCP 'bbr' congestion control module to BBRv3"
        " [v6.18.33+]"], bbr


def test_ni_montee_de_version_ni_integration_continue():
    serie = xanmod_lts.serie_vivante(BRANCHE)
    sujets = [s for _, _, s in serie]
    assert not [s for s in sujets if s.startswith("Linux 6.18")]
    assert not [s for s in sujets if ".gitlab-ci" in s]
    # what is left is the real series, oldest first
    assert sujets == ["locking: rwsem: spin faster",
                      "tcp_bbr: v3: update TCP 'bbr' congestion control"
                      " module to BBRv3 [v6.18.33+]"], sujets


def test_une_annulation_sans_cible_leve():
    """A revert whose target is not in the series means the selection has
    lost track of the branch. Dropping that line would hand back a series
    that looks plausible and is not the branch tip."""
    branche = [("aaaaaaaaaa", "A Frade", 'Revert "something never applied"'),
               ("7d0a66e4bb", "Linus Torvalds", "Linux 6.18")]
    with pytest.raises(xanmod_lts.SerieIncoherente) as e:
        xanmod_lts.serie_vivante(branche)
    assert "something never applied" in str(e.value)


def test_le_manifeste_couvre_toute_la_serie_mesuree():
    """Every patch of the measured series has a recorded verdict. This is
    the file the chain reads before it builds."""
    manifeste = xanmod_lts.lire_manifeste(MANIFESTE)
    assert len(manifeste) >= 49, len(manifeste)
    for sujet, verdict in manifeste.items():
        assert verdict in xanmod_lts.VERDICTS, (sujet, verdict)


def test_une_rustine_inconnue_du_manifeste_fait_refuser():
    """🚨 The central guard. XanMod adds a patch; nobody looked at it; the
    chain must stop and name it. A chain that degrades in silence is worse
    than no chain: it ships a kernel nobody reviewed."""
    manifeste = xanmod_lts.lire_manifeste(MANIFESTE)
    serie = [("ffffffffff", "Quelqu un", "XANMOD: une rustine toute neuve")]
    manquantes = xanmod_lts.rustines_non_revues(serie, manifeste)
    assert manquantes == ["XANMOD: une rustine toute neuve"]
    with pytest.raises(xanmod_lts.RevueManquante) as e:
        xanmod_lts.exiger_serie_revue(serie, manifeste)
    assert "une rustine toute neuve" in str(e.value)


def test_une_serie_deja_revue_ne_fait_pas_refuser():
    """And the guard must not cry on the series it already knows, or it
    would be turned off within a week."""
    manifeste = xanmod_lts.lire_manifeste(MANIFESTE)
    serie = [("0404c989ab", "Arjan van de Ven", "locking: rwsem: spin faster")]
    assert xanmod_lts.rustines_non_revues(serie, manifeste) == []
    xanmod_lts.exiger_serie_revue(serie, manifeste)


def test_une_serie_amputee_fait_refuser():
    """A patch that does not apply is not applied approximately. Half a
    kernel patch builds, boots, and behaves badly under load, and nothing
    says so -- so the only safe answer is to refuse the build."""
    resultats = [("0001-quelque-chose.patch", 0),
                 ("0002-autre-chose.patch", 1)]
    with pytest.raises(xanmod_lts.SerieNonApplicable) as e:
        xanmod_lts.exiger_serie_applicable(resultats)
    assert "0002-autre-chose.patch" in str(e.value)
    xanmod_lts.exiger_serie_applicable([("0001-quelque-chose.patch", 0)])


def test_le_script_dit_en_une_ligne_ce_qu_il_faut_lancer():
    """Like fetch-sources.sh --have: the remedy comes from the side that
    knows it, so iso/tools/raye-tests can lift the line into its report
    instead of carrying a copy that goes stale."""
    p = subprocess.run([sys.executable, os.path.join(REPO, "xanmod_lts.py"),
                        "--have"], capture_output=True, text=True, cwd=REPO)
    assert p.returncode in (0, 1)
    if p.returncode:
        assert "xanmod_lts.py" in (p.stderr + p.stdout)
        assert len((p.stderr + p.stdout).strip().splitlines()) == 1
