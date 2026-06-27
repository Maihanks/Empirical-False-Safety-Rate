"""EFSR: measurement pipeline for the Empirical False Safety Rate.

Implements the Stage 0-9 protocol described in the project methodology:
three-check protocol admission (compile, tests, metric), non-determinism
screening, differential test generation (EvoSuite regression mode +
Randoop), replay/confirmation, divergence taxonomy classification, and
EFSR aggregation with Wilson confidence intervals.
"""

__version__ = "0.1.0"
