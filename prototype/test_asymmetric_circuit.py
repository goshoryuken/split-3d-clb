#!/usr/bin/env python3
"""Check functional diversity directly from the committed BLIF truth tables."""
from itertools import combinations
from pathlib import Path

tables = []
for line in Path(__file__).with_name("asymmetric_ten_luts.blif").read_text().splitlines():
    if line.startswith(".names"):
        ports = line.split()[1:]
        i = len(tables)
        assert ports == ["a" if i == 0 else f"n{i-1}", "b", "c", "d", "e", "f", f"n{i}"]
        tables.append(set())
    elif line and line[0] in "01":
        bits, value = line.split()
        assert len(bits) == 6 and value == "1"
        tables[-1].add(sum(int(bit) << i for i, bit in enumerate(bits)))
assert len(tables) == 10
for table in tables:
    assert all(any((x in table) != ((x ^ (1 << i)) in table) for x in range(64)) for i in range(6))
rows = []
for x in range(64):
    previous = x & 1
    outputs = []
    for table in tables:
        previous = int(((x & 62) | previous) in table)
        outputs.append(previous)
    rows.append(tuple(outputs))
assert len(set(zip(*rows))) == 10, "Some outputs have identical truth tables"
for i, j in combinations(range(6), 2):
    assert any(rows[x] != rows[x ^ ((((x >> i) ^ (x >> j)) & 1) * ((1 << i) | (1 << j)))]
               for x in range(64)), f"Input swap {i},{j} is invisible"
print("PASS: ten distinct output truth tables; each LUT depends on six inputs; all 15 input swaps observable")
