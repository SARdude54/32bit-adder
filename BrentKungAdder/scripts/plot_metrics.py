#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def to_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        if value == "" or value.lower() in {"none", "nan", "null"}:
            return None

    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def require_rows(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("CSV has no rows.")


def design_labels(rows: list[dict[str, str]]) -> list[str]:
    labels = []
    for i, row in enumerate(rows):
        label = row.get("design") or row.get("design_name") or f"design_{i}"
        labels.append(label)
    return labels


def get_values(rows: list[dict[str, str]], key: str) -> list[float | None]:
    return [to_float(row.get(key)) for row in rows]


def filter_valid(labels: list[str], values: list[float | None]) -> tuple[list[str], list[float]]:
    out_labels = []
    out_values = []

    for label, value in zip(labels, values):
        if value is not None:
            out_labels.append(label)
            out_values.append(value)

    return out_labels, out_values


def save_current_plot(out_dir: Path, name: str, fmt: str, dpi: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.{fmt}"
    plt.tight_layout()
    plt.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close()
    print(f"Wrote {path}")


def bar_plot(
    rows: list[dict[str, str]],
    key: str,
    ylabel: str,
    title: str,
    out_dir: Path,
    filename: str,
    fmt: str,
    dpi: int,
) -> None:
    labels = design_labels(rows)
    values = get_values(rows, key)
    labels, values = filter_valid(labels, values)

    if not values:
        print(f"Skipping {filename}: no valid values for '{key}'")
        return

    plt.figure(figsize=(8, 4.8))
    plt.bar(labels, values)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.xticks(rotation=30, ha="right")
    plt.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.7)

    save_current_plot(out_dir, filename, fmt, dpi)


def stacked_power_plot(
    rows: list[dict[str, str]],
    out_dir: Path,
    fmt: str,
    dpi: int,
) -> None:
    labels = design_labels(rows)

    internal = get_values(rows, "internal_power_mw")
    switching = get_values(rows, "switching_power_mw")
    leakage = get_values(rows, "leakage_power_mw")

    valid_rows = []
    for label, i, s, l in zip(labels, internal, switching, leakage):
        if i is not None or s is not None or l is not None:
            valid_rows.append((label, i or 0.0, s or 0.0, l or 0.0))

    if not valid_rows:
        print("Skipping power_breakdown_bar: no valid power values")
        return

    labels = [r[0] for r in valid_rows]
    internal = [r[1] for r in valid_rows]
    switching = [r[2] for r in valid_rows]
    leakage = [r[3] for r in valid_rows]

    bottom_switching = internal
    bottom_leakage = [i + s for i, s in zip(internal, switching)]

    plt.figure(figsize=(8, 4.8))
    plt.bar(labels, internal, label="Internal")
    plt.bar(labels, switching, bottom=bottom_switching, label="Switching")
    plt.bar(labels, leakage, bottom=bottom_leakage, label="Leakage")

    plt.ylabel("Power (mW)")
    plt.title("Power Breakdown")
    plt.xticks(rotation=30, ha="right")
    plt.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.7)
    plt.legend()

    save_current_plot(out_dir, "power_breakdown_bar", fmt, dpi)


def scatter_plot(
    rows: list[dict[str, str]],
    x_key: str,
    y_key: str,
    xlabel: str,
    ylabel: str,
    title: str,
    out_dir: Path,
    filename: str,
    fmt: str,
    dpi: int,
) -> None:
    labels = design_labels(rows)
    x_values = get_values(rows, x_key)
    y_values = get_values(rows, y_key)

    points = []
    for label, x, y in zip(labels, x_values, y_values):
        if x is not None and y is not None:
            points.append((label, x, y))

    if not points:
        print(f"Skipping {filename}: no valid values for '{x_key}' and '{y_key}'")
        return

    plt.figure(figsize=(7, 5.2))

    for label, x, y in points:
        plt.scatter(x, y)
        plt.annotate(label, (x, y), textcoords="offset points", xytext=(6, 6), fontsize=8)

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True, linestyle="--", linewidth=0.5, alpha=0.7)

    save_current_plot(out_dir, filename, fmt, dpi)


def signoff_summary_plot(
    rows: list[dict[str, str]],
    out_dir: Path,
    fmt: str,
    dpi: int,
) -> None:
    labels = design_labels(rows)

    checks = [
        ("Timing", "timing_clean"),
        ("DRC", "drc_clean"),
        ("LVS", "lvs_clean"),
        ("Antenna", "antenna_clean"),
        ("Signoff", "signoff_clean"),
    ]

    if not rows:
        return

    y_labels = [name for name, _ in checks]
    x_labels = labels

    matrix = []
    for _, key in checks:
        row_values = []
        for row in rows:
            value = str(row.get(key, "")).strip().upper()
            row_values.append(1 if value == "PASS" else 0)
        matrix.append(row_values)

    plt.figure(figsize=(max(7, 1.0 * len(x_labels)), 3.8))
    plt.imshow(matrix, aspect="auto", vmin=0, vmax=1)

    plt.xticks(range(len(x_labels)), x_labels, rotation=30, ha="right")
    plt.yticks(range(len(y_labels)), y_labels)
    plt.title("Physical Signoff Summary")

    for y, check_row in enumerate(matrix):
        for x, passed in enumerate(check_row):
            text = "PASS" if passed else "FAIL"
            plt.text(x, y, text, ha="center", va="center", fontsize=8)

    save_current_plot(out_dir, "signoff_summary", fmt, dpi)


