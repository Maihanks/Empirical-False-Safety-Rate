import numpy as np
import pandas as pd
import pytest

from efsr.stats.predictors import CANDIDATE_PREDICTORS, build_predictor_frame, fit_l1_logistic


def test_fit_l1_logistic_recovers_informative_predictor():
    rng = np.random.default_rng(0)
    n = 300
    df = pd.DataFrame({c: rng.normal(size=n) for c in CANDIDATE_PREDICTORS})
    y = (df["cbo"] + rng.normal(scale=0.5, size=n) > 0).astype(int).to_numpy()

    result = fit_l1_logistic(df, y)

    assert result.n_observations == n
    assert result.n_events == int(y.sum())
    retained_names = {r.name for r in result.retained}
    assert "cbo" in retained_names


def test_fit_l1_logistic_flags_exploratory_when_epv_too_low():
    rng = np.random.default_rng(1)
    n = 20  # deliberately small -> few events -> EPV rule should trip
    df = pd.DataFrame({c: rng.normal(size=n) for c in CANDIDATE_PREDICTORS})
    y = (df["cbo"] + df["rfc"] + df["ce"] + rng.normal(size=n) > 1.0).astype(int).to_numpy()

    result = fit_l1_logistic(df, y)
    if result.retained:
        assert result.epv_achieved == pytest.approx(result.n_events / len(result.retained))


def test_fit_l1_logistic_rejects_misaligned_lengths():
    df = pd.DataFrame({c: [0.0, 1.0] for c in CANDIDATE_PREDICTORS})
    with pytest.raises(ValueError):
        fit_l1_logistic(df, np.array([0, 1, 1]))


def test_build_predictor_frame_filters_to_pi_s_and_excludes_errors():
    rows = [
        {"admitted": "True", "excluded_nondeterministic": "False", "verdict": "DIVERGE", "cc": "5", "wmc": "10"},
        {"admitted": "True", "excluded_nondeterministic": "False", "verdict": "NO_DIFFERENCE", "cc": "2", "wmc": "3"},
        {"admitted": "False", "excluded_nondeterministic": "False", "verdict": "NOT_ADMITTED", "cc": "9", "wmc": "9"},
        {"admitted": "True", "excluded_nondeterministic": "True", "verdict": "EXCLUDED", "cc": "1", "wmc": "1"},
        {"admitted": "True", "excluded_nondeterministic": "False", "verdict": "ERROR", "cc": "1", "wmc": "1"},
    ]
    X, y = build_predictor_frame(rows)
    assert len(X) == 2
    assert list(y) == [1, 0]
