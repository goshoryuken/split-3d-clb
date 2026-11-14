# Related work: 3D FPGAs (2026-11-09)

## Scope of the search

Web and Semantic Scholar searches, two arXiv papers read in full, and all 7 papers citing
LaZagna. A full IEEE Xplore / ACM DL search has not been done. Entries marked *(summary)* come
from an abstract or summary, not the full text.

## Finding

No paper found splits one logic block's LUTs across layers with crossings inside its crossbar.
Every 3D FPGA paper found keeps the logic block whole and goes 3D in one of these ways:

1. vertical links at the logic block's pins or in the switch blocks;
2. routing or configuration memory moved onto another tier (monolithic 3D, or a separate die);
3. whole FPGA dies stacked.

## Closest work

### Pins or routing go 3D, the logic block stays whole

**LaZagna**
- Youssef, Yang, Hao (Georgia Tech), ICCAD 2025, DOI 10.1109/ICCAD66269.2025.11240893, [arXiv 2505.05579](https://arxiv.org/abs/2505.05579).
- Fabrics: 3D CB, CB-O and CB-I (links at logic-block pins) and 3D SB (links in switch blocks).
- 7 citing papers on Semantic Scholar. None splits a logic block.

**Escaping Flatland**
- Youssef, Pramanik, Kahng, Hao (GT, UCSD), DAC 2026, [arXiv 2604.01078](https://arxiv.org/abs/2604.01078).
- 3D placement on LaZagna's fabrics. Layers are assigned per packed block.
- CPD 2-6% better than VTR's placer (geomean), up to ~18%.

**Multi-die routing**
- Poolad, Shahrouz, Boutros, Betz (Toronto, Waterloo), FPL 2026, [arXiv 2606.06421](https://arxiv.org/abs/2606.06421).
- Two 7 nm dies, connected from switch-block wires or block outputs.
- Abstract: up to 14% WL and 6% CPD better than 2D. Uses Koios 2.0.

**Into the Third Dimension**
- Boutros et al. (Toronto), FPT 2023 ([pdf](https://www.eecg.utoronto.ca/~vaughn/papers/fpt2023_3dfpgas.pdf)).
- VPR-3D and RAD-Gen. Vertical links only at logic-block outputs, per the two papers above.

**Hamada et al.**
- VLSI-SoC 2013, two-layer face-to-face FPGA, vertical links at logic-block pins.
- About 31% CPD below a 2D 4-LUT island FPGA, an old baseline.
- Related Kumamoto work: [J-STAGE](https://www.jstage.jst.go.jp/article/imt/10/3/10_425/_pdf/-char/en).

**Siozios, Bartzas, Soudris (3D MEANDER)**
- 2008, vertical interconnect schemes.
- Reported frequency 35% above 2D, in an old model.

**Ababei et al. (TPR)**
- 2005, partition-based 3D place and route.

### Routing or memory on another tier

**Waqar et al. (Georgia Tech, UCLA; Shimeng Yu, Jason Cong)**
- "Monolithic 3D FPGAs Utilizing Back-End-of-Line Configuration Memories", [arXiv 2501.06921](https://arxiv.org/abs/2501.06921). The venue (DAC 2025?) isn't confirmed from the arXiv text.
- Monolithic 3D with oxide-semiconductor transistors (n-type W-doped In2O3, p-type SnO) built in the back-end-of-line. Two changes:
  - configuration SRAM moved to that tier;
  - switch- and connection-block pass gates moved into a tier above the CLBs.
- Read from the PDF text (figures not readable here):
  - Tile footprint is ~49% smaller with the SRAM moved alone, ~59% with the pass gates moved too.
  - Tile-level CPD at equal SRAM voltage (0.8 V) is only ~8% lower, from shorter routing RC. The oxide transistors' weaker drive limits it.
  - The rest comes from overdriving the oxide pass gates (1.2 V against the CMOS baseline's 0.8 V). That removes level restorers, and they argue oxide tolerates the overdrive.
  - Both fabrics are VTR 8's Xilinx-7-like architecture, with delays from a modified COFFE: ASAP7 7 nm for CMOS, ASAP7 plus their compact model for oxide.
  - Six large hyperdimensional-computing benchmarks (FFT, convolution, GEMM, SpMV, AES, Huffman). CPD 11.9-30% lower, area >52% lower, AT² 63.6-77.1% lower. The abstract quotes 27% and 3.4x.
  - GPT-2 on Versal: an estimate assuming the same resource use. Delay -20.6%, area -42.4%.
- **This is the biggest-gain competitor**, but it needs new back-end-of-line devices. Most of its gain is a smaller tile, so shorter wires at 7 nm where wires dominate, plus pass-gate overdrive. It is orthogonal to a bigger cluster.

**vFPGA**
- Cherukuri et al., ACM FPGA 2026.
- Configuration memory on a top die, for fast reconfiguration. The fabric stays on one die.

**Lin, El Gamal et al.**
- Monolithically stacked 3D-FPGA ([pdf](https://isl.stanford.edu/groups/elgamal/people/mlin/papers/performance_FPGA_Lin.pdf)), plus a routing-fabric paper.
- Configuration memory and switches above the logic.
- DATE 2014: logic-on-memory, 14 nm FDSOI.

**Zhang et al., "Monolithic 3-D FPGAs"**
- Proc. IEEE 2015, a review.
- Three kinds: normally-off, 3D switches, and 3D configuration memory or pass transistors *(catalog record)*.

### Patents (light search)

- Xilinx stacked-die interposer and NoC patents (US 7727896, US 8863065, US 8869088).
- US 7692448: reprogrammable 3D FPGA, 16-block clusters per layer.
- None splits a logic block's LUTs across dies.

## How this work relates

1. **Splitting one CLB's LUTs across layers, with crossings inside its crossbar,** is not in the
   papers found. It makes a bigger cluster affordable on each layer, so there are fewer hops between
   CLBs, and it needs only two ordinary logic layers bonded together.
2. **Routing on top instead:** Waqar et al. report 27% lower CPD by moving routing onto a
   back-end-of-line tier with oxide transistors. This work uses ordinary front-end silicon on both
   layers; the two ideas could combine (untested).
3. **Placement delay model:** Escaping Flatland (DAC) shows that VTR's placer mis-charges layer
   changes ("a single average delay per routing-segment type") and fixes it more thoroughly. The
   placer change here is consistent with it.
4. **Comparisons are head to head in one flow:** split against stacked (LaZagna's own 3D) and
   against the best 2D, with the same delays, since each paper's 2D baseline and process differ.
5. **Benchmarks:** recent papers use Koios 2.0. This work uses 7 Koios designs with RAM and DSP
   blocks, 7 bigger VTR designs and 16 MCNC designs.
6. **Bond model:** hybrid bonding is studied at 1-5 µm pitch and microbumps at 10-25 µm. The
   crossing here is a sky130 met5 pad, with a bond-pitch sweep in `results_pitch/`.
