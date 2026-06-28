"""Section V-B / Fig. 1: per-project EFSR distributions as box plots.

Uses the Agg backend explicitly so this runs headless (CI machines,
servers without a display) -- matplotlib must not try to open a GUI
window when this module is imported.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from efsr.stats.compare import per_project_rates


def plot_per_project_efsr(rows: list[dict], processes: list[str], out_path) -> None:
    """Box plot of per-project EFSR rates, one box per process (Fig. 1).

    Each box summarises the distribution of per-project EFSR(S) values for
    one process across the corpus's constituent projects -- the same data
    `efsr.stats.compare.compare_processes` tests pairwise.
    """
    data = []
    labels = []
    for process in processes:
        rates = list(per_project_rates(rows, process).values())
        if not rates:
            continue
        data.append(rates)
        labels.append(process)

    fig, ax = plt.subplots(figsize=(max(4, 1.2 * len(labels)), 5))
    if data:
        ax.boxplot(data, tick_labels=labels, showmeans=True)
    ax.set_ylabel("Per-project EFSR")
    ax.set_xlabel("Process")
    ax.set_title("Per-project EFSR by process")
    ax.set_ylim(-0.02, 1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
