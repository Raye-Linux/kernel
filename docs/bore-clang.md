# BORE and Clang (V1)

From V1 the Raye kernel is still Ubuntu's 7.0 kernel with Ubuntu's
configuration, with two changes aimed at games and at how the desktop
feels under load:

- the **BORE** scheduler on top of EEVDF (`patches/0005`);
- built with **Clang and LLD, with ThinLTO**, instead of GCC.

Only these two. A whole desktop patch set from another kernel project
would mean a merge to redo by hand at every Ubuntu update, and security
fixes that wait for that merge; this repository keeps to changes small
enough to carry.

## BORE

BORE 7.0.0 by Masahito Suzuki, from
https://github.com/firelzrd/bore-scheduler (the stable patch for 7.1.5,
sha256 in the patch header). It applies to Ubuntu's 7.0.0-43.43 with
fuzz 0 once three hunks are moved by hand; the patch header says which
and why. BORE watches how long a task runs between sleeps and gives the
ones that run in short bursts (compositor, a game's render thread,
audio, input) earlier deadlines than the ones that run flat out.

| | |
|---|---|
| on/off at run time | `sysctl kernel.sched_bore=0` (plain EEVDF) / `=1` |
| boot line | `BORE CPU Scheduler modification 7.0.0 by Masahito Suzuki` |
| base slice | 2 ms at 1000 Hz (`CONFIG_MIN_BASE_SLICE_NS`, BORE's default), not scaled by CPU count |
| game mode | sched_ext (scx_lavd) still replaces it while a game runs |

`docs/bench.md` measured shorter EEVDF slices and full preemption as no
help to frames. BORE is a different thing (it changes who runs first,
not how long), and it is in because the owner asked for it; it still has
to show its numbers with `tests/bench/game-bench` (EEVDF is one sysctl
away, so both run on the same kernel).

## Clang and ThinLTO

`build.sh` reads which `clang-<n>` the `.dsc` of Ubuntu's source
builds with (21 for 7.0.0-43.43; Ubuntu already uses it for the Rust
bindings), installs `lld-<n>` and `llvm-<n>` next to it, and passes
`LLVM=-<n>` to every make. `config/raye.config` asks for
`CC_IS_CLANG`, `LD_IS_LLD` and `LTO_CLANG_THIN`, so a make that lost
`LLVM=` stops at the configuration check, and after the build
`include/generated/compile.h` (what `/proc/version` prints) must name
that Clang and LLD or the build stops.

Ubuntu's tree builds with Clang but for one module: its EtherCAT master
asked for a GCC-only warning, which Clang refuses (`patches/0006`).

What changes against Ubuntu's GCC configuration, read from the merged
`.config`:

| | |
|---|---|
| `RUST` off | Rust cannot be on together with LTO and BTF, and BTF stays (sched_ext needs it). The one Rust driver Ubuntu builds goes with it: `AMCC_QT2025_PHY`, the PHY of Tehuti TN40xx 10G cards |
| `GENDWARFKSYMS` → `GENKSYMS` | module versions computed the classic way, Rust being gone |
| `BUILTIN_MODULE_RANGES` off | not available with LTO; only used by tracing tools |
| `REGULATOR_DA903X` off | its Kconfig refuses Clang; a PMIC of old ARM boards, never found on a PC |
| GCC only, so gone | `UBSAN_BOUNDS_STRICT` (Clang gets `UBSAN_ARRAY_BOUNDS`), `USE_X86_SEG_SUPPORT`, `CC_NO_STRINGOP_OVERFLOW` and the like |

### What it costs elsewhere

- **DKMS.** `dkms` sees `CONFIG_CC_IS_CLANG=y` and builds with
  `make LLVM=1`, which needs the unversioned `clang`, `lld` and `llvm`
  packages on the computer. Without them a DKMS module (VirtualBox,
  v4l2loopback...) fails to build for this kernel. The headers package
  does not depend on them: offline, a dependency apt cannot fetch would
  stop the kernel itself from installing.
- **NVIDIA.** Ubuntu's prebuilt NVIDIA modules never load on this kernel
  (they are signed for and built against Ubuntu's own), so Settings
  refuses the switch on NVIDIA computers. DKMS NVIDIA would build with
  Clang once the three packages above are there, and would then need the
  Raye MOK key to sign it.

## Not done

- **Two variants** (x86-64-v3 and generic, chosen at install). Upstream
  7.0 has no ISA-level option; the generic build is the only one. A v3
  flavour needs XanMod's ISA-level patch (see `xanmod-lts.md`) and a
  choice in the installer.
- **AutoFDO / Propeller**: needs profiles from real machines first.
- **No numbers yet.** Nothing here was booted or measured by this change;
  `game-bench.md` is the protocol.
