#!/usr/bin/env python3
# tests/bench/summary.py turns the raw files of a bench run into numbers.
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("summary", os.path.join(HERE, "bench", "summary.py"))
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)

HIST = """# Histogram
000000 000000\t000000
000010 000050\t000040
000020 000045\t000059
000030 000004\t000000
000400 000001\t000001
# Total: 000000100 000000100
# Min Latencies: 00010 00010
# Avg Latencies: 00015 00016
# Max Latencies: 00400 00400
# Histogram Overflows: 00000 00000
"""


def test_cyclictest_histogram_percentiles(tmp_path):
    p = tmp_path / "cyc.hist"
    p.write_text(HIST)
    got = summary.cyclictest(str(p))
    # 200 samples: 90 at 10 us, 104 at 20, 4 at 30, 2 at 400
    assert got == {"p50": 20, "p99": 30, "max": 400, "n": 200}


def test_cyclictest_overflow_counts_as_worst(tmp_path):
    p = tmp_path / "cyc.hist"
    p.write_text(HIST.replace("# Histogram Overflows: 00000 00000",
                              "# Histogram Overflows: 00003 00000")
                     .replace("# Max Latencies: 00400 00400",
                              "# Max Latencies: 61000 00400"))
    got = summary.cyclictest(str(p))
    assert got["max"] == 61000 and got["n"] == 203


def test_frame_line(tmp_path):
    p = tmp_path / "frame.txt"
    p.write_text("4103 4410 6120 9001 missed 2\n")
    assert summary.frame(str(p)) == {"p50": 4103, "p99": 4410, "p999": 6120,
                                     "max": 9001, "missed": 2}


def test_mangohud_lows(tmp_path):
    # MangoHud CSV: two header lines (system info), then a column header
    rows = ["os,cpu,gpu", "Raye,x,y", "fps,frametime,cpu_load"]
    rows += ["%d,%f,10" % (1000 / ft, ft) for ft in [10.0] * 98 + [40.0, 50.0]]
    p = tmp_path / "game.csv"
    p.write_text("\n".join(rows) + "\n")
    got = summary.mangohud(str(p))
    assert got["frames"] == 100
    assert abs(got["avg_fps"] - 100000 / 1070) < 0.01
    # the 1 % low is the frame rate of the slowest 1 % of frames
    assert got["low1"] == 20.0
