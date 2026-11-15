# What came from XanMod, and what did not

Raye's kernel is Ubuntu's. XanMod is a kernel built for desktops on the
same upstream source, and its series is a ready-made list of the changes
desktop kernels usually carry. The decision (2026-11-05) was to take the
useful patches, never the whole kernel: XanMod's long-term line is 6.18
and Ubuntu 26.04 ships 7.0, so taking their kernel would mean going back
two versions and losing the recent hardware support that is the point of
Raye.

This file is the outcome of a survey made patch by patch.

## The claim everything rests on, measured

Ubuntu's `linux_7.0.0-42.42` is upstream **7.0.14** plus Ubuntu's own
patches, and XanMod has a 7.0 branch of its own whose last state is
`7.0.14-xanmod1`. Both sit on the same upstream code, so nothing had to
be moved from 6.18 to 7.0 by hand.

Checked rather than assumed, in a tree rebuilt the way `build.sh` gets
its source (`linux_7.0.0.orig.tar.gz`, md5 `415e5d4e…` as the `.dsc`
says, plus `linux_7.0.0-42.42.diff.gz`):

- the Ubuntu diff applies with **0 failed hunks and 0 fuzz**, and the
  tree's `Makefile` then reads `SUBLEVEL = 14`;
- the eight patches below apply to it with **`--fuzz=0 --forward`**, the
  flags `build.sh` now uses, with no fuzz anywhere. Some land at an
  offset, which is a hunk found at a different line and not a hunk found
  approximately: `mm` at ten offsets, `rq_affinity` and `blk-wbt` at one;
- the repository's own `0001` and `0002` also still apply at `--fuzz=0`,
  so the stricter flags cost nothing today.

XanMod's 7.0 branch is **frozen** - they are on 7.3 and that branch gets
no more fixes. Patches are taken out of it; it is not followed.

## In `patches/`

Both are packaging, both are three lines or fewer, and neither changes
anything the running kernel does.

- **`0003`, `.config` in the headers package.** Ubuntu's own
  `linux-headers-7.0.0-42-generic` ships
  `/usr/src/linux-headers-…/.config`; the package built here does not,
  because `bindeb-pkg` goes through `install-extmod-build`, which copies
  `include/config/auto.conf` and `kernel.release` and stops. Both halves
  were read from the real `.deb` files, not inferred.
- **`0004`, the `-dbg` package only on request.** `CONFIG_DEBUG_INFO` is
  on, so every build runs `objcopy --only-keep-debug` over every module
  to make a package `build.sh` then deletes. `builddeb` chooses what to
  install from the package name in `debian/control`, so dropping the
  entry stops the work. The image, the modules and the BTF data inside
  `vmlinux` are untouched.

## In `experiments/`, waiting to be measured

Nothing here has been built or measured. `docs/bench.md` is what decides
whether any of it moves to `patches/`.

- **The block batch**: `block-rq-affinity-forced`,
  `block-write-expire-1s`, `block-no-front-merges`. One line each, all
  aimed at how a desktop feels while the disk is busy. Measure as a batch
  first, then one at a time.
- **`blk-wbt-2ms`**, on its own, never in that batch. It is the one that
  can make things worse on the hardware Raye cares about: it gives a hard
  disk the 2 ms latency target meant for flash, and the way write-back
  throttling meets a target it cannot reach is by holding writes back. A
  gain on an SSD and a loss on a hard disk would cancel out in a batch.
- **`rwsem-spin-faster`**. Two lines, and the cost is not only in
  throughput: on x86 the `cpu_relax()` it skips is the `PAUSE`
  instruction, which is what lets a hyperthread sibling use the core and
  lets the CPU drop its frequency. Measure power draw on a laptop too.
- **`mm-working-set-protection`**. The only one that adds a feature
  instead of changing a default, and the one worth the most on a machine
  short of memory. Also the largest, ~290 lines, so the dearest to carry
  forward. It is not inert: `CONFIG_ANON_MIN_RATIO` defaults to 15.

## Refused

| | Why |
|---|---|
| `CONFIG_X86_64_VERSION=3` and the ISA-level patches | v3 needs AVX2, so nothing older than Haswell starts. XanMod ships `=3`; Raye promises to boot on old machines. A separate flavour one day, never the default |
| `DEBUG_BUGVERBOSE=n` | Takes the file and line out of a `BUG()` report, which is what the stop code on the crash screen comes from. Both are `=y` today. ~70 kB against the one screen a user ever sees |
| `HZ_500` | Ubuntu is at **1000**, XanMod at 250. Read from both configs. Adding a 500 Hz option would be a step down |
| `cpufreq` ondemand/conservative tuning | Ubuntu starts on `schedutil`; the patch touches neither governor |
| Polly (`-mllvm` flags) | Clang only, and Ubuntu builds with GCC (`CONFIG_CC_IS_GCC=y`). The flags are dropped in silence |
| `-O3`, SMS pipelining | Would take effect (`CC_OPTIMIZE_FOR_PERFORMANCE=y`), but leaves the binary Ubuntu validated for no shown gain |
| BBRv3 (1722 lines, 3 failing hunks) | Cannot be carried from one Ubuntu kernel to the next. See below: it is also unnecessary |
| ACS override | Breaks IOMMU group isolation. Useful for passing a card to a VM, harmful by default |
| `xt_FLOWOFFLOAD`, `nf_tables` fullcone, LIFO `accept()`, TCP collapse sysctl | Router and server features |
| 6 Steam Deck patches | Hardware enablement, not optimisation |
| `setlocalversion` patches | The version suffix decides the module path, so the signing and the TPM seal. `build.sh` already drives `LOCALVERSION` |
| `CLONE_NEWUSER` sysctl | Already in Ubuntu, identically. Worse, it still applies and duplicates the definition: this is the patch that `--fuzz=0` exists for |
| `file_close_fd`, `__wake_up_pollfree`, both binder patches, ata-before-graphics | Already in Ubuntu's tree |
| `dm-crypt` queues off, unscaled scheduler slices | Already measured here and left out - `experiments/`, `docs/bench.md`. Not to be reopened without new numbers |
| `evdev` `call_rcu` | Already in, as `patches/0002`, measured |

