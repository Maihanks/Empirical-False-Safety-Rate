from efsr.stats.plotting import plot_per_project_efsr


def _row(process, project, verdict):
    return {
        "process": process, "target_id": f"{project}:X#a",
        "admitted": "True", "excluded_nondeterministic": "False", "verdict": verdict,
    }


def test_plot_per_project_efsr_writes_a_png(tmp_path):
    rows = [
        _row("LLM-A", "p1", "DIVERGE"), _row("LLM-A", "p1", "NO_DIFFERENCE"),
        _row("LLM-A", "p2", "DIVERGE"), _row("LLM-A", "p2", "DIVERGE"),
        _row("JDeodorant", "p1", "NO_DIFFERENCE"), _row("JDeodorant", "p2", "NO_DIFFERENCE"),
    ]
    out = tmp_path / "fig1.png"
    plot_per_project_efsr(rows, ["LLM-A", "JDeodorant"], out)
    assert out.is_file()
    assert out.stat().st_size > 0


def test_plot_per_project_efsr_handles_process_with_no_data(tmp_path):
    rows = [_row("LLM-A", "p1", "DIVERGE")]
    out = tmp_path / "fig1.png"
    plot_per_project_efsr(rows, ["LLM-A", "Empty-Process"], out)
    assert out.is_file()
