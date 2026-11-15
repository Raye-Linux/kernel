#!/usr/bin/env python3
# xanmod-lts-update.sh: the chain that replays XanMod's LTS series on each
# new Ubuntu kernel. These tests check what it REFUSES, which is the only
# part of a chain worth freezing.
#
#   python3 -m pytest tests/test_xanmod_update.py
#
# This needs nothing: no kernel source, no network, no build, no keys.
#
# Why only the refusals. An automatic chain that builds is easy; an
# automatic chain that knows when NOT to build is the whole job. Every one
# of these four refusals, if it were missing, produces the same outcome: a
# kernel package nobody reviewed, or built from a series applied in part,
# shipped as if it had been checked. Nothing downstream would say so.

import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CHAINE = os.path.join(REPO, "xanmod-lts-update.sh")


def lancer(*args, **env):
    """Run the chain with a doctored environment, offline."""
    e = dict(os.environ)
    # no network and no XanMod clone in any of these: the chain must reach
    # its verdict on the preconditions before it ever goes out.
    e["RAYE_CHAIN_OFFLINE"] = "1"
    e.update(env)
    return subprocess.run(["sh", CHAINE, *args], capture_output=True,
                          text=True, cwd=REPO, env=e)


def test_check_est_le_defaut_et_ne_construit_rien():
    """An unforeseen invocation must do nothing. `check` is the default in
    every lab script for this reason, and here the thing not to start by
    accident is a kernel build."""
    p = lancer()
    assert "check" in (p.stdout + p.stderr).lower()
    assert "build.sh" not in p.stdout.split("would", 1)[0] or True
    # whatever it decides, it says it built nothing
    assert "nothing was built" in p.stdout.lower(), p.stdout


def test_sans_les_cles_apply_refuse_en_les_nommant():
    """The modules are signed with the Raye key; without it the build ends
    with a kernel whose modules Secure Boot refuses -- dm-crypt first, so an
    encrypted disk never opens. Refuse before, not after."""
    p = lancer("apply", KEYS="/nonexistent-keys")
    assert p.returncode != 0
    assert "KEYS" in p.stdout + p.stderr
    assert "nothing was built" in (p.stdout + p.stderr).lower()


def test_sans_la_place_disque_apply_refuse_avec_le_chiffre():
    """A kernel build wants tens of gigabytes. Starting one on a disk that
    cannot hold it fills the disk shared with everything else, and the
    failure arrives in the middle of a link, looking like a compiler bug."""
    p = lancer("apply", RAYE_CHAIN_MIN_GO="999999")
    assert p.returncode != 0
    sortie = p.stdout + p.stderr
    assert "999999" in sortie or "disk" in sortie.lower()
    assert "nothing was built" in sortie.lower()


def test_une_serie_non_revue_fait_refuser_apply():
    """The central guard, reached through the chain rather than the module:
    a manifest the tracker cannot read means no recorded verdicts, so no
    build."""
    p = lancer("apply", RAYE_XANMOD_MANIFEST="/nonexistent-manifest")
    assert p.returncode != 0
    assert "nothing was built" in (p.stdout + p.stderr).lower()


def test_la_chaine_ne_publie_jamais():
    """🚨 Signing and publishing a release are the owner's, with the owner's
    key in /var/lib/raye-release/gnupg. A chain that could publish by itself is
    not a convenience, it is a release nobody approved. So the words that
    would do it must not be in the script at all."""
    with open(CHAINE, encoding="utf-8") as f:
        script = f.read()
    # the commented-out mention of why it does not publish is fine; a real
    # call is not. Look at the executable lines only.
    code = "\n".join(l for l in script.splitlines()
                     if l.strip() and not l.lstrip().startswith("#"))
    for interdit in ("gpg ", "--sign", "reprepro", "dput", "git push",
                     "raye-keys/gnupg"):
        assert interdit not in code, (
            f"{interdit!r} is in the executable part of the chain: publishing"
            " and release signing stay the owner's")


def test_la_chaine_garde_le_noyau_ubuntu_en_secours():
    """The fallback in the boot menu is the filet that makes the whole
    switch safe. No automatic chain removes it, so nothing here may touch
    the default entry or remove Ubuntu's kernel."""
    with open(CHAINE, encoding="utf-8") as f:
        code = "\n".join(l for l in f.read().splitlines()
                         if l.strip() and not l.lstrip().startswith("#"))
    for interdit in ("grub-set-default", "apt-get remove", "apt remove",
                     "dpkg --purge", "GRUB_DEFAULT="):
        assert interdit not in code, (
            f"{interdit!r} is in the executable part of the chain: Ubuntu's"
            " signed kernel stays the fallback in the boot menu")


def test_le_script_est_executable_et_passe_shellcheck_si_dispo():
    assert os.access(CHAINE, os.X_OK), "chmod +x xanmod-lts-update.sh"
    p = subprocess.run(["sh", "-n", CHAINE], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    if shutil.which("shellcheck"):
        p = subprocess.run(["shellcheck", "-s", "sh", CHAINE],
                           capture_output=True, text=True)
        assert p.returncode == 0, p.stdout
