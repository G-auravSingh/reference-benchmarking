"""
Statistical Comparison
======================

Methods for comparing site indicator values against reference distributions.

Implements:
    - Intactness Ratio: site_value / reference_value, bounded [0, 1]
    - Hedges' g effect size with 95% CI (bias-corrected for small samples)
    - Bootstrap confidence intervals for intactness ratios (BCa method)
    - Permutation tests for difference in means

References
----------
Cohen, J. (1988). Statistical Power Analysis for the Behavioral Sciences
    (2nd ed.). Lawrence Erlbaum Associates.

Hedges, L.V. (1981). Distribution Theory for Glass's Estimator of Effect
    Size. Journal of Educational Statistics, 6(2), 107–128.

Davison, A.C. & Hinkley, D.V. (1998). Bootstrap Methods and Their
    Application. Cambridge University Press.

Manly, B.F.J. (1997). Randomization, Bootstrap and Monte Carlo Methods
    in Biology (2nd ed.). Chapman and Hall.

Anderson, M.J. (2001). A new method for non-parametric multivariate
    analysis of variance. Austral Ecology, 26, 32–46.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

from darukaa_reference.config import Config
from darukaa_reference.reference import ReferenceResult

logger = logging.getLogger(__name__)


@dataclass
class ComparisonResult:
    """Full statistical comparison for one indicator at one site."""

    indicator_name: str
    site_id: str

    # Raw values
    site_value: Optional[float] = None
    tier1_reference: Optional[float] = None
    tier2_reference: Optional[float] = None

    # Intactness ratios
    tier1_intactness: Optional[float] = None
    tier2_intactness: Optional[float] = None

    # Hedges' g (site vs Tier 2 reference pixels)
    hedges_g: Optional[float] = None
    hedges_g_ci: Optional[Tuple[float, float]] = None

    # Bootstrap CI for intactness ratio
    intactness_bootstrap_ci: Optional[Tuple[float, float]] = None

    # Permutation test
    permutation_p_value: Optional[float] = None
    permutation_diff: Optional[float] = None

    # Interpretation
    interpretation: str = ""

    metadata: Dict = field(default_factory=dict)


class StatisticalComparison:
    """
    Compare site values against reference distributions.

    Usage::

        stats = StatisticalComparison(config)
        comparison = stats.compare(reference_result)
    """

    def __init__(self, config: Config):
        self.config = config
        self.rng = np.random.default_rng(config.random_seed)

    def compare(self, ref_result: ReferenceResult) -> ComparisonResult:
        """
        Run full statistical comparison for a single indicator × site.

        Parameters
        ----------
        ref_result : ReferenceResult
            Output from ReferenceSelector.compute()

        Returns
        -------
        ComparisonResult
        """
        comp = ComparisonResult(
            indicator_name=ref_result.indicator_name,
            site_id=ref_result.site_id,
            site_value=ref_result.site_value,
            tier1_reference=ref_result.tier1_median,
            tier2_reference=ref_result.tier2_median,
            tier1_intactness=ref_result.tier1_intactness,
            tier2_intactness=ref_result.tier2_intactness,
        )

        # If we have pixel-level data for both site and reference
        site_pixels = ref_result.site_pixels
        ref_pixels = ref_result.tier2_pixels

        if site_pixels is not None and ref_pixels is not None:
            site_arr = np.array(site_pixels, dtype=float)
            ref_arr = np.array(ref_pixels, dtype=float)

            # Clean arrays
            site_arr = site_arr[np.isfinite(site_arr)]
            ref_arr = ref_arr[np.isfinite(ref_arr)]

            if len(site_arr) >= 3 and len(ref_arr) >= 3:
                # Hedges' g
                hg = self.hedges_g(site_arr, ref_arr)
                comp.hedges_g = hg["g"]
                comp.hedges_g_ci = hg["ci"]

                # Bootstrap intactness
                bi = self.bootstrap_intactness(site_arr, ref_arr)
                comp.intactness_bootstrap_ci = bi["ci"]

                # Permutation test
                pt = self.permutation_test(site_arr, ref_arr)
                comp.permutation_p_value = pt["p_value"]
                comp.permutation_diff = pt["diff"]

        # Interpretation
        comp.interpretation = self._interpret(comp)

        return comp

    def hedges_g(
        self, site: np.ndarray, ref: np.ndarray
    ) -> Dict[str, any]:
        """
        Compute Hedges' g effect size with 95% CI.

        Hedges' g corrects the upward bias (~4%) in Cohen's d for small samples
        using the correction factor J = 1 - 3/(4(n1+n2) - 9).

        Interpretation (Cohen 1988):
            |g| < 0.2 = negligible
            0.2 ≤ |g| < 0.5 = small
            0.5 ≤ |g| < 0.8 = medium
            |g| ≥ 0.8 = large

        Reference: Hedges, L.V. (1981). JESS, 6(2), 107–128.
        """
        n1, n2 = len(site), len(ref)
        if n1 < 2 or n2 < 2:
            return {"g": None, "ci": None}

        # Pooled standard deviation
        var1 = np.var(site, ddof=1)
        var2 = np.var(ref, ddof=1)
        pooled_sd = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

        if pooled_sd == 0:
            return {"g": 0.0, "ci": (0.0, 0.0)}

        # Cohen's d
        d = (np.mean(site) - np.mean(ref)) / pooled_sd

        # Hedges' correction factor
        J = 1 - 3 / (4 * (n1 + n2) - 9)
        g = d * J

        # Standard error of g
        se = np.sqrt((n1 + n2) / (n1 * n2) + g ** 2 / (2 * (n1 + n2)))

        alpha = 1 - self.config.confidence_level
        from scipy import stats as sp_stats

        z = sp_stats.norm.ppf(1 - alpha / 2)
        ci = (g - z * se, g + z * se)

        return {"g": float(g), "ci": (float(ci[0]), float(ci[1]))}

    def bootstrap_intactness(
        self, site: np.ndarray, ref: np.ndarray
    ) -> Dict[str, any]:
        """
        Bootstrap confidence interval for the intactness ratio.

        Intactness Ratio = mean(site) / mean(reference), bounded [0, 1].
        Uses BCa-like approach with percentile method.

        Reference: Davison & Hinkley (1998). Bootstrap Methods. CUP.
        """
        n_boot = self.config.bootstrap_iterations
        observed = np.mean(site) / np.mean(ref) if np.mean(ref) != 0 else None

        if observed is None:
            return {"ratio": None, "ci": None}

        boot_ratios = np.empty(n_boot)
        for i in range(n_boot):
            s_boot = self.rng.choice(site, size=len(site), replace=True)
            r_boot = self.rng.choice(ref, size=len(ref), replace=True)
            r_mean = np.mean(r_boot)
            if r_mean != 0:
                boot_ratios[i] = np.mean(s_boot) / r_mean
            else:
                boot_ratios[i] = np.nan

        boot_ratios = boot_ratios[np.isfinite(boot_ratios)]
        alpha = 1 - self.config.confidence_level
        ci = (
            float(np.percentile(boot_ratios, 100 * alpha / 2)),
            float(np.percentile(boot_ratios, 100 * (1 - alpha / 2))),
        )

        return {"ratio": float(min(observed, 1.0)), "ci": ci}

    def permutation_test(
        self, site: np.ndarray, ref: np.ndarray
    ) -> Dict[str, any]:
        """
        Two-sided permutation test for difference in means.

        Tests H0: mean(site) = mean(reference).
        Distribution-free; preferred in ecology when parametric assumptions
        may be violated.

        Reference: Manly (1997). Randomization, Bootstrap and Monte Carlo
        Methods in Biology (2nd ed.). Chapman and Hall.
        """
        n_perm = self.config.permutation_iterations
        obs_diff = np.mean(site) - np.mean(ref)
        combined = np.concatenate([site, ref])
        n_site = len(site)

        count_extreme = 0
        for _ in range(n_perm):
            perm = self.rng.permutation(combined)
            perm_diff = np.mean(perm[:n_site]) - np.mean(perm[n_site:])
            if abs(perm_diff) >= abs(obs_diff):
                count_extreme += 1

        p_value = count_extreme / n_perm

        return {"diff": float(obs_diff), "p_value": float(p_value)}

    def _interpret(self, comp: ComparisonResult) -> str:
        """Generate human-readable interpretation."""
        parts = []

        if comp.tier2_intactness is not None:
            ratio = comp.tier2_intactness
            if ratio >= 0.9:
                parts.append(f"Near-reference condition ({ratio:.1%} of Tier 2 benchmark)")
            elif ratio >= 0.7:
                parts.append(f"Moderate intactness ({ratio:.1%} of Tier 2 benchmark)")
            elif ratio >= 0.5:
                parts.append(f"Degraded ({ratio:.1%} of Tier 2 benchmark)")
            else:
                parts.append(f"Severely degraded ({ratio:.1%} of Tier 2 benchmark)")

        if comp.hedges_g is not None:
            g = abs(comp.hedges_g)
            direction = "below" if comp.hedges_g < 0 else "above"
            if g < 0.2:
                parts.append(f"negligible difference from reference (g={comp.hedges_g:.2f})")
            elif g < 0.5:
                parts.append(f"small difference {direction} reference (g={comp.hedges_g:.2f})")
            elif g < 0.8:
                parts.append(f"medium difference {direction} reference (g={comp.hedges_g:.2f})")
            else:
                parts.append(f"large difference {direction} reference (g={comp.hedges_g:.2f})")

        if comp.permutation_p_value is not None:
            if comp.permutation_p_value < 0.05:
                parts.append(f"statistically significant (p={comp.permutation_p_value:.4f})")
            else:
                parts.append(f"not statistically significant (p={comp.permutation_p_value:.4f})")

        return "; ".join(parts) if parts else "Insufficient data for interpretation"