def write_latex_table(rows: list[dict[str, str]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "metrics_table.tex"

    columns = [
        ("Multiplier", "design"),
        ("Area ($\\mu m^2$)", "paper_area_um2"),
        ("Crit. Path (ns)", "estimated_critical_path_ns"),
        ("Fmax (MHz)", "estimated_fmax_mhz"),
        ("Power (mW)", "total_power_mw"),
        ("Energy/op (pJ)", "energy_per_op_at_target_pj"),
        ("ADP", "area_delay_product_um2_ns"),
        ("Signoff", "signoff_clean"),
    ]

    def fmt_value(key: str, value: str | None) -> str:
        if value is None:
            return "--"

        value = str(value).strip()
        if value == "":
            return "--"

        number = to_float(value)
        if number is None:
            return value.replace("_", "\\_")

        if key in {"paper_area_um2", "area_delay_product_um2_ns"}:
            return f"{number:.2f}"
        if key in {"estimated_critical_path_ns", "total_power_mw", "energy_per_op_at_target_pj"}:
            return f"{number:.3f}"
        if key in {"estimated_fmax_mhz"}:
            return f"{number:.2f}"

        return f"{number:.3f}"

    with path.open("w", encoding="utf-8") as f:
        f.write("\\begin{table}[t]\n")
        f.write("\\centering\n")
        f.write("\\caption{Post-layout ASIC multiplier comparison.}\n")
        f.write("\\label{tab:multiplier_metrics}\n")
        f.write("\\begin{tabular}{lrrrrrrl}\n")
        f.write("\\hline\n")
        f.write(" & ".join(col[0] for col in columns) + " \\\\\n")
        f.write("\\hline\n")

        for row in rows:
            values = [fmt_value(key, row.get(key)) for _, key in columns]
            f.write(" & ".join(values) + " \\\\\n")

        f.write("\\hline\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table}\n")

    print(f"Wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate plots from OpenLane multiplier metrics CSV.")
    parser.add_argument("csv_path", type=Path, help="Path to metrics_summary.csv")
    parser.add_argument("--out-dir", type=Path, default=Path("results/plots"))
    parser.add_argument("--format", choices=["png", "pdf", "svg"], default="png")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--latex-table", action="store_true", help="Also write a LaTeX table.")
    args = parser.parse_args()

    try:
        rows = load_csv(args.csv_path)
        require_rows(rows)

        bar_plot(
            rows,
            key="paper_area_um2",
            ylabel="Area ($\\mu m^2$)",
            title="Multiplier Area Comparison",
            out_dir=args.out_dir,
            filename="area_bar",
            fmt=args.format,
            dpi=args.dpi,
        )

        bar_plot(
            rows,
            key="total_power_mw",
            ylabel="Total Power (mW)",
            title="Total Power Comparison",
            out_dir=args.out_dir,
            filename="power_bar",
            fmt=args.format,
            dpi=args.dpi,
        )

        stacked_power_plot(rows, args.out_dir, args.format, args.dpi)

        bar_plot(
            rows,
            key="estimated_critical_path_ns",
            ylabel="Estimated Critical Path (ns)",
            title="Estimated Critical Path Comparison",
            out_dir=args.out_dir,
            filename="critical_path_bar",
            fmt=args.format,
            dpi=args.dpi,
        )

        bar_plot(
            rows,
            key="estimated_fmax_mhz",
            ylabel="Estimated Fmax (MHz)",
            title="Estimated Fmax Comparison",
            out_dir=args.out_dir,
            filename="fmax_bar",
            fmt=args.format,
            dpi=args.dpi,
        )

        bar_plot(
            rows,
            key="energy_per_op_at_target_pj",
            ylabel="Energy/op at Target Clock (pJ)",
            title="Energy per Operation Comparison",
            out_dir=args.out_dir,
            filename="energy_bar",
            fmt=args.format,
            dpi=args.dpi,
        )

        bar_plot(
            rows,
            key="area_delay_product_um2_ns",
            ylabel="Area-Delay Product ($\\mu m^2 \\cdot ns$)",
            title="Area-Delay Product Comparison",
            out_dir=args.out_dir,
            filename="area_delay_bar",
            fmt=args.format,
            dpi=args.dpi,
        )

        scatter_plot(
            rows,
            x_key="paper_area_um2",
            y_key="estimated_critical_path_ns",
            xlabel="Area ($\\mu m^2$)",
            ylabel="Estimated Critical Path (ns)",
            title="Area-Delay Tradeoff",
            out_dir=args.out_dir,
            filename="area_delay_scatter",
            fmt=args.format,
            dpi=args.dpi,
        )

        scatter_plot(
            rows,
            x_key="total_power_mw",
            y_key="estimated_critical_path_ns",
            xlabel="Total Power (mW)",
            ylabel="Estimated Critical Path (ns)",
            title="Power-Delay Tradeoff",
            out_dir=args.out_dir,
            filename="power_delay_scatter",
            fmt=args.format,
            dpi=args.dpi,
        )

        scatter_plot(
            rows,
            x_key="paper_area_um2",
            y_key="total_power_mw",
            xlabel="Area ($\\mu m^2$)",
            ylabel="Total Power (mW)",
            title="Area-Power Tradeoff",
            out_dir=args.out_dir,
            filename="area_power_scatter",
            fmt=args.format,
            dpi=args.dpi,
        )

        signoff_summary_plot(rows, args.out_dir, args.format, args.dpi)

        if args.latex_table:
            write_latex_table(rows, args.out_dir)

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())