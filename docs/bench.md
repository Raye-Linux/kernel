# Raye kernel: what was measured

Ubuntu's 7.0.0-42-generic against the same kernel with Raye's changes,
November 2026. Each candidate came from the usual desktop kernel tweaks
(scheduler, preemption, I/O, compiler flags, memory defaults); only the
ones that are small enough to carry from one Ubuntu update to the next
were built and measured. None of this was measured on real hardware
yet: the numbers below come from virtual machines on a shared host, so
read them as directions, not as figures to publish.

## Where and how

- **Bench guest**: 8 vCPU, 4 GiB, Ubuntu's kernel, no Secure Boot, so
  the scheduler settings could be switched at run time
  (`/sys/kernel/debug/sched/base_slice_ns` and `preempt`). Rounds taken
  while another big build ran on the host were thrown away.
- **the test VM**: the Raye beta image, 4 vCPU, Secure Boot on, encrypted
  Btrfs, TPM. Ubuntu's kernel, then a Raye test kernel with all four
  candidates, signed with a test key enrolled through MokManager.
- `tests/bench/frame.c`: a game-like loop, 4 ms of CPU work every
  16.7 ms (60 Hz); prints how long after the frame start the work was
  done (p50, p99, p99.9, max, in µs) and the frames that missed 16.7 ms.
  Run next to `stress-ng --cpu N`, N = one or two times the CPU count.
- `cyclictest -p0`: wake-up latency of a normal (not real-time) task,
  1 ms period, under the same load.
- `tests/bench/evclose.c`: 300 open/close of `/dev/input/event0`.
- fio on a LUKS2 (aes-xts) mapping, 2 jobs, 15 s per test, with and
  without dm-crypt's queues (`cryptsetup refresh --perf-no_*`).
- A `tinyconfig` kernel build, hackbench, `stress-ng --switch`.

## Kept

### Input devices close without waiting (patch 0002)

| 300 open/close of an input device, the test VM | Ubuntu | Raye |
|---|---|---|
| total | 1377 ms | 0.8 ms |

Every close waited for an RCU grace period, about 4.5 ms. A session
start, a logout or a switch to a text console closes dozens of input
devices one after the other. Nothing else changes; the freeing of the
client is deferred to an RCU callback.

## Left out (in `experiments/`)

### Scheduler base slice not scaled by CPU count

Frame test in the bench guest, µs, two clean rounds each:

| | 8 hogs p50 | 8 hogs p99 | 16 hogs p50 | 16 hogs p99 |
|---|---|---|---|---|
| Ubuntu (2.8 ms slice, lazy) | 7543, 7606 | 9875, 8417 | 7609, 7817 | 14615, 14816 |
| 0.7 ms slice | 8372, 8237 | 8477, 8645 | 8678, 8671 | 12907, 12560 |
| full preemption | 7457, 7563 | 8774, 8903 | 7794, 7773 | 14464, 14106 |
| both | 8127, 8142 | 9114, 8744 | 8690, 8618 | 15900, 13143 |

The test VM, Raye test kernel (0.7 ms slice and full preemption) against
Ubuntu: p50 6600 → 8073 µs with 4 hogs, 7031 → 8557 µs with 8 hogs;
p99 9617 → 9061 and 13061 → 13089 µs.

Shorter slices make the worst frames under heavy load a little steadier
and every frame slower: the game's 4 ms of work gets cut into more
pieces. Not a win for games. Wake-up latency of a sleeping task
(cyclictest p99, 40 to 80 µs) did not move with either setting.

### Full preemption

No difference in the frame test, in wake-up latency or in the build
time above the noise; hackbench 8.5–8.9 s against 8.9–9.1 s. Ubuntu's
lazy model stays. Anyone who wants it can boot with `preempt=full`.

### dm-crypt without its queues

