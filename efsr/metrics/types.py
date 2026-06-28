"""The structural-metric panel used for metric(T) and the RQ3 predictor model.

Field names follow the Chidamber & Kemerer suite plus size/complexity
measures named in Section III-H of the draft: CC, WMC, Ce, CBO, RFC, LCOM,
DIT, LOC.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class StructuralMetrics:
    cc: Optional[float] = None     # cyclomatic complexity (of the target method, for Extract Method)
    wmc: Optional[float] = None    # weighted methods per class
    ce: Optional[float] = None     # efferent coupling
    cbo: Optional[float] = None    # coupling between objects
    rfc: Optional[float] = None    # response for a class
    lcom: Optional[float] = None   # lack of cohesion of methods
    dit: Optional[float] = None    # depth of inheritance tree
    loc: Optional[float] = None    # lines of code
    nom: Optional[float] = None    # number of declared methods (metric(T) gate only, not an RQ3 predictor)

    def as_dict(self) -> dict:
        return {
            "cc": self.cc, "wmc": self.wmc, "ce": self.ce, "cbo": self.cbo,
            "rfc": self.rfc, "lcom": self.lcom, "dit": self.dit, "loc": self.loc,
            "nom": self.nom,
        }

    # The RQ3 candidate predictor panel (Section III-H) is fixed to exactly
    # these eight; `nom` is deliberately excluded -- it exists only to
    # support the metric(T) method-count gate in Section III-B.
    PREDICTOR_NAMES = ("cc", "wmc", "ce", "cbo", "rfc", "lcom", "dit", "loc")
