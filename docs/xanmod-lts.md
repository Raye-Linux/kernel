# XanMod LTS as a patch series on Ubuntu's kernel - measured 2026-11-06

The owner's decision, in his words: *« tu te base sur le noyau xanmod lts
avec leurs patch, pas tu le remplace. Le noyau va être lui de Ubuntu de
base mais avec les patchs les plus récents de la version LTS, auto update
bien sûr, je veux avoir rien à faire. »*

So Ubuntu's kernel stays the base - `build.sh` is unchanged, it still does
`apt-get source linux=<version>` - and XanMod's **LTS series** goes on top,
the way `patches/0001` and `0002` already do. This file is what that costs,
measured rather than argued.

## The answer, in four numbers

| | |
|---|---|
| Patches in XanMod's LTS series (`6.18.60-xanmod1`) | **49** |
| Apply whole on Ubuntu's `linux 7.0.0-43.43`, in series order | **36** |
| Already in Ubuntu's tree - `patch(1)` refuses them itself | **4** |
| Do not apply; a real rewrite, not a nudge | **9** |

**Feasible, and cheaper than the version gap suggested** - but the useful
count is not 36. Of those 36, almost every one is already settled in this
repository: three are `patches/` today, nine are `experiments/`, and the
rest `docs/xanmod.md` refuses for reasons that have nothing to do with
whether they apply. What the owner asks for is, in substance, **already
built**; what was missing is the machine that notices when XanMod's series
moves. That is `xanmod_lts.py`.

**And the nine conflicts cost Raye nothing.** Eight of them are patches
this repository already refuses, or that Ubuntu already carries by another
route - measured below, one by one. Exactly **one** is a genuine open
question, and it happens to be one of the two patches `docs/xanmod.md`
admitted had been *« compared by title only, never against Ubuntu's
tree »*. Both are now measured.

## What this was measured against

| Quoi | Référence exacte |
|---|---|
| XanMod LTS | `gitlab.com/xanmod/linux`, tag **`6.18.60-xanmod1`**, branch `6.18`. It is the LTS line: the EPYC host's own meta-package reads `linux-xanmod-lts-x64v3 6.18.60-xanmod1-0` |
| Ubuntu kernel | **`linux 7.0.0-43.43`**, rebuilt from `linux_7.0.0.orig.tar.gz` (md5 `415e5d4ee110d9415c2901751e6f9c9d`, as the `.dsc` says) + `linux_7.0.0-43.43.diff.gz`, applied with **0 failed hunks and 0 fuzz**. Upstream `SUBLEVEL = 14` |
| How | `patch -p1 --fuzz=0 --forward --batch` - `build.sh`'s own flags - each patch alone on the pristine tree, **and** the series applied cumulatively in order |

**`linux 7.0.0-43.43` does exist, and the pocket is what decides.** Read
from the four `Sources` indexes rather than from one machine's
`sources.list`:

```
resolute            7.0.0-14.14      ← the release pocket, months behind
resolute-security   7.0.0-42.42
resolute-updates    7.0.0-43.43      ← the current kernel
resolute-proposed   7.0.0-43.43
```

A chain that reads `resolute` tracks a kernel four months old and never
says so. `xanmod_lts.py ubuntu` reads `resolute-updates`, and says which
pocket it read.

## The two traps in getting the series at all

Neither is visible from the outside, and either one silently hands back the
wrong series.

**1. Reachability cannot be used.** `git log <upstream>..<tip>` on a shallow
clone answered **12849** commits where the series is 49: the graft cuts the
history, so commits that *are* upstream look unreachable and get counted.
The branch has to be walked by **first parent**, stopping at the upstream
release it was forked from (`Linux 6.18`, by Linus) - 115 commits.

`git fetch --deepen=400 origin` on a clone made from a **tag** does
nothing at all: measured, the clone stayed at depth 1 and the walk then saw
no series whatever. The ref has to be named: `git fetch --depth 200 origin
6.18.60-xanmod1`.