| fio, LUKS2 | with queues | in place |
|---|---|---|
| 4k random read | 70.6k, 80.0k IOPS | 75.3k, 76.9k |
| 4k random write | 38.9k, 64.2k IOPS (p99 2.7, 1.5 ms) | 81.6k, 82.3k (p99 1.3, 1.3 ms) |
| 1M read | 1203, 1040 MiB/s | 1020, 1070 |
| 1M write | 1980, 2077 MiB/s | 1338, 1367 |

Small writes up to twice as fast with half the tail latency, but big
writes (copying a game, a video) a third slower: the queues spread the
encryption of one big copy over every core. Mixed, so not on by
default. It can be set per disk without a kernel change:
`cryptsetup refresh --perf-no_read_workqueue --perf-no_write_workqueue --persistent <name>`.

## Game mode scheduler (sched_ext), November 12

Nested guest on a busy host (8 vCPU, 6 GiB, the 0.3.1 image's own
system and tuning), Ubuntu's `7.0.0-43-generic`. `frame.c` and
`cyclictest -p0` next to 8 (1x) and 16 (2x) CPU hogs, `hackbench` x3.
Median of three rounds for EEVDF and lavd, two for the others; µs.

| | frame p99 1x | frame p99 2x | frame p99.9 2x | frames over 16.7 ms, 2x | hackbench s |
|---|---|---|---|---|---|
| EEVDF (default) | 8468 | 14205 | 15224 | 1, 2, 0 | 0.747 |
| scx_lavd 1.1.4 | 9542 | 8159 | 8906 | 0, 0, 0 | 0.700 |
| `preempt=full` | 8521 | 14610 | 26345 | 6, 0 | 0.788 |
| scx_bpfland 1.1.4 | 7799 | 9497 | 10691 | 0, 0 | 1.325 |

lavd keeps the frame on time when the game competes with twice as many
busy tasks as CPUs: the slow frames come down by 40 % and none miss
16.7 ms, with no loss of throughput. At 1x it is a little slower than
EEVDF and both stay far under a frame. bpfland has the best median
but costs three quarters more time in hackbench. Full preemption again
does nothing for frames. So: EEVDF for the desktop, lavd while a game
runs (raye-scx). lavd also attached and ran the same with
`lockdown=integrity`, the lockdown level Secure Boot puts the kernel in.

The Raye kernel built on 7.0.0-43.43 against Ubuntu's, same guest, runs
interleaved (two rounds each), frame p99 at 2x: EEVDF 14439 against
14821 µs, lavd 8324 against 8173 µs; hackbench 0.726 against 0.747 s.
The same, as it should be: nothing in the scheduler differs. Boot to
the login screen, `systemd-analyze`, kernel then user space: Raye 3.31
and 2.94 s, 3.32 and 2.88 s; Ubuntu 3.38 and 3.28, 3.33 and 3.17, 3.24
and 3.16 s.

## Same either way

- Boot, the test VM with Ubuntu's kernel: 11.9, 12.3, 13.1 s (kernel and
  initrd with the TPM unlock 8.4–8.9 s, user space 3.6–4.1 s). The Raye
  kernel reaches the end of its own init in 1.49 s against 1.20 s
  (one boot each, inside the noise of this host); its first boot asks
  the disk password (see Secure Boot below), so its total is not
  comparable.
- Memory: same configuration, same footprint (7868 against 7869 MiB
  visible to the system).
- Build time, context switches: within the noise.

## Secure Boot

Checked in the test VM with the test key: the kernel image signed with the
boot key is refused until that key is enrolled ("bad shim lock
signature", then GRUB falls back to Ubuntu's kernel); after enrolment
in MokManager (blue screen at the restart: Enroll MOK, Continue, Yes,
the one-time password) it starts, lockdown stays in integrity mode, and
every module loads, the disk encryption included. The first start asks
the disk password once, because the TPM measures the certificate that
checked the kernel. `raye-kernel-setup` handles the order (enrol first,
install after) and the second TPM binding.
