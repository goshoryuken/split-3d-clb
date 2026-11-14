#!/usr/bin/env python3
"""What the critical path of each hard-block run goes through (run_hardblocks.sh outputs).

Reads Path 1 of each run's report_timing.setup.rpt, written with --timing_report_detail
detailed (run_hardblocks.sh passes it), which lists every routing node with its layer. Per path:

  wire      delay of inter-block routing: output pin, wire segments, connection block
  intra     delay inside blocks: crossbars, block-internal wiring and in-block layer crossings
  prim      primitive delays: LUTs, multipliers, flip-flop and RAM clock-to-Q
  hops      wire segments used; L16 how many of them are long wires
  xings     layer changes along the inter-block routing (pin to wire, wire to pin)
  hard      hard blocks on the path (dsp, ram), or "-"
  skew      launch minus capture clock arrival (clocks are routed, so it is not zero);
            cpd-skew is the data path plus setup of that one path

Usage: hb_paths.py OUT [--runs]   (OUT/{split,stack}/<run>/report_timing.setup.rpt)
"""
import collections
import re
import statistics
import sys
from pathlib import Path

HARD = {"two_mult_18x19": "dsp", "one_mult_27x27": "dsp", "dual_port_ram": "ram", "single_port_ram": "ram"}
ROW = re.compile(r"^(.*?)\s+(-?[\d.]+)\s+(-?[\d.]+)$")
LAYER = re.compile(r"\((\d+),(\d+),(\d+)\)?")


def path_one(report):
    text = report.read_text()
    m = re.search(r"#Path 1\n(.*?)\n#Path 2", text, re.S) or re.search(r"#Path 1\n(.*)", text, re.S)
    return m.group(1)


def analyse(report):
    block = path_one(report)
    arrival, required = block.split("data arrival time", 1)
    rows = []
    for line in arrival.splitlines():
        m = ROW.match(line.strip())
        if m and not line.startswith(("clock", "Point")):
            rows.append((m.group(1), float(m.group(2))))
    # The data path starts at the launching element's clock-to-output.
    start = next(i for i, (text, _) in enumerate(rows) if "Tcq_max" in text or "[clock-to-output]" in text
                 or "(.input" in text and "clk" not in text.split()[0])
    launch = sum(incr for _, incr in rows[:start])
    capture = 0.0
    for line in required.splitlines():
        m = ROW.match(line.strip())
        if m and not line.strip().startswith(("clock", "cell setup", "data required", "data arrival")):
            capture += float(m.group(2))
    out = dict(wire=0.0, intra=0.0, prim=0.0, hops=0, l16=0, xings=0, hard=[], start="", end="")
    last_layer = None
    for text, incr in rows[start:]:
        if text.startswith("| (intra"):
            out["intra"] += incr
        elif text.startswith("| (primitive"):
            out["prim"] += incr
            kind = re.search(r"primitive '([^']+)'", text).group(1)
            if kind in HARD:
                out["hard"].append(HARD[kind])
        elif text.startswith(("| (OPIN", "| (IPIN", "| (CHAN")):
            out["wire"] += incr
            layers = [int(z) for _, _, z in LAYER.findall(text)]
            if text.startswith("| (CHAN"):
                out["hops"] += 1
                out["l16"] += " L16 " in text
            first = layers[0] if layers else None
            if text.startswith("| (OPIN"):
                last_layer = first
            elif first is not None and last_layer is not None and first != last_layer:
                out["xings"] += 1
            if layers:
                last_layer = layers[-1]
        elif not text.startswith("|"):
            kind = re.search(r"\(([^ )]+)", text)
            if kind:
                out["start"] = out["start"] or kind.group(1)
                out["end"] = kind.group(1)
    out["hard"] = "+".join(out["hard"]) or "-"
    out["skew"] = launch - capture
    out["cpd"] = -float(re.search(r"slack \(\w+\)\s+(-?[\d.]+)", block).group(1))
    return out


def config_of(run):
    name = run.name
    fabric = "2d" if name.startswith("2d_") else run.parent.name
    m = re.search(r"_hb(\w*?)(_clk\w+)?$", name)
    placement = m.group(1) if m and m.group(1) else "2d"
    bench = re.search(r"_c[\d.]+_(.+)_(\d+)_hb", name)
    return ("2d" if fabric == "2d" else f"{fabric}/{placement}"), bench.group(1), bench.group(2)


def main():
    out = Path(sys.argv[1])
    rows = collections.defaultdict(list)
    for report in sorted(out.glob("*/*/report_timing.setup.rpt")):
        config, bench, seed = config_of(report.parent)
        try:
            r = analyse(report)
        except (StopIteration, AttributeError, ValueError) as error:
            print(f"skip {report}: {error!r}", file=sys.stderr)
            continue
        rows[config].append((bench, seed, r))
        if "--runs" in sys.argv:
            print(f"{config:15} {bench:22} {seed:>2} cpd {r['cpd']:6.2f} skew {r['skew']:5.2f} wire {r['wire']:5.2f} "
                  f"intra {r['intra']:5.2f} prim {r['prim']:5.2f} hops {r['hops']:2} L16 {r['l16']:2} xings {r['xings']:2} "
                  f"{r['start']:>15} -> {r['end']:<15} hard {r['hard']}")
    print(f"\n{'config':15}{'runs':>5}{'via hard':>9}{'cpd':>7}{'skew':>6}{'cpd-skew':>9}{'wire':>6}{'intra':>6}{'prim':>6}{'hops':>6}{'L16':>5}{'xings':>6}"
          "   (means; delays in ns)")
    for config, items in sorted(rows.items(), key=lambda kv: (kv[0] != "2d", kv[0])):
        rs = [r for _, _, r in items]
        via = sum(r["hard"] != "-" or r["start"] in HARD or r["end"] in HARD for r in rs)
        mean = lambda k: statistics.mean(r[k] for r in rs)
        print(f"{config:15}{len(rs):>5}{via:>9}{mean('cpd'):7.2f}{mean('skew'):6.2f}{mean('cpd') - mean('skew'):9.2f}{mean('wire'):6.2f}{mean('intra'):6.2f}"
              f"{mean('prim'):6.2f}{mean('hops'):6.1f}{mean('l16'):5.1f}{mean('xings'):6.1f}")


if __name__ == "__main__":
    main()
