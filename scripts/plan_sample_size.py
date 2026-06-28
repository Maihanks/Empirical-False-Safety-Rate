#!/usr/bin/env python3
"""Section III-I: compute the minimum per-process corpus size from a pilot
divergence rate, before committing to the full-scale corpus.

Usage:
  uv run python scripts/plan_sample_size.py --pilot-rate 0.15 --margin 0.09
  uv run python scripts/plan_sample_size.py --pilot-rate 0.15 --margin 0.09 \
      --comparison-effect-size 0.4 --comparison-power 0.8
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from efsr.config import DEFAULT_CONFIG
from efsr.stats.power import required_n_for_mannwhitney_power, required_sample_size_for_efsr_precision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-rate", type=float, required=True,
                         help="pilot estimate of EFSR(S), e.g. from a small initial run")
    parser.add_argument("--margin", type=float, required=True,
                         help="target Wilson 95%% CI half-width (e.g. 0.09 for +/-9pp)")
    parser.add_argument("--comparison-effect-size", type=float, default=None,
                         help="optional: also size the corpus for an RQ2 Mann-Whitney comparison")
    parser.add_argument("--comparison-power", type=float, default=0.8)
    args = parser.parse_args()

    precision = required_sample_size_for_efsr_precision(args.pilot_rate, args.margin, DEFAULT_CONFIG)
    print(f"Precision target: Wilson 95% CI half-width <= {args.margin} at pilot rate {args.pilot_rate}")
    print(f"  -> requires |Pi(S)| >= {precision.required_n} "
          f"(achieved half-width {precision.achieved_half_width:.4f})")

    if args.comparison_effect_size is not None:
        comparison = required_n_for_mannwhitney_power(
            effect_size=args.comparison_effect_size, power_target=args.comparison_power,
        )
        print(f"\nComparison target: Mann-Whitney power >= {args.comparison_power} "
              f"at effect size {args.comparison_effect_size}")
        print(f"  -> requires >= {comparison.required_n_per_group} per-project rate observations per process")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
