#!/usr/bin/env python3
"""Numbers out of a game-bench run.

    summary.py <run folder>...

Reads cyclictest histograms (cyc-*.hist), frame.c output (frame-*.txt),
hackbench times and MangoHud logs (*.csv), and prints one table per run.
"""
import csv
import glob
import os
import sys


def cyclictest(path):
    """p50, p99 and max wake-up latency in microseconds, all threads together."""
    counts = {}
    overflow = 0
    worst = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("# Max Latencies:"):
                worst = max(int(x) for x in line.split(":")[1].split())
            elif line.startswith("# Histogram Overflows:"):
                overflow = sum(int(x) for x in line.split(":")[1].split())
            elif line[:1].isdigit():
                cols = line.split()
                counts[int(cols[0])] = sum(int(c) for c in cols[1:])
    n = sum(counts.values()) + overflow

    def pct(q):
        seen = 0
        for us in sorted(counts):
            seen += counts[us]
            if seen >= q * n:
                return us
        return worst

    return {"p50": pct(0.50), "p99": pct(0.99), "max": worst, "n": n}


def frame(path):
    with open(path, encoding="utf-8") as f:
        p50, p99, p999, mx, _, missed = f.read().split()
    return {"p50": int(p50), "p99": int(p99), "p999": int(p999),
            "max": int(mx), "missed": int(missed)}


def mangohud(path):
    """Average fps and the 1 % / 0.1 % lows, from the frame times."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    head = next(i for i, r in enumerate(rows) if "frametime" in r)
    col = rows[head].index("frametime")
    ft = sorted((float(r[col]) for r in rows[head + 1:] if len(r) > col and r[col]),
                reverse=True)

    def low(share):
        k = max(1, int(len(ft) * share))
        return round(1000 / (sum(ft[:k]) / k), 2)

    return {"frames": len(ft), "avg_fps": 1000 * len(ft) / sum(ft),
            "low1": low(0.01), "low01": low(0.001)}


def run(folder):
    out = {}
    for p in sorted(glob.glob(os.path.join(folder, "cyc-*.hist"))):
        out["wake " + os.path.basename(p)[4:-5]] = cyclictest(p)
    for p in sorted(glob.glob(os.path.join(folder, "frame-*.txt"))):
        out["frame " + os.path.basename(p)[6:-4]] = frame(p)
    for p in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        out["game " + os.path.basename(p)[:-4]] = mangohud(p)
    hb = os.path.join(folder, "hackbench.txt")
    if os.path.exists(hb):
        with open(hb, encoding="utf-8") as f:
            out["hackbench s"] = [float(l.split()[1]) for l in f if l.startswith("Time:")]
    return out


def main(folders):
    for folder in folders:
        print("==", folder)
        for name, value in run(folder).items():
            print("  %-18s %s" % (name, value))


if __name__ == "__main__":
    main(sys.argv[1:])
