# Measuring a kernel for games on real hardware

The numbers in `bench.md` come from virtual machines. They are good for
spotting a regression, not for saying a kernel is faster at games: a VM
has no real GPU, a virtual timer and a host that runs other work. This is
the protocol for a real laptop or desktop, the same every time.

## Before

- Mains power, power mode **Balanced** (Settings > System > Power), lid
  open, screen on, nothing else running. Five minutes after signing in.
- `sudo apt install rt-tests stress-ng gcc mangohud`
- Copy `tests/bench/` from this repository to the computer.

## 1. Scheduler latency and frame pacing (no game, ~25 min)

On Ubuntu's kernel, then again after switching to the Raye kernel
(Settings > Raye Update > Drivers > Raye kernel), same day, same
power mode:

    sudo ./game-bench

It records the machine (kernel, CPU, power mode, cpufreq driver and EPP,
THP, ntsync, I/O schedulers, sysctls, boot time) and runs, three rounds:

| | what | read |
|---|---|---|
| `cyc-*` | cyclictest, a normal task waking every 1 ms, idle and next to 1x and 2x as many CPU hogs as CPUs | p50, p99, max wake-up delay (µs) |
| `frame-*` | `frame.c`: 4 ms of work every 16.7 ms, same three loads | p50, p99, p99.9 time to finish the frame (µs), frames over 16.7 ms |
| `hackbench` | message passing between 160 tasks | seconds, lower is better: what the scheduler costs in throughput |

With raye-scx installed each round runs twice, the kernel's own
scheduler and then scx_lavd (what game mode loads).

    ./summary.py ~/raye-bench/*/*/

## 2. Boot

Three cold starts on each kernel (power off, wait 10 s, power on, sign
in), then `systemd-analyze` and `systemd-analyze blame | head`. Keep the
three "Startup finished" lines; report the median.

## 3. A game

One game with a fixed, repeatable scene (a benchmark mode if it has one,
otherwise the same 60 s walk from the same save). In Steam, launch
options:

    MANGOHUD_CONFIG=autostart_log=10,log_duration=60,output_folder=/home/<you>/raye-bench/game mangohud %command%

Three runs per kernel and scheduler, each with the game alone and with a
background load started just before (`stress-ng --cpu $(( $(nproc) / 2 )) --timeout 120s`).
For lavd, start it first: `sudo scx_lavd` in a terminal, Ctrl-C after.
Then `./summary.py ~/raye-bench/game/` gives the average fps and the
1 % and 0.1 % lows of each log.

## Reading it

Median of three. A change is kept only when it moves the median the
right way by more than the spread of the three runs, as in `bench.md`.
What matters most for a game is the 1 % low and the frames over 16.7 ms
under load, not the average.
