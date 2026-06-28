"""RQ3 / Section III-H, IV eq. (4): structural predictors of divergence.

    P(y(T)=1 | x) = 1 / (1 + exp(-(b0 + b^T x))),  b = argmin[ -loglik(b) + lambda||b||_1 ]

y(T) = 1 iff div(T) = DIVERGE. x is the candidate structural-metric panel
(CC, WMC, Ce, CBO, RFC, LCOM, DIT, LOC) measured on the pre-transformation
target. The L1 penalty is selected by cross-validation (LogisticRegressionCV),
and a variance-inflation-factor check flags multicollinearity among the
candidate predictors before fitting.

Section III-I pre-specifies an events-per-variable (EPV) floor: the number
of detected divergences (events) must be at least `min_epv` times the
number of *retained* predictors, or the model is reported as exploratory
only rather than as a confirmatory finding.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegressionCV
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.outliers_influence import variance_inflation_factor

from efsr.config import PipelineConfig, DEFAULT_CONFIG
from efsr.metrics.types import StructuralMetrics

CANDIDATE_PREDICTORS = list(StructuralMetrics.PREDICTOR_NAMES)


@dataclass
class PredictorRow:
    name: str
    coefficient: float
    odds_ratio: float
    ci_low: float
    ci_high: float


@dataclass
class PredictorModelResult:
    retained: list[PredictorRow]
    n_events: int
    n_observations: int
    epv_achieved: float
    epv_required: int
    exploratory_only: bool
    vif: dict[str, float]
    dropped_for_multicollinearity: list[str]


def variance_inflation(df: pd.DataFrame, vif_threshold: float = 10.0) -> tuple[dict[str, float], list[str]]:
    """VIF per candidate predictor; predictors with VIF above the threshold
    are flagged for exclusion before fitting the penalised model.
    """
    X = df.copy()
    X.insert(0, "_const", 1.0)
    vifs = {}
    for i, col in enumerate(X.columns):
        if col == "_const":
            continue
        vifs[col] = float(variance_inflation_factor(X.values, i))
    dropped = [col for col, v in vifs.items() if v > vif_threshold]
    return vifs, dropped


def _refit_unpenalised_for_inference(
    X: pd.DataFrame, X_scaled: np.ndarray, y: np.ndarray,
    all_columns: list[str], selected_names: list[str],
) -> list[PredictorRow]:
    """Relaxed-LASSO-style inference: L1 selects which predictors matter
    (above, in fit_l1_logistic); this refits an *unpenalised* logistic
    regression restricted to exactly those predictors to get unbiased
    coefficients and Wald confidence intervals -- LogisticRegressionCV's
    shrunk coefficients have no closed-form standard error, so they cannot
    support the "Coefficient / Odds ratio / 95% CI" columns Table II
    requires on their own.
    """
    if not selected_names:
        return []

    selected_idx = [all_columns.index(name) for name in selected_names]
    X_selected = sm.add_constant(X_scaled[:, selected_idx])

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            refit = sm.Logit(y, X_selected).fit(disp=0, maxiter=200)
    except Exception:
        # Perfect separation or non-convergence on the selected subset --
        # report the predictor as retained (by L1) but without inferential
        # CIs rather than fabricating a number.
        return [
            PredictorRow(name=name, coefficient=float("nan"), odds_ratio=float("nan"),
                          ci_low=float("nan"), ci_high=float("nan"))
            for name in selected_names
        ]

    params = refit.params[1:]  # drop the intercept
    conf_int = refit.conf_int(alpha=0.05)[1:]

    rows = []
    for name, coef, (ci_lo, ci_hi) in zip(selected_names, params, conf_int):
        rows.append(PredictorRow(
            name=name, coefficient=float(coef), odds_ratio=float(np.exp(coef)),
            ci_low=float(np.exp(ci_lo)), ci_high=float(np.exp(ci_hi)),
        ))
    return rows


def fit_l1_logistic(
    df: pd.DataFrame,
    y: np.ndarray,
    config: PipelineConfig = DEFAULT_CONFIG,
    vif_threshold: float = 10.0,
) -> PredictorModelResult:
    """Fit the cross-validated L1-penalised logistic model of eq. (4).

    `df` columns must be a subset of CANDIDATE_PREDICTORS; rows with any
    missing value are dropped prior to fitting.
    """
    df = df[[c for c in CANDIDATE_PREDICTORS if c in df.columns]].copy()
    y = np.asarray(y)
    if len(y) != len(df):
        raise ValueError(f"y has {len(y)} entries but df has {len(df)} rows; must be row-aligned")
    keep_mask = ~df.isna().any(axis=1)
    complete = df[keep_mask]
    y = y[keep_mask.to_numpy()]
    n_obs = len(complete)
    n_events = int(np.sum(y))

    vifs, dropped = variance_inflation(complete, vif_threshold) if n_obs > len(complete.columns) else ({}, [])
    retained_columns = [c for c in complete.columns if c not in dropped]
    X = complete[retained_columns]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X.values)

    model = LogisticRegressionCV(
        Cs=10, cv=min(5, max(2, n_events)) if n_events >= 2 else 2,
        penalty="l1", solver="liblinear", scoring="neg_log_loss",
        max_iter=5000, random_state=config.generation_seed,
    )
    model.fit(X_scaled, y)

    selected_names = [name for name, coef in zip(retained_columns, model.coef_[0]) if abs(coef) >= 1e-8]
    retained_rows = _refit_unpenalised_for_inference(X, X_scaled, y, retained_columns, selected_names)

    n_retained = len(retained_rows)
    epv_achieved = n_events / n_retained if n_retained else float("inf")
    exploratory_only = n_retained > 0 and epv_achieved < config.min_events_per_variable

    return PredictorModelResult(
        retained=retained_rows, n_events=n_events, n_observations=n_obs,
        epv_achieved=epv_achieved, epv_required=config.min_events_per_variable,
        exploratory_only=exploratory_only, vif=vifs, dropped_for_multicollinearity=dropped,
    )


def build_predictor_frame(rows: list[dict]) -> tuple[pd.DataFrame, np.ndarray]:
    """Build the (X, y) pair for fitting from ResultsStore rows.

    Only rows admitted to Pi(S) and not a priori excluded are eligible
    (matching the EFSR denominator); y = 1 iff verdict == DIVERGE.
    """
    from efsr.stats.efsr import _retained, _to_bool

    eligible = [
        r for r in rows
        if _to_bool(r.get("admitted")) and _retained(r) and not _to_bool(r.get("excluded_nondeterministic"))
        and r.get("verdict") != "ERROR"
    ]
    df = pd.DataFrame(eligible)
    for col in CANDIDATE_PREDICTORS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    y = (df.get("verdict") == "DIVERGE").astype(int).to_numpy() if not df.empty else np.array([])
    return df[[c for c in CANDIDATE_PREDICTORS if c in df.columns]], y