## The three that are not kernel changes at all

`vm.swappiness`, `vm.vfs_cache_pressure` and `vm.max_map_count` are
sysctl defaults. They do not belong in a patch, and they do not belong in
this repository either: this repository builds a kernel, not a system.
They live in `/etc/sysctl.d/90-raye.conf`, shipped by `raye-base`
(`iso/packages/raye-base/release/tuning/90-raye.conf`).

Two of the three are already decided there, and one of them in the
opposite direction:

- **`vm.swappiness`: Raye sets 150, XanMod wants 10.** Raye swaps to
  zram, where swapping out costs a compression and dropping file cache
  costs a disk read, so swapping sooner is the right answer. Taking
  XanMod's value would undo a deliberate choice.
- **`vm.max_map_count`: already high.** Ubuntu's own
  `55-map-count.conf` sets 1048576, Raye deliberately removed its
  duplicate, and `raye-base`'s own test fails if it is set again. Wine
  and Proton are served already.
- **`vm.vfs_cache_pressure`** is the only one still open, and it is
  `raye-base`'s to take.

## BBR is already on, and a fragment cannot turn it on here

The survey suggests replacing the BBRv3 patch with
`CONFIG_DEFAULT_TCP_CONG="bbr"` in `config/raye.config`. That was not
done, for two measured reasons.

It is unnecessary: `90-raye.conf` already sets
`net.ipv4.tcp_congestion_control = bbr`, with `net.core.default_qdisc =
fq` next to it, and the kernel loads `tcp_bbr` itself when the sysctl
asks for it.

And it would not work. `CONFIG_DEFAULT_TCP_CONG` is a derived string with
no prompt of its own; its value comes from the `DEFAULT_BBR` choice,
which `net/ipv4/Kconfig` offers only `if TCP_CONG_BBR=y`, and Ubuntu
builds BBR as a module. Run through the same two steps `build.sh` uses,
`merge_config.sh -m` then `make olddefconfig`, the line is dropped and
the symbol goes back to `"cubic"`. `build.sh` then stops with *the
configuration did not take: CONFIG_DEFAULT_TCP_CONG="bbr"* - checked, and
a fair demonstration that the `EXTRA_CONFIG` guard does its job. Doing it
in the kernel would mean building BBR in instead of as a module, which is
a change to Ubuntu's configuration for no gain over the sysctl.

## Where the survey is wrong

- **`0003` is not about signing.** The survey says the signing scripts
  read `CONFIG_MODULE_SIG_HASH` and `CONFIG_MODULE_SIG_KEY` from
  `.config`. They do not: `scripts/Makefile.modinst` reads them from
  `include/config/auto.conf`, and that file is already in the headers
  package - both symbols are in the one we ship. The patch is worth
  having because Ubuntu ships `.config` and we did not, and out-of-tree
  trees that read it directly would find it on Ubuntu's kernel and not on
  ours. Not because anything is unsigned.
- **The fuzzy `vmscan` patch is the swappiness one**, which is refused
  anyway. The working-set-protection patch, which touches the same file,
  applies with offsets and no fuzz. Measured: `mm/vmscan: Reduce amount
  of swapping` fails at `--fuzz=0` and succeeds "with fuzz 2" without it.
- **`CONFIG_RCU_BOOST` is not set**, and that is now read from the
  shipped configuration rather than deduced from its Kconfig default.

## Not measured

Nothing here was compiled or run. "Applies" means the text goes into the
tree - not that the kernel builds, and not that it is faster. Every
`experiments/` verdict is a candidate for `docs/bench.md`, not a result.

The two patches XanMod's 6.18 branch has and its 7.0 branch does not - 
an `autogroup` boot parameter, and a `yield_type` sysctl sometimes quoted
for games under Wine - were compared by title only, never against
Ubuntu's tree.

**Both are measured now**, against `linux 7.0.0-43.43` - see
`xanmod-lts.md`, which surveys the whole LTS series the same way:

- the **`autogroup` boot parameter** applies cleanly (3 offsets). Ubuntu
  already has `CONFIG_SCHED_AUTOGROUP=y`, so it adds the switch, not the
  feature. No run-time measurement, so `experiments/` at best;
- the **`yield_type` sysctl conflicts**, and it is the only conflict of the
  49 that is a real open question. `kernel/sched/syscalls.c` fails at
  `--fuzz=0`, because Ubuntu 7.0 carries the `sched/proxy` donor-task
  rework - which is exactly what XanMod's own two `Fix merge` commits were
  written for on 6.18.

And the survey's premise was right where this file doubted it: the LTS
series is **not** a 6.18-only thing to be ported forward. 36 of its 49
patches apply to Ubuntu's 7.0 tree unchanged.
