#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import argparse
import csv
import json
import math
import sys
from typing import Any


# Main raw OpenLane metrics to collect.
METRIC_KEYS = {
    # Run health
    "flow_errors": "flow__errors__count",
    "flow_warnings": "flow__warnings__count",
    "lint_errors": "design__lint_error__count",
    "lint_warnings": "design__lint_warning__count",
    "inferred_latches": "design__inferred_latch__count",
    "unmapped_cells": "design__instance_unmapped__count",
    "synthesis_check_errors": "synthesis__check_error__count",

    # Area / size
    "instance_count": "design__instance__count",
    "stdcell_count": "design__instance__count__stdcell",
    "instance_area_um2": "design__instance__area",
    "stdcell_area_um2": "design__instance__area__stdcell",
    "core_area_um2": "design__core__area",
    "die_area_um2": "design__die__area",
    "utilization": "design__instance__utilization",

    # Cell breakdown
    "inverter_count": "design__instance__count__class:inverter",
    "sequential_cell_count": "design__instance__count__class:sequential_cell",
    "multi_input_comb_cell_count": "design__instance__count__class:multi_input_combinational_cell",
    "timing_repair_buffer_count": "design__instance__count__class:timing_repair_buffer",
    "clock_buffer_count": "design__instance__count__class:clock_buffer",
    "clock_inverter_count": "design__instance__count__class:clock_inverter",
    "setup_buffer_count": "design__instance__count_setup_buffer",
    "hold_buffer_count": "design__instance__count_hold_buffer",
    "antenna_diode_count": "antenna_diodes_count",

    # Timing summary
    "setup_ws_ns": "timing__setup__ws",
    "hold_ws_ns": "timing__hold__ws",
    "setup_tns_ns": "timing__setup__tns",
    "hold_tns_ns": "timing__hold__tns",
    "setup_wns_ns": "timing__setup__wns",
    "hold_wns_ns": "timing__hold__wns",
    "setup_violations": "timing__setup_vio__count",
    "hold_violations": "timing__hold_vio__count",
    "setup_r2r_ws_ns": "timing__setup_r2r__ws",
    "hold_r2r_ws_ns": "timing__hold_r2r__ws",

    # Corner timing
    "setup_ws_tt_ns": "timing__setup__ws__corner:max_tt_025C_1v80",
    "setup_ws_ss_ns": "timing__setup__ws__corner:max_ss_100C_1v60",
    "setup_ws_ff_ns": "timing__setup__ws__corner:max_ff_n40C_1v95",
    "hold_ws_tt_ns": "timing__hold__ws__corner:min_tt_025C_1v80",
    "hold_ws_ss_ns": "timing__hold__ws__corner:min_ss_100C_1v60",
    "hold_ws_ff_ns": "timing__hold__ws__corner:min_ff_n40C_1v95",

    # Routing / physical checks
    "max_slew_violations": "design__max_slew_violation__count",
    "max_fanout_violations": "design__max_fanout_violation__count",
    "max_cap_violations": "design__max_cap_violation__count",
    "design_violations": "design__violations",
    "route_drc_errors": "route__drc_errors",
    "magic_drc_errors": "magic__drc_error__count",
    "klayout_drc_errors": "klayout__drc_error__count",
    "antenna_violations": "route__antenna_violation__count",
    "antenna_violating_nets": "antenna__violating__nets",
    "antenna_violating_pins": "antenna__violating__pins",

    # Routing complexity
    "estimated_wirelength_um": "route__wirelength__estimated",
    "final_wirelength_um": "route__wirelength",
    "max_wirelength_um": "route__wirelength__max",
    "vias": "route__vias",
    "nets": "route__net",
    "special_nets": "route__net__special",

    # Power
    "internal_power_w": "power__internal__total",
    "switching_power_w": "power__switching__total",
    "leakage_power_w": "power__leakage__total",
    "total_power_w": "power__total",

    # LVS / signoff
    "xor_differences": "design__xor_difference__count",
    "lvs_errors": "design__lvs_error__count",
    "lvs_device_differences": "design__lvs_device_difference__count",
    "lvs_net_differences": "design__lvs_net_difference__count",
    "lvs_unmatched_devices": "design__lvs_unmatched_device__count",
    "lvs_unmatched_nets": "design__lvs_unmatched_net__count",
    "lvs_unmatched_pins": "design__lvs_unmatched_pin__count",
}


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(errors="ignore"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str) and value.strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def safe_zero(value: Any) -> float:
    number = to_float(value)
    return 0.0 if number is None else number


