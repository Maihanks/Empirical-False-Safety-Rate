#!/usr/bin/env python3
"""Aggregate results/csv/transformations.csv into Table I and Table II of
the article (Section V), plus the pairwise between-process comparisons of
RQ2 and the divergence-taxonomy distribution.

Usage: uv run python scripts/aggregate_results.py [--csv path] [--out results/tables]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from efsr.config import DEFAULT_CONFIG
from efsr.results import ResultsStore
from efsr.stats.compare import compare_processes
from efsr.stats.efsr import compute_efsr_from_rows
from efsr.stats.plotting import plot_per_project_efsr
from efsr.stats.predictors import build_predictor_frame, fit_l1_logistic


def table_i(rows: list[dict]) -> pd.DataFrame:
    processes = sorted({r["process"] for r in rows})
    records = []
    for process in processes:
        gen = sum(1 for r in rows if r["process"] == process)
        result = compute_efsr_from_rows(rows, process)
        records.append({
            "Process": process,
            "Gen.": gen,
            "Protocol-pass": result.denom,
            "Diverg.": result.diverge_count,
            "EFSR": f"{result.p_hat:.3f}",
            "95% CI": f"[{result.ci_low:.3f}, {result.ci_high:.3f}]",
        })
    return pd.DataFrame.from_records(records)


def table_ii(rows: list[dict]) -> tuple[pd.DataFrame, dict]:
    X, y = build_predictor_frame(rows)
    columns = ["Retained predictor", "Coefficient", "Odds ratio", "95% CI"]
    if X.empty or len(set(y.tolist())) < 2:
        return pd.DataFrame(columns=columns), {}
    fit = fit_l1_logistic(X, y, DEFAULT_CONFIG)
    records = [
        {"Retained predictor": r.name, "Coefficient": round(r.coefficient, 4),
         "Odds ratio": round(r.odds_ratio, 4),
         "95% CI": f"[{r.ci_low:.3f}, {r.ci_high:.3f}]"}
        for r in fit.retained
    ]
    records.append({"Retained predictor": "EPV achieved", "Coefficient": "",
                     "Odds ratio": round(fit.epv_achieved, 2), "95% CI": ""})
    summary = {
        "n_events": fit.n_events, "n_observations": fit.n_observations,
        "exploratory_only": fit.exploratory_only,
        "dropped_for_multicollinearity": fit.dropped_for_multicollinearity,
    }
    return pd.DataFrame.from_records(records), summary


def taxonomy_distribution(rows: list[dict]) -> pd.DataFrame:
    diverged = [r for r in rows if r.get("verdict") == "DIVERGE"]
    df = pd.DataFrame(diverged)
    if df.empty:
        return pd.DataFrame(columns=["process", "taxonomy_category", "count"])
    return df.groupby(["process", "taxonomy_category"]).size().reset_index(name="count")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CONFIG.results_csv)
    parser.add_argument("--out", type=Path, default=DEFAULT_CONFIG.results_dir / "tables")
    args = parser.parse_args()

    rows = ResultsStore(args.csv).read_all()
    if not rows:
        print(f"No rows found in {args.csv}; run scripts/run_pipeline.py first.")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)

    t1 = table_i(rows)
    print("\nTABLE I -- Empirical False Safety Rate by Refactoring Process\n")
    print(t1.to_string(index=False))
    t1.to_csv(args.out / "table_i_efsr_by_process.csv", index=False)

    processes = sorted({r["process"] for r in rows})
    if len(processes) >= 2:
        comparisons = compare_processes(rows, processes)
        print("\nRQ2 -- Pairwise between-process comparisons (Mann-Whitney U, Bonferroni-corrected)\n")
        for c in comparisons:
            print(f"  {c.process_a} vs {c.process_b}: U={c.statistic:.2f} p={c.p_value:.4f} "
                  f"p_bonf={c.p_value_bonferroni:.4f} delta={c.cliffs_delta:.3f} "
                  f"significant={c.significant}")

    if processes:
        fig1_path = args.out / "fig1_per_project_efsr.png"
        plot_per_project_efsr(rows, processes, fig1_path)
        print(f"\nFig. 1 written to {fig1_path}")

    t2, summary = table_ii(rows)
    print("\nTABLE II -- Retained Structural Predictors of Detectable Divergence\n")
    print(t2.to_string(index=False) if not t2.empty else "(insufficient data to fit a predictor model)")
    if summary:
        print(f"\n  events={summary['n_events']} observations={summary['n_observations']} "
              f"exploratory_only={summary['exploratory_only']} "
              f"dropped_for_multicollinearity={summary['dropped_for_multicollinearity']}")
    t2.to_csv(args.out / "table_ii_predictors.csv", index=False)

    tax = taxonomy_distribution(rows)
    print("\nDivergence Taxonomy Distribution\n")
    print(tax.to_string(index=False) if not tax.empty else "(no confirmed divergences yet)")
    tax.to_csv(args.out / "taxonomy_distribution.csv", index=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