**2. XanMod applies, reverts, and re-applies.** Of those 115 commits, 66 are
version bumps, CI commits, reverts, or the commits those reverts cancel.
BBRv3 appears **three times** and is reverted twice; the ISA-level pair
appears twice and is reverted once. Take the commits naively and the series
carries both a patch and its own revert, or a stale copy of one - and the
kernel that comes out compiles, boots, and misbehaves. `serie_vivante()`
resolves the pairs, tolerating the `[v6.18.33+]` suffix XanMod adds when it
re-applies, and **raises** on a revert whose target is not in the series
rather than dropping the line.

## The series, patch by patch

« alone » is the patch on the pristine Ubuntu tree; « in order » is the
series applied cumulatively, which is what `build.sh` does. The two differ
and the difference matters: **0002** needs **0001** first (it edits lines
0001 adds), and **0033**/**0036** patch files that **0032**/**0035**
*create*, so alone they fail with *can't find file to patch*.

| # | Patch | Applies alone | In order |
|---|---|---|---|
| 1 | `XANMOD: x86/build: Add more CFLAGS optimizations` | yes | applies |
| 2 | `XANMOD: x86/build: Add LLVM polyhedral loop optimizer flags` | no | applies |
| 3 | `XANMOD: kbuild: Add SMS-based software pipelining flags` | yes | applies |
| 4 | `XANMOD: kbuild: deb-pkg: Create -dbg when make DEB_DEBUG_PKG=1` | yes | applies |
| 5 | `kbuild: Re-add .config file required to sign external modules` | yes | applies |
| 6 | `XANMOD: fair: Set scheduler tunable latencies to unscaled` | yes | applies |
| 7 | `XANMOD: sched: Add yield_type sysctl to reduce or disable sched_yield` | no | CONFLICT |
| 8 | `XANMOD: block/mq-deadline: Increase write priority to improve responsiveness` | yes | applies |
| 9 | `XANMOD: block/mq-deadline: Disable front_merges by default` | yes | applies |
| 10 | `XANMOD: block: Set rq_affinity to force complete I/O requests on same CPU` | yes | applies |
| 11 | `XANMOD: blk-wbt: Set wbt_default_latency_nsec() to 2msec` | no | CONFLICT |
| 12 | `XANMOD: kconfig: add 500Hz timer interrupt kernel config option` | yes | applies |
| 13 | `XANMOD: vfs: Decrease rate at which vfs caches are reclaimed` | yes | applies |
| 14 | `XANMOD: mm: Raise max_map_count default value` | yes | applies |
| 15 | `XANMOD: mm/vmscan: Reduce amount of swapping` | no | CONFLICT |
| 16 | `XANMOD: sched/autogroup: Add kernel parameter and config option to enable/disable autogr` | yes | applies |
| 17 | `XANMOD: cpufreq: tunes ondemand and conservative governor for performance` | yes | applies |
| 18 | `XANMOD: lib/kconfig.debug: disable default SYMBOLIC_ERRNAME and DEBUG_BUGVERBOSE` | yes | applies |
| 19 | `XANMOD: scripts/setlocalversion: remove '+' tag for git repo short version` | yes | applies |
| 20 | `XANMOD: scripts/setlocalversion: Move localversion* files to the end` | yes | applies |
| 21 | `XANMOD: x86/build: Prevent generating avx2 floating-point code` | yes | applies |
| 22 | `sched/wait: Do accept() in LIFO order for cache efficiency` | yes | applies |
| 23 | `firmware: Enable stateless firmware loading` | yes | applies |
| 24 | `locking: rwsem: spin faster` | yes | applies |
| 25 | `drivers: initialize ata before graphics` | no | CONFLICT |
| 26 | `ZEN: input/evdev: Use call_rcu when detaching client` | yes | applies |
| 27 | `ZEN: dm-crypt: Disable workqueues for crypto ops` | yes | applies |
| 28 | `tcp: Add a sysctl to skip tcp collapse processing when the receive buffer is full` | yes | applies |
| 29 | `netfilter: Add netfilter nf_tables fullcone support` | yes | applies |
| 30 | `netfilter: add xt_FLOWOFFLOAD target` | yes | applies |
| 31 | `extcon: Add driver for Steam Deck` | yes | applies |
| 32 | `hwmon: Add driver for Steam Deck's EC sensors` | yes | applies |
| 33 | `hwmon: steamdeck-hwmon: Add support for max battery level/rate` | no | applies |
| 34 | `leds: steamdeck: Add support for Steam Deck LED` | yes | applies |
| 35 | `mfd: Add MFD core driver for Steam Deck` | yes | applies |
| 36 | `mfd: steamdeck: Expose controller board power in sysfs` | no | applies |
| 37 | `binder: turn into module` | no | already upstream |
| 38 | `binder: give binder_alloc its own debug mask file` | no | already upstream |
| 39 | `wait: allow to use __wake_up_pollfree() from GPL modules` | no | already upstream |
| 40 | `file: export file_close_fd() instead of close_fd_get_file()` | no | already upstream |
| 41 | `PCI: Enable overrides for missing ACS capabilities` | no | CONFLICT |
| 42 | `sysctl: add sysctl to disallow unprivileged CLONE_NEWUSER by default` | no | CONFLICT |
| 43 | `Fix merge [1/2]: sched/proxy: Yield the donor task` | no | CONFLICT |
| 44 | `Fix merge [2/2]: sched/proxy: Yield the donor task` | yes | applies |
| 45 | `mm: Add working set protection for anon and clean file pages` | yes | applies |
| 46 | `tcp_bbr: v3: update TCP 'bbr' congestion control module to BBRv3 [v6.18.33+]` | no | CONFLICT |
| 47 | `x86/kconfig: more x86-64 ISA levels and uarches [v6.18.54+]` | yes | applies |
| 48 | `XANMOD: Makefile: Move x86 instruction set selection to kernel-wide build [v6.18.54+]` | no | CONFLICT |
| 49 | `x86/build/64: Fix kconfig recursive dependency` | yes | applies |

## The nine conflicts, one by one

The order is what matters here, not the count: **eight of the nine are
patches Raye already refuses or already has.** A conflict is not forced and
no hunk is trimmed to fit - a kernel patch applied in part builds, boots,
and behaves badly under load, and nothing anywhere reports it.

| # | Patch | What failed, measured | Verdict |
|---|---|---|---|
| 25 | `drivers: initialize ata before graphics` | both hunks FAILED. **Ubuntu already did it**: in the pristine tree `obj-$(CONFIG_ATA) += ata/` is line **80** and `obj-y += gpu/` is line **83**. Ubuntu moved the same line by another route, so the context the patch removes is gone | **unnecessary** - the change is already in effect |
| 42 | `sysctl: add sysctl to disallow unprivileged CLONE_NEWUSER by default` | 2 of 3 hunks FAILED in `kernel/fork.c`. **Ubuntu already carries it**: `unprivileged_userns_clone` at `include/linux/user_namespace.h:208` and `kernel/fork.c:126, 1999, 3164` | **unnecessary, and forcing it would duplicate the definitions** |
| 15 | `XANMOD: mm/vmscan: Reduce amount of swapping` | hunk FAILED at 199 at `--fuzz=0`; it **would** pass with fuzz tolerated, which is exactly why `build.sh` forbids fuzz | **refused on purpose**: Ubuntu's default is `vm_swappiness = 60`, XanMod wants 10, and Raye deliberately sets **150** (`90-raye.conf`) because it swaps to zram. Taking it would undo a measured choice, in the opposite direction |
| 11 | `XANMOD: blk-wbt: Set wbt_default_latency_nsec() to 2msec` | hunk FAILED at 731 | already `experiments/blk-wbt-2ms.patch`, and flagged there as **the one that can cost a hard disk** - a 2 ms target meant for flash, met by holding writes back |
| 41 | `PCI: Enable overrides for missing ACS capabilities` | 1 of 1 hunk FAILED in the kernel-parameters doc, 1 of 2 in `drivers/pci/quirks.c` | **refused** (`docs/xanmod.md`): it breaks IOMMU group isolation. Useful to pass a card to a VM, harmful as a default |
| 46 | `tcp_bbr: v3: ... BBRv3 [v6.18.33+]` | **5 hunks FAILED** across 17 files, 32 offsets | **refused**: 1722 lines that cannot be carried from one Ubuntu kernel to the next, and unnecessary - `90-raye.conf` already sets `net.ipv4.tcp_congestion_control = bbr`, and the kernel loads `tcp_bbr` itself |
| 48 | `XANMOD: Makefile: Move x86 instruction set selection to kernel-wide build` | 3 hunks FAILED (`Makefile:1116`, `arch/x86/Makefile:178`) - Ubuntu put its APX/EGPR lines in the very block the patch moves | **refused**: its point is `CONFIG_X86_64_VERSION=3`, which needs **AVX2**, so nothing older than Haswell starts. Raye promises to boot old machines. A separate flavour one day, never the default |
| 7 + 43 | `XANMOD: sched: Add yield_type sysctl` and `Fix merge [1/2]: sched/proxy: Yield the donor task` | `kernel/sched/syscalls.c` hunk FAILED at 1343, and the fix-up at 1364. `kernel/sysctl.c` applies (offset −82) | **the only genuinely open one.** It exists on XanMod's 6.18 branch and not on their 7.0 branch, and `docs/xanmod.md` admitted it had only ever been compared by title. Now measured: it conflicts because Ubuntu 7.0 carries the `sched/proxy` donor-task rework - which is precisely what XanMod's own two `Fix merge` commits were written for, on 6.18 |

## What is actually new, and applies

The other of the two patches `docs/xanmod.md` had only compared by title:

- **16, `XANMOD: sched/autogroup: Add kernel parameter and config option`** - 
  **applies cleanly** (3 offsets). A boot parameter and a config option to
  turn autogroup on or off; Ubuntu has `CONFIG_SCHED_AUTOGROUP=y` already,
  so this adds the switch, not the feature. Not measured at run time.
- **21, `XANMOD: x86/build: Prevent generating avx2 floating-point code`** - 
  applies cleanly. Unlike 47/48 it does not raise the ISA level, so it does
  not cost old machines their boot.

Everything else that applies is already decided in this repository:
`patches/` (3 of them: `0003` = XanMod 5, `0004` = XanMod 4, `0002` =
XanMod 26), `experiments/` (9), or refused in `docs/xanmod.md` with its
reason. **Applying the 36 wholesale would, among other things, turn off
`DEBUG_BUGVERBOSE` - the stop code on Raye's own crash screen - and move
`localversion` handling, which decides the module path, so the signing and
the TPM seal.** Those are patches 18, 19 and 20, and all three apply
cleanly. *Applies* is not *wanted*.

## The automatic chain, and the line it does not cross

`xanmod_lts.py` is the tracker. It does not build and it does not publish.

```
./xanmod_lts.py tag                  the newest XanMod LTS tag
./xanmod_lts.py ubuntu               the newest Ubuntu kernel (resolute-updates)
./xanmod_lts.py review <tag>         what XanMod changed since the manifest
./xanmod_lts.py check <tag> --tree T apply-test the series; refuse on any failure
./xanmod_lts.py --have               exit 0 when the manifest is usable
```

Two refusals, and they are the whole point:

- **`exiger_serie_revue`** - a patch of XanMod's series with no line in
  `xanmod/manifest.txt` stops the chain **by name**. That is how « je veux
  rien avoir à faire » stays safe: XanMod adding a patch is the event that
  must not pass unseen, and a chain that degrades in silence is worse than
  no chain, because it ships a kernel nobody read.
- **`exiger_serie_applicable`** - one patch that does not apply, and the
  build does not happen. Nothing is forced, no hunk is dropped.