def bool_pass(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def find_metrics_path(run_dir: Path) -> Path:
    metrics_path = run_dir / "final" / "metrics.json"
    if metrics_path.exists():
        return metrics_path

    # Fallback for unusual run layouts.
    candidates = list(run_dir.rglob("metrics.json"))
    if candidates:
        return sorted(candidates)[-1]

    raise FileNotFoundError(f"Could not find final/metrics.json under {run_dir}")


def find_config(run_dir: Path) -> dict[str, Any]:
    candidates = [
        run_dir / "config.json",
        run_dir / "final" / "config.json",
        run_dir / "76-misc-reportmanufacturability" / "config.json",
    ]

    for path in candidates:
        if path.exists():
            data = load_json(path)
            if data:
                return data

    # Fallback: use the last config.json found.
    found = list(run_dir.rglob("config.json"))
    if found:
        data = load_json(sorted(found)[-1])
        if data:
            return data

    return {}


def get_metric(metrics: dict[str, Any], key: str) -> Any:
    return metrics.get(key)


def get_clock_period_ns(metrics: dict[str, Any], config: dict[str, Any]) -> float | None:
    # Prefer config CLOCK_PERIOD because this is the user-specified target.
    for source in (config, metrics):
        value = source.get("CLOCK_PERIOD")
        number = to_float(value)
        if number is not None:
            return number

    # Some OpenLane versions may store this under different names.
    for key in ("clock_period", "design__clock_period", "timing__clock_period"):
        number = to_float(metrics.get(key))
        if number is not None:
            return number

    return None


def collect_one_run(name: str, run_dir: Path) -> dict[str, Any]:
    metrics_path = find_metrics_path(run_dir)
    metrics = load_json(metrics_path)
    if metrics is None:
        raise ValueError(f"Could not parse metrics JSON: {metrics_path}")

    config = find_config(run_dir)

    row: dict[str, Any] = {
        "design": name,
        "run_dir": str(run_dir),
        "metrics_path": str(metrics_path),
        "openlane_version": config.get("meta", {}).get("openlane_version") if isinstance(config.get("meta"), dict) else None,
        "design_name": config.get("DESIGN_NAME"),
        "clock_period_ns": get_clock_period_ns(metrics, config),
        "fp_core_util": config.get("FP_CORE_UTIL"),
        "pdk": config.get("PDK"),
        "std_cell_library": config.get("STD_CELL_LIBRARY"),
    }

    for out_key, metric_key in METRIC_KEYS.items():
        row[out_key] = get_metric(metrics, metric_key)

    add_derived_metrics(row)
    add_signoff_status(row)

    return row


def add_derived_metrics(row: dict[str, Any]) -> None:
    clock_period_ns = to_float(row.get("clock_period_ns"))
    setup_ws_ns = to_float(row.get("setup_ws_ns"))
    instance_area_um2 = to_float(row.get("instance_area_um2"))
    stdcell_area_um2 = to_float(row.get("stdcell_area_um2"))
    total_power_w = to_float(row.get("total_power_w"))

    # Convert W to mW for paper readability.
    if total_power_w is not None:
        row["total_power_mw"] = total_power_w * 1e3
    else:
        row["total_power_mw"] = None

    internal_power_w = to_float(row.get("internal_power_w"))
    switching_power_w = to_float(row.get("switching_power_w"))
    leakage_power_w = to_float(row.get("leakage_power_w"))

    row["internal_power_mw"] = internal_power_w * 1e3 if internal_power_w is not None else None
    row["switching_power_mw"] = switching_power_w * 1e3 if switching_power_w is not None else None
    row["leakage_power_mw"] = leakage_power_w * 1e3 if leakage_power_w is not None else None

    # Target frequency from the requested clock period.
    if clock_period_ns and clock_period_ns > 0:
        row["target_fmax_mhz"] = 1000.0 / clock_period_ns
    else:
        row["target_fmax_mhz"] = None

    # Estimated critical path from target period minus setup slack.
    # This is useful because all designs may target the same clock.
    if clock_period_ns is not None and setup_ws_ns is not None:
        critical_path_ns = clock_period_ns - setup_ws_ns
        row["estimated_critical_path_ns"] = critical_path_ns

        if critical_path_ns > 0:
            row["estimated_fmax_mhz"] = 1000.0 / critical_path_ns
        else:
            row["estimated_fmax_mhz"] = None
    else:
        row["estimated_critical_path_ns"] = None
        row["estimated_fmax_mhz"] = None

    # Use instance area as primary area metric. Fall back to stdcell area.
    area_um2 = instance_area_um2 if instance_area_um2 is not None else stdcell_area_um2
    row["paper_area_um2"] = area_um2

    # Energy/op approximation:
    # mW * ns = pJ, assuming one operation per cycle and power estimate is representative.
    total_power_mw = to_float(row.get("total_power_mw"))

    if total_power_mw is not None and clock_period_ns is not None:
        row["energy_per_op_at_target_pj"] = total_power_mw * clock_period_ns
    else:
        row["energy_per_op_at_target_pj"] = None

    critical_path_ns = to_float(row.get("estimated_critical_path_ns"))
    if total_power_mw is not None and critical_path_ns is not None:
        row["energy_per_op_estimated_pj"] = total_power_mw * critical_path_ns
    else:
        row["energy_per_op_estimated_pj"] = None

    if area_um2 is not None and critical_path_ns is not None:
        row["area_delay_product_um2_ns"] = area_um2 * critical_path_ns
    else:
        row["area_delay_product_um2_ns"] = None

    if total_power_mw is not None and critical_path_ns is not None:
        row["power_delay_product_mw_ns"] = total_power_mw * critical_path_ns
    else:
        row["power_delay_product_mw_ns"] = None

    if area_um2 is not None and row.get("estimated_fmax_mhz") is not None:
        row["fmax_per_area_mhz_per_um2"] = row["estimated_fmax_mhz"] / area_um2
    else:
        row["fmax_per_area_mhz_per_um2"] = None


def add_signoff_status(row: dict[str, Any]) -> None:
    setup_vios = safe_zero(row.get("setup_violations"))
    hold_vios = safe_zero(row.get("hold_violations"))
    max_slew_vios = safe_zero(row.get("max_slew_violations"))
    max_cap_vios = safe_zero(row.get("max_cap_violations"))
    max_fanout_vios = safe_zero(row.get("max_fanout_violations"))

    magic_drc = safe_zero(row.get("magic_drc_errors"))
    klayout_drc = safe_zero(row.get("klayout_drc_errors"))
    route_drc = safe_zero(row.get("route_drc_errors"))

    lvs_errors = safe_zero(row.get("lvs_errors"))
    lvs_device_diff = safe_zero(row.get("lvs_device_differences"))
    lvs_net_diff = safe_zero(row.get("lvs_net_differences"))
    lvs_unmatched_devices = safe_zero(row.get("lvs_unmatched_devices"))
    lvs_unmatched_nets = safe_zero(row.get("lvs_unmatched_nets"))
    lvs_unmatched_pins = safe_zero(row.get("lvs_unmatched_pins"))

    antenna_vios = safe_zero(row.get("antenna_violations"))
    antenna_nets = safe_zero(row.get("antenna_violating_nets"))
    antenna_pins = safe_zero(row.get("antenna_violating_pins"))

    lint_errors = safe_zero(row.get("lint_errors"))
    inferred_latches = safe_zero(row.get("inferred_latches"))
    unmapped_cells = safe_zero(row.get("unmapped_cells"))
    synth_errors = safe_zero(row.get("synthesis_check_errors"))

    timing_clean = (
        setup_vios == 0
        and hold_vios == 0
        and max_slew_vios == 0
        and max_cap_vios == 0
        and max_fanout_vios == 0
    )

    drc_clean = magic_drc == 0 and klayout_drc == 0 and route_drc == 0

    lvs_clean = (
        lvs_errors == 0
        and lvs_device_diff == 0
        and lvs_net_diff == 0
        and lvs_unmatched_devices == 0
        and lvs_unmatched_nets == 0
        and lvs_unmatched_pins == 0
    )

    antenna_clean = antenna_vios == 0 and antenna_nets == 0 and antenna_pins == 0

    synth_clean = lint_errors == 0 and inferred_latches == 0 and unmapped_cells == 0 and synth_errors == 0

    signoff_clean = timing_clean and drc_clean and lvs_clean and antenna_clean

    row["timing_clean"] = bool_pass(timing_clean)
    row["drc_clean"] = bool_pass(drc_clean)
    row["lvs_clean"] = bool_pass(lvs_clean)
    row["antenna_clean"] = bool_pass(antenna_clean)
    row["synthesis_clean"] = bool_pass(synth_clean)
    row["signoff_clean"] = bool_pass(signoff_clean)


def parse_design_arg(item: str) -> tuple[str, Path]:
    if ":" not in item:
        raise ValueError(f"Expected --design NAME:RUN_DIR, got: {item}")

    name, run = item.split(":", 1)
    name = name.strip()
    run = run.strip()

    if not name or not run:
        raise ValueError(f"Expected --design NAME:RUN_DIR, got: {item}")

    return name, Path(run)


def get_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    design_runs: list[tuple[str, Path]] = []

    for item in args.design:
        design_runs.append(parse_design_arg(item))

    for run_dir in args.run_dirs:
        name = args.name if args.name else Path(run_dir).parent.parent.name
        design_runs.append((name, Path(run_dir)))

    if not design_runs:
        raise ValueError("No runs provided. Use positional run_dir or --design NAME:RUN_DIR.")

    rows = []
    for name, run_dir in design_runs:
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory does not exist: {run_dir}")
        rows.append(collect_one_run(name, run_dir))

    return rows


def write_csv(rows: list[dict[str, Any]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # Stable column order: important paper fields first, then everything else.
    preferred = [
        "design",
        "design_name",
        "run_dir",
        "clock_period_ns",
        "target_fmax_mhz",
        "estimated_critical_path_ns",
        "estimated_fmax_mhz",

        "paper_area_um2",
        "instance_area_um2",
        "stdcell_area_um2",
        "core_area_um2",
        "die_area_um2",
        "utilization",
        "instance_count",
        "stdcell_count",

        "total_power_mw",
        "internal_power_mw",
        "switching_power_mw",
        "leakage_power_mw",

        "energy_per_op_at_target_pj",
        "energy_per_op_estimated_pj",
        "area_delay_product_um2_ns",
        "power_delay_product_mw_ns",
        "fmax_per_area_mhz_per_um2",

        "setup_ws_ns",
        "hold_ws_ns",
        "setup_violations",
        "hold_violations",
        "max_slew_violations",
        "max_cap_violations",
        "max_fanout_violations",

        "magic_drc_errors",
        "klayout_drc_errors",
        "route_drc_errors",
        "lvs_errors",
        "antenna_violations",
        "antenna_violating_nets",
        "antenna_violating_pins",

        "timing_clean",
        "drc_clean",
        "lvs_clean",
        "antenna_clean",
        "synthesis_clean",
        "signoff_clean",

        "lint_errors",
        "lint_warnings",
        "inferred_latches",
        "unmapped_cells",
        "synthesis_check_errors",

        "final_wirelength_um",
        "estimated_wirelength_um",
        "max_wirelength_um",
        "vias",
        "nets",
        "special_nets",

        "sequential_cell_count",
        "multi_input_comb_cell_count",
        "inverter_count",
        "timing_repair_buffer_count",
        "clock_buffer_count",
        "clock_inverter_count",
        "setup_buffer_count",
        "hold_buffer_count",
        "antenna_diode_count",

        "pdk",
        "std_cell_library",
        "openlane_version",
        "metrics_path",
    ]

    all_keys = set()
    for row in rows:
        all_keys.update(row.keys())

    fieldnames = preferred + sorted(k for k in all_keys if k not in preferred)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows: list[dict[str, Any]], out_json: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=4)


def print_summary(rows: list[dict[str, Any]]) -> None:
    print("\n=== Metrics Summary ===")
    for row in rows:
        print(f"\nDesign: {row.get('design')}")
        print(f"  Run: {row.get('run_dir')}")
        print(f"  Signoff: {row.get('signoff_clean')}")
        print(f"  Timing/DRC/LVS/Antenna: "
              f"{row.get('timing_clean')}/"
              f"{row.get('drc_clean')}/"
              f"{row.get('lvs_clean')}/"
              f"{row.get('antenna_clean')}")
        print(f"  Area: {row.get('paper_area_um2')} um^2")
        print(f"  Critical path estimate: {row.get('estimated_critical_path_ns')} ns")
        print(f"  Estimated Fmax: {row.get('estimated_fmax_mhz')} MHz")
        print(f"  Total power: {row.get('total_power_mw')} mW")
        print(f"  Energy/op at target: {row.get('energy_per_op_at_target_pj')} pJ")
        print(f"  Area-delay product: {row.get('area_delay_product_um2_ns')} um^2*ns")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect OpenLane final metrics for ASIC multiplier comparison.")
    parser.add_argument("run_dirs", nargs="*", type=Path, help="Path(s) to OpenLane runs/RUN_* directories")
    parser.add_argument("--name", type=str, default=None, help="Design name for single positional run")
    parser.add_argument(
        "--design",
        action="append",
        default=[],
        help="Named run in the form NAME:RUN_DIR. Can be used multiple times.",
    )
    parser.add_argument("--out-csv", type=Path, default=Path("results/metrics_summary.csv"))
    parser.add_argument("--out-json", type=Path, default=Path("results/metrics_summary.json"))
    parser.add_argument("--summary", action="store_true", help="Print compact human-readable summary")
    args = parser.parse_args()

    try:
        rows = get_rows(args)
        write_csv(rows, args.out_csv)
        write_json(rows, args.out_json)

        print(f"Wrote CSV:  {args.out_csv}")
        print(f"Wrote JSON: {args.out_json}")

        if args.summary:
            print_summary(rows)

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())