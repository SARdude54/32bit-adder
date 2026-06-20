#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, TextIO


ANTENNA_REPORT_NAMES = {
    "antenna.rpt",
    "antenna_summary.rpt",
}

METRIC_KEYS = {
    "antenna__violating__nets",
    "antenna__violating__pins",
    "route__antenna_violation__count",
    "antenna_diodes_count",
    "design__instance__count__class:antenna_cell",
}


def emit(out: TextIO, msg: str = "") -> None:
    print(msg, file=out)


def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except Exception as exc:
        return f"<<could not read {path}: {exc}>>"


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(errors="ignore"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def find_files(run_dir: Path) -> dict[str, list[Path]]:
    files = {
        "antenna_reports": [],
        "metrics_json": [],
        "logs": [],
        "defs": [],
        "verilog": [],
    }

    for path in run_dir.rglob("*"):
        if not path.is_file():
            continue

        name = path.name.lower()
        path_str = str(path).lower()

        if name in ANTENNA_REPORT_NAMES:
            files["antenna_reports"].append(path)
        elif name in {"or_metrics_out.json", "state_out.json", "state_in.json"}:
            files["metrics_json"].append(path)
        elif "antenna" in path_str and name.endswith(".log"):
            files["logs"].append(path)
        elif name.endswith(".def"):
            files["defs"].append(path)
        elif name.endswith((".v", ".sv")):
            files["verilog"].append(path)

    return files


def extract_metrics(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not data:
        return {}

    out = {}
    for key in METRIC_KEYS:
        if key in data:
            out[key] = data[key]

    metrics = data.get("metrics")
    if isinstance(metrics, dict):
        for key in METRIC_KEYS:
            if key in metrics:
                out[key] = metrics[key]

    return out


def parse_antenna_report(path: Path) -> dict[str, Any]:
    text = read_text(path)
    lines = text.splitlines()

    result: dict[str, Any] = {
        "path": path,
        "nets": [],
        "pins": [],
        "info": [],
        "summary_rows": [],
        "raw_violation_lines": [],
    }

    current_net = None

    for line in lines:
        stripped = line.strip()

        net_match = re.match(r"Net:\s+(.+)", stripped)
        if net_match:
            current_net = net_match.group(1).strip()
            result["nets"].append(current_net)
            result["raw_violation_lines"].append(stripped)
            continue

        pin_match = re.match(r"Pin:\s+(.+)", stripped)
        if pin_match:
            pin_text = pin_match.group(1).strip()
            result["pins"].append({"net": current_net, "pin": pin_text})
            result["raw_violation_lines"].append(stripped)
            continue

        if "Found" in stripped and ("violation" in stripped or "violations" in stripped):
            result["info"].append(stripped)
            result["raw_violation_lines"].append(stripped)

        # Parse OpenROAD antenna_summary.rpt table lines like:
        # │ 1.15 │ 460.97 │ 400.00 │ clknet_... │ _11024_/CLK │ met1 │
        if "│" in stripped and not any(h in stripped for h in ["Partial", "Required", "━", "┃"]):
            cells = [c.strip() for c in stripped.split("│") if c.strip()]
            if len(cells) >= 6:
                result["summary_rows"].append(
                    {
                        "p_over_r": cells[0],
                        "partial": cells[1],
                        "required": cells[2],
                        "net": cells[3],
                        "pin": cells[4],
                        "layer": cells[5],
                    }
                )

    result["nets"] = list(dict.fromkeys(result["nets"]))
    return result


def grep_net_in_files(net: str, files: list[Path], max_hits: int = 40) -> list[tuple[Path, int, str]]:
    hits = []
    for path in files:
        text = read_text(path)
        for i, line in enumerate(text.splitlines(), start=1):
            if net in line:
                hits.append((path, i, line.rstrip()))
                if len(hits) >= max_hits:
                    return hits
    return hits


def print_metrics_summary(out: TextIO, files: dict[str, list[Path]], show_clean: bool) -> None:
    emit(out, "\n=== Antenna Metrics by Step ===")

    rows = []
    for path in sorted(files["metrics_json"]):
        metrics = extract_metrics(path)
        if not metrics:
            continue

        has_antenna_metric = any(k in metrics for k in METRIC_KEYS)
        if not has_antenna_metric:
            continue

        violating_nets = metrics.get("antenna__violating__nets")
        violating_pins = metrics.get("antenna__violating__pins")

        if not show_clean and violating_nets in {0, "0"} and violating_pins in {0, "0"}:
            continue

        rows.append((path, metrics))

    if not rows:
        emit(out, "No antenna metrics found.")
        return

    for path, metrics in rows:
        emit(out, f"\n[{path}]")
        for key in sorted(metrics):
            emit(out, f"  {key}: {metrics[key]}")


def print_report_summary(
    out: TextIO,
    run_dir: Path,
    files: dict[str, list[Path]],
    net_filter: str | None,
) -> list[str]:
    emit(out, "\n=== Antenna Reports ===")

    found_nets: list[str] = []

    if not files["antenna_reports"]:
        emit(out, "No antenna.rpt or antenna_summary.rpt files found.")
        return found_nets

    for report in sorted(files["antenna_reports"]):
        parsed = parse_antenna_report(report)

        if net_filter:
            report_text = read_text(report)
            if net_filter not in report_text:
                continue

        rel = report.relative_to(run_dir)
        emit(out, f"\n--- {rel} ---")

        if parsed["info"]:
            for item in parsed["info"]:
                emit(out, f"  {item}")

        if parsed["summary_rows"]:
            emit(out, "  Summary rows:")
            for row in parsed["summary_rows"]:
                emit(
                    out,
                    f"    net={row['net']} pin={row['pin']} "
                    f"layer={row['layer']} partial={row['partial']} "
                    f"required={row['required']} P/R={row['p_over_r']}",
                )
                found_nets.append(row["net"])

        if parsed["nets"]:
            emit(out, "  Nets:")
            for net in parsed["nets"]:
                emit(out, f"    {net}")
                found_nets.append(net)

        if parsed["pins"]:
            emit(out, "  Pins:")
            for item in parsed["pins"][:20]:
                emit(out, f"    net={item['net']} pin={item['pin']}")
            if len(parsed["pins"]) > 20:
                emit(out, f"    ... {len(parsed['pins']) - 20} more pins")

        if not parsed["info"] and not parsed["summary_rows"] and not parsed["nets"] and not parsed["pins"]:
            emit(out, "  No explicit violations found in this report.")

    return list(dict.fromkeys(found_nets))


def print_diode_summary(out: TextIO, run_dir: Path, files: dict[str, list[Path]]) -> None:
    emit(out, "\n=== Antenna Diode Instances in DEF ===")

    diode_re = re.compile(r"^\s*-\s+(\S+)\s+(\S*diode\S*)\b", re.IGNORECASE)
    found = []

    for path in sorted(files["defs"]):
        text = read_text(path)
        for line in text.splitlines():
            m = diode_re.match(line)
            if m:
                found.append((path, m.group(1), m.group(2), line.strip()))

    if not found:
        emit(out, "No diode instances found in DEF files.")
        return

    emit(out, f"Found {len(found)} diode instance entries.")
    for path, inst, cell, _line in found[:40]:
        emit(out, f"  {path.relative_to(run_dir)}: {inst} {cell}")
    if len(found) > 40:
        emit(out, f"  ... {len(found) - 40} more")


def print_net_context(out: TextIO, run_dir: Path, files: dict[str, list[Path]], nets: list[str]) -> None:
    if not nets:
        return

    searchable = files["defs"] + files["verilog"] + files["logs"]

    emit(out, "\n=== Net Context ===")
    for net in nets:
        emit(out, f"\n--- Net: {net} ---")
        hits = grep_net_in_files(net, searchable, max_hits=20)
        if not hits:
            emit(out, "  No context hits found.")
            continue

        for path, line_no, line in hits:
            emit(out, f"  {path.relative_to(run_dir)}:{line_no}: {line}")


def write_report(
    out: TextIO,
    run_dir: Path,
    files: dict[str, list[Path]],
    show_clean: bool,
    net_filter: str | None,
    no_context: bool,
) -> None:
    emit(out, f"OpenLane run: {run_dir}")
    emit(out, f"antenna reports: {len(files['antenna_reports'])}")
    emit(out, f"metrics json files: {len(files['metrics_json'])}")
    emit(out, f"DEF files: {len(files['defs'])}")
    emit(out, f"Verilog files: {len(files['verilog'])}")

    print_metrics_summary(out, files, show_clean)
    nets = print_report_summary(out, run_dir, files, net_filter)
    print_diode_summary(out, run_dir, files)

    if net_filter:
        nets = [net_filter]

    if not no_context:
        print_net_context(out, run_dir, files, nets)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize antenna violations from an OpenLane run.")
    parser.add_argument("run_dir", type=Path, help="Path to runs/RUN_* directory")
    parser.add_argument("--show-clean", action="store_true", help="Show steps with zero antenna violations")
    parser.add_argument("--net", type=str, default=None, help="Filter reports/context to a specific net")
    parser.add_argument("--no-context", action="store_true", help="Do not grep DEF/Verilog/logs for net context")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output report path. Default: <run_dir>/antenna_debug_summary.txt",
    )
    args = parser.parse_args()

    run_dir = args.run_dir
    if not run_dir.exists() or not run_dir.is_dir():
        print(f"ERROR: run directory does not exist: {run_dir}", file=sys.stderr)
        return 1

    out_path = args.out if args.out is not None else run_dir / "antenna_debug_summary.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = find_files(run_dir)

    try:
        with out_path.open("w", encoding="utf-8") as out:
            write_report(
                out=out,
                run_dir=run_dir,
                files=files,
                show_clean=args.show_clean,
                net_filter=args.net,
                no_context=args.no_context,
            )
    except OSError as exc:
        print(f"ERROR: could not write output file {out_path}: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote antenna debug report to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())