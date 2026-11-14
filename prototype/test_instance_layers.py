#!/usr/bin/env python3
"""Exercise the compiled VTR parser and its stored-data echo, not a mock parser."""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "vtr_flow/arch/timing/k6_frac_N10_mem32K_40nm.xml"
FIXTURE = ROOT / "prototype/split_fle_example.xml"
SPLIT = "0 0 0 0 0 1 1 1 1 1"


def annotate(xml, name, values):
    pattern = r'(<pb_type name="' + re.escape(name) + r'"[^>]*)(>)'
    updated, count = re.subn(
        pattern, lambda m: m[1] + ' instance_layer_offsets="' + values + '"' + m[2], xml
    )
    if count != 1:
        raise AssertionError("Expected exactly one pb_type named " + name)
    return updated


def echo_records(echo):
    """Keep each type's name and indentation so generated children stay distinct."""
    records = []
    for line in echo.splitlines():
        match = re.fullmatch(r"(\t*)pb_type name: (.+)", line)
        if match:
            records.append({"depth": len(match[1]), "name": match[2], "offsets": None})
        elif line.strip().startswith("instance_layer_offsets:"):
            if not records or records[-1]["offsets"] is not None:
                raise AssertionError("Unexpected or duplicate echo assignment")
            records[-1]["offsets"] = line.split(":", 1)[1].strip()
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader", type=Path, required=True)
    args = parser.parse_args()
    reader = args.reader.resolve()
    original = BASE.read_text()
    split_xml = annotate(original, "fle", SPLIT)
    if FIXTURE.read_text() != split_xml:
        raise AssertionError("Bundled fixture must differ only by the FLE attribute")

    cases = []

    def valid(name, xml, assignments, expanded=None):
        cases.append((name, xml, assignments, None, expanded))

    def invalid(name, values, diagnostic="expected a nonnegative decimal integer"):
        cases.append((name, annotate(original, "fle", values), None, diagnostic, None))

    valid("legacy architecture (attribute absent)", original, [])
    valid("five-and-five FLE split", split_xml, [("fle", SPLIT)])
    zeros = " ".join(["0"] * 10)
    valid("explicit all-zero assignment", annotate(original, "fle", zeros), [("fle", zeros)])
    invalid("too few entries", "0 0", "requires exactly num_pb=10 entries; got 2")
    invalid("too many entries", zeros + " 0", "requires exactly num_pb=10 entries; got 11")
    invalid("empty list", "", "requires exactly num_pb=10 entries; got 0")
    for name, token in [
        ("negative entry", "-1"),
        ("trailing junk", "1x"),
        ("fractional entry", "0.5"),
        ("integer overflow", "2147483648"),
    ]:
        invalid(name, " ".join([token] + ["0"] * 9))
    cases.append(("root attribute rejected", annotate(original, "clb", "0"), None,
                  "Unexpected attribute 'instance_layer_offsets'", None))
    valid("automatic LUT expansion preserves original site only",
          annotate(original, "lut6", "1"), [("lut6", "1")], ("lut6", "lut"))

    # Additional boundary and hierarchy coverage beyond the original twelve.
    max_values = "2147483647 " + " ".join(["0"] * 9)
    valid("maximum int accepted (32-bit int target)", annotate(original, "fle", max_values),
          [("fle", max_values)])
    invalid("whitespace-only list", "   &#x9; &#xA; ", "got 0")
    invalid("explicit plus sign", "+1 " + " ".join(["0"] * 9))
    invalid("very large integer", "9" * 100 + " " + " ".join(["0"] * 9))
    valid("XML whitespace separators", annotate(original, "fle", "  0&#x9;0 0 0 0&#xA;1 1 1 1 1  "),
          [("fle", SPLIT)])
    valid("nested offsets stored separately", annotate(split_xml, "ble6", "2"),
          [("fle", SPLIT), ("ble6", "2")])
    valid("automatic memory expansion preserves original site only",
          annotate(original, "mem_512x64_sp", "1"), [("mem_512x64_sp", "1")],
          ("mem_512x64_sp", "memory_slice"))
    valid("leading zeros are decimal", annotate(original, "fle", SPLIT.replace("1", "01")),
          [("fle", SPLIT)])

    failures = 0
    with tempfile.TemporaryDirectory(prefix="vtr-instance-layers-") as directory:
        work = Path(directory)
        for index, (name, xml, expected, diagnostic, expanded) in enumerate(cases, 1):
            source, output = work / "case.xml", work / "case.echo"
            source.write_text(xml)
            if output.exists():
                output.unlink()
            result = subprocess.run([str(reader), str(source), "1", str(output)],
                                    cwd=work, text=True, capture_output=True, timeout=30)
            try:
                if diagnostic is not None:
                    # A crash or an unrelated parser error is not a passing rejection.
                    assert result.returncode == 1, "Expected clean parser rejection"
                    assert "instance_layer_offsets" in result.stdout + result.stderr
                    assert diagnostic in result.stdout + result.stderr
                    assert not output.exists(), "Rejected input produced an echo"
                else:
                    assert result.returncode == 0, "Reader failed"
                    records = echo_records(output.read_text())
                    actual = [(r["name"], r["offsets"]) for r in records if r["offsets"] is not None]
                    assert actual == expected, "Stored assignments: " + repr(actual)
                    if expanded:
                        parent_name, child_name = expanded
                        parent_index = next(i for i, r in enumerate(records) if r["name"] == parent_name)
                        parent = records[parent_index]
                        child = records[parent_index + 1]
                        assert child["name"] == child_name and child["depth"] > parent["depth"]
                        assert child["offsets"] is None, "Generated child duplicates parent offset"
                print("PASS {:02d}: {}".format(index, name))
            except AssertionError as error:
                failures += 1
                print("FAIL {:02d}: {}: {}\n{}{}".format(index, name, error, result.stdout, result.stderr))
    print("{}/{} integration cases passed".format(len(cases) - failures, len(cases)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
