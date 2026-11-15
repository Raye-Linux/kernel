#!/usr/bin/env python3
# xanmod-check: the trigger that wakes the XanMod LTS chain and makes its
# news reachable. Like test_xanmod_update.py, these tests freeze what it
# REFUSES and what it SURFACES -- never what it builds, because it builds
# nothing.
#
#   python3 -m pytest tests/test_xanmod_check.py
#
# This needs nothing: no kernel source, no network, no build, no keys. The
# chain is replaced by a stub that prints whatever the test wants.
#
# Why a bare systemd timer would NOT have been enough, and why these
# tests exist. `xanmod-lts-update.sh check` exits 0 whichever answer it
# has -- a new XanMod tag, a new Ubuntu kernel, or nothing. A timer running
# it nightly succeeds identically in all three cases, and the one line that
# matters sits in the journal. Every assertion below guards one way of
# rebuilding that silence.
import hashlib
import os
import pathlib
import stat
import subprocess

import pytest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
TRIGGER = REPO / "xanmod-check"
UNITS = REPO / "data"

BOUGE = "==> MOVED: was '6.18.59-xanmod1 7.0.0-42.42', now '6.18.60-xanmod1 7.0.0-43.43'"
CALME = "==> unchanged since the last run (6.18.60-xanmod1 7.0.0-43.43): there is nothing to do"
MANQUE = "these preconditions are not met:\n  - KEYS: /var/lib/raye-release/raye-mok.key is missing"


def stub(tmp_path, sortie, rc=0, nom="chaine.sh"):
    """A stand-in for xanmod-lts-update.sh that prints what the test wants.

    ⚠️ It records its own argv. Without that, no assertion could tell
    `check` from `apply`, and the whole point of this trigger -- that it
    never builds or signs unattended -- would be untested.
    """
    p = tmp_path / nom
    journal = tmp_path / "argv.txt"
    p.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" > {journal}\n'
        f"cat <<'EOF'\n{sortie}\nEOF\n"
        f"exit {rc}\n"
    )
    p.chmod(0o755)
    return p, journal


def run(tmp_path, chaine, **env_extra):
    annonce = tmp_path / "xanmod" / "annonce.txt"
    env = dict(os.environ)
    env["RAYE_XANMOD_CHAIN"] = str(chaine)
    env["RAYE_XANMOD_ANNONCE"] = str(annonce)
    env.pop("RAYE_NOTIFY", None)
    env.update({k: str(v) for k, v in env_extra.items()})
    done = subprocess.run(["sh", str(TRIGGER)], capture_output=True, text=True,
                          env=env, timeout=30)
    return done, annonce


# ------------------------------------------------- it never builds or signs
def test_il_lance_check_et_jamais_apply(tmp_path):
    """🚨 The single most important assertion in this file.

    An unattended `apply` is not a convenience: three of XanMod's patches
    apply cleanly while breaking module signing and the TPM sealing of the
    disk, so an unreviewed build ships a machine whose encrypted disk does
    not open. Nothing downstream would say so.
    """
    chaine, journal = stub(tmp_path, BOUGE)
    done, _ = run(tmp_path, chaine)
    assert done.returncode == 0, done.stderr
    argv = journal.read_text().split()
    assert argv == ["check"], f"the trigger called the chain with {argv!r}, not ['check']"


# ---------------------------------------------------------- the news lands
def test_un_deplacement_laisse_une_annonce_lisible(tmp_path):
    chaine, _ = stub(tmp_path, BOUGE)
    done, annonce = run(tmp_path, chaine)
    assert done.returncode == 0, done.stderr
    assert annonce.exists(), "nothing moved into the announcement, so the news is only in the journal"
    texte = annonce.read_text()
    assert "6.18.60-xanmod1" in texte and "7.0.0-43.43" in texte, (
        f"the announcement does not carry the two versions: {texte!r}")
    assert "apply" in texte, "the announcement does not say what to run next"


def test_des_prealables_non_remplis_sont_aussi_une_nouvelle(tmp_path):
    """A chain that can never build is news, not quiet.

    `check` prints its unmet preconditions and still exits 0. Missing
    signing keys mean every future kernel is already lost, months before
    anyone tries to build one.
    """
    chaine, _ = stub(tmp_path, MANQUE)
    done, annonce = run(tmp_path, chaine)
    assert done.returncode == 0, done.stderr
    assert annonce.exists(), "unmet preconditions produced no announcement at all"
    assert "raye-mok.key" in annonce.read_text()


# ------------------------------------------------- and silence stays silent
def test_rien_qui_bouge_ne_produit_aucune_annonce(tmp_path):
    chaine, _ = stub(tmp_path, CALME)
    done, annonce = run(tmp_path, chaine)
    assert done.returncode == 0, done.stderr
    assert not annonce.exists(), (
        "an unchanged run still announced something. A trigger that speaks "
        "every night is a trigger nobody reads.")


def test_une_annonce_perimee_est_effacee(tmp_path):
    """⚠️ The half that a 'does it announce?' test cannot catch.

    Without this, the first moved kernel leaves a file that tells him about
    the same version every day forever -- and the day it is stale is the
    day he stops believing it.
    """
    chaine, _ = stub(tmp_path, CALME)
    annonce = tmp_path / "xanmod" / "annonce.txt"
    annonce.parent.mkdir(parents=True, exist_ok=True)
    annonce.write_text("une vieille nouvelle, de la semaine derniere\n")
    done, _ = run(tmp_path, chaine)
    assert done.returncode == 0, done.stderr
    assert not annonce.exists(), "a stale announcement survived a quiet run"


