import pytest

from efsr.stats.power import (
    required_n_for_mannwhitney_power,
    required_sample_size_for_efsr_precision,
)


def test_required_sample_size_matches_worked_example():
    # Worked example: p_hat=0.15, n=60 -> Wilson half-width ~ (26-8)/2 = 9pp.
    result = required_sample_size_for_efsr_precision(0.15, 0.09)
    assert result.required_n == pytest.approx(60, abs=2)
    assert result.achieved_half_width <= 0.09


def test_required_sample_size_smaller_margin_needs_more_n():
    loose = required_sample_size_for_efsr_precision(0.15, 0.09)
    tight = required_sample_size_for_efsr_precision(0.15, 0.03)
    assert tight.required_n > loose.required_n


def test_required_sample_size_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        required_sample_size_for_efsr_precision(1.5, 0.05)
    with pytest.raises(ValueError):
        required_sample_size_for_efsr_precision(0.15, 0.0)


def test_required_sample_size_unreachable_margin_raises():
    with pytest.raises(ValueError):
        required_sample_size_for_efsr_precision(0.5, 0.001, max_n=50)


def test_mannwhitney_power_increases_required_n_as_effect_shrinks():
    # Larger effect size should need fewer observations to detect.
    big_effect = required_n_for_mannwhitney_power(
        effect_size=0.6, power_target=0.8, n_simulations=200, max_n_per_group=80, random_state=1,
    )
    small_effect = required_n_for_mannwhitney_power(
        effect_size=0.2, power_target=0.8, n_simulations=200, max_n_per_group=80, random_state=1,
    )
    assert small_effect.required_n_per_group >= big_effect.required_n_per_group


def test_mannwhitney_power_unreachable_raises():
    with pytest.raises(ValueError):
        required_n_for_mannwhitney_power(
            effect_size=0.01, power_target=0.99, n_simulations=50, max_n_per_group=5,
        )