**Where it stops, and the owner has to know it.** The release's signature
is his: the key lives in `/var/lib/raye-release/gnupg` and nothing is published
without him saying so. The chain is built to go as far as *a package built
and tested* and then stop on a plain statement - « an update is ready, here
is what it changes, here are the bench numbers ». It will never publish by
itself, and that limit is deliberate, not an omission.

**And the fallback never goes away.** Ubuntu's signed kernel stays the
default in the boot menu, the Raye kernel gets one trial boot, and a disk
the TPM opens gets a second binding for the new kernel. That is the filet;
no automatic chain is allowed to remove it.

## What wakes it - and why a bare timer would not have

The owner's words were *« auto update bien sûr je veux avoir rien à
faire »*. Until 2026-11-06 nothing woke the chain at all: it was a tool you
had to remember, which is the opposite of nothing to do.

```
./xanmod-check              # the default: look, speak only if something moved
./xanmod-check --montre     # what the last look found
```

| Piece | Where |
|---|---|
| trigger | `xanmod-check` |
| units | `data/raye-xanmod-check.service` + `.timer` - daily, `Persistent=true` |
| the news | `xanmod/annonce.txt`, written only when there is news and **erased when there is not** |
| channel | `RAYE_NOTIFY`, an **absolute** path, in `/etc/default/raye-xanmod-check` |
| tests | `tests/test_xanmod_check.py` - 14 checks, proven red on 6 injected regressions |

**A plain timer on `check` would have rebuilt the silence it was meant
to remove.** `xanmod-lts-update.sh check` exits **0** whichever answer it
has - a new XanMod tag, a new Ubuntu kernel, or nothing at all. A nightly
timer therefore succeeds identically in all three cases, and the one line
that matters, `MOVED: was X, now Y`, sits in the journal where nobody
reads it. That is this product's most expensive defect family, and it
would have been reintroduced by the very thing meant to fix it. So the
news has to leave a durable artefact, and a chain that cannot run has to
**fail** rather than report nothing.

**`RAYE_NOTIFY` must be an absolute path, and the trigger refuses a
bare name.** Measured twice in this lab: systemd and `ssh` both run a
command with a `PATH` that has no `/usr/local/bin`, so a bare name is
simply not found - and the notifier's own failure would be exactly the
silence this file exists to remove. A notifier that fails is not
swallowed either: the announcement is already on disk, but the unit going
red is the only thing left that says the channel is broken.

### Where « nothing to do » stops, and why that is the right place

The trigger looks by itself. It does **not** build, and that is a refusal,
not a gap:

- three of XanMod's patches **apply cleanly while breaking promises Raye
  makes** - `DEBUG_BUGVERBOSE=n` removes the stop code from the crash
  screen, and two `setlocalversion` patches move the module path, which
  breaks module signing **and** the TPM sealing of the disk;
- so an unattended build does not save a chore, it ships a machine whose
  encrypted disk will not open - and nothing downstream would say so.

A new series bump therefore costs **one** human verdict
(`./xanmod_lts.py review <tag>`), after which `apply` runs unattended. The
units are written and tested; **installing them is one command, and it is
the owner's**, since a timer is persistence on his machine:

```
cp data/raye-xanmod-check.{service,timer} /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now raye-xanmod-check.timer
systemctl list-timers raye-xanmod-check.timer
```

## Not measured

- **Nothing here was compiled.** « Applies » means the text goes into the
  tree: not that the kernel builds, not that it boots, not that it is
  faster. A kernel build wants tens of gigabytes and this was measured on a
  host with 55 GB free and eleven other jobs running, so no build was
  started - a deliberate refusal, not an oversight.
- **No bench numbers.** `docs/bench.md` is what turns any of this into a
  verdict, and it needs a built kernel.
- **Battery** on the owner's laptop model cannot be measured here at all.
- **Patch 16 and 21**, the two genuinely new candidates, have no run-time
  measurement. They belong in `experiments/` until `docs/bench.md` says
  otherwise.