# ------------------------------------------- a broken chain is a FAILURE
@pytest.mark.parametrize("comment", ["absente", "non-executable"])
def test_une_chaine_injoignable_fait_echouer(tmp_path, comment):
    """Not news: a failure.

    Without this the unit goes green forever on a renamed or deleted
    script, and the kernel quietly stops being followed. That is the exact
    shape of the 22 installer QML tests that no package build ever ran.
    """
    if comment == "absente":
        chaine = tmp_path / "nulle-part.sh"
    else:
        chaine, _ = stub(tmp_path, CALME)
        chaine.chmod(chaine.stat().st_mode & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH)
    done, annonce = run(tmp_path, chaine)
    assert done.returncode != 0, (
        f"a chain that is {comment} was treated as 'nothing to report': rc=0")
    assert not annonce.exists()


# --------------------------------------------------------- the notifier
def test_un_notifieur_sans_chemin_absolu_est_refuse(tmp_path):
    """⚠️ Measured in this lab, twice: systemd and ssh both run a command
    with a PATH that has no /usr/local/bin, so a bare name is simply not
    found -- and the notifier's own failure would be the silence this file
    exists to remove."""
    chaine, _ = stub(tmp_path, BOUGE)
    done, _ = run(tmp_path, chaine, RAYE_NOTIFY="lab-notify-admin")
    assert done.returncode != 0, "a bare notifier name was accepted"
    assert "absolute" in done.stderr


def test_le_notifieur_recoit_l_annonce_sur_son_entree(tmp_path):
    chaine, _ = stub(tmp_path, BOUGE)
    recu = tmp_path / "recu.txt"
    notif = tmp_path / "notifieur.sh"
    notif.write_text(f'#!/bin/sh\nprintf "sujet=%s\\n" "$1" > {recu}\ncat >> {recu}\n')
    notif.chmod(0o755)
    done, _ = run(tmp_path, chaine, RAYE_NOTIFY=str(notif))
    assert done.returncode == 0, done.stderr
    texte = recu.read_text()
    assert "sujet=" in texte and "XanMod" in texte
    assert "6.18.60-xanmod1" in texte, f"the notifier got no versions: {texte!r}"


def test_un_notifieur_en_panne_ne_passe_pas_inapercu(tmp_path):
    """The announcement is already on disk, so the news is not lost -- but
    if the one channel that reaches him is broken, the unit going red is
    the only thing left that says so."""
    chaine, _ = stub(tmp_path, BOUGE)
    notif = tmp_path / "casse.sh"
    notif.write_text("#!/bin/sh\nexit 3\n")
    notif.chmod(0o755)
    done, annonce = run(tmp_path, chaine, RAYE_NOTIFY=str(notif))
    assert done.returncode != 0, "a notifier that failed was swallowed"
    assert annonce.exists(), "the news should survive a broken notifier"


# ------------------------------------------------------------ the units
def test_les_deux_unites_existent_et_systemd_ne_s_en_plaint_pas():
    service = UNITS / "raye-xanmod-check.service"
    timer = UNITS / "raye-xanmod-check.timer"
    for u in (service, timer):
        assert u.is_file(), f"{u} is missing: nothing would ever wake the chain"
    import shutil
    if not shutil.which("systemd-analyze"):
        pytest.skip("systemd-analyze absent: the units cannot be validated here")
    done = subprocess.run(["systemd-analyze", "verify", str(service), str(timer)],
                          capture_output=True, text=True, timeout=60)
    # Not the return code: systemd-analyze exits 0 even on a unit it
    # could not parse ("Failed to parse ..., ignoring"). The output is the
    # verdict. Measured 2026-11-06.
    bruit = [l for l in done.stderr.splitlines() if "raye-xanmod-check" in l]
    assert not bruit, "systemd objects to the units:\n" + "\n".join(bruit)


def test_le_minuteur_rattrape_une_journee_manquee():
    """Without Persistent=true, a machine that was off on the day the timer
    was due simply never looks -- and a laptop is off most of the time."""
    texte = (UNITS / "raye-xanmod-check.timer").read_text()
    assert "Persistent=true" in texte
    assert "OnCalendar" in texte


def test_le_service_ne_nomme_jamais_apply():
    """🚨 Read as a string, deliberately. A unit that grew an `apply` would
    build and sign a kernel nobody reviewed, on a timer."""
    texte = (UNITS / "raye-xanmod-check.service").read_text()
    exec_lines = [l for l in texte.splitlines() if l.startswith("Exec")]
    assert exec_lines, "the service has no ExecStart at all"
    for l in exec_lines:
        assert " apply" not in l, f"the unit runs apply on a timer: {l!r}"


def test_le_declencheur_est_executable():
    assert TRIGGER.stat().st_mode & stat.S_IXUSR, f"{TRIGGER} is not executable"
    done = subprocess.run(["sh", "-n", str(TRIGGER)], capture_output=True, text=True)
    assert done.returncode == 0, f"sh refuses the trigger: {done.stderr}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
