"""General reference-selection policy shared across ecosystem realms.

The policy is deliberately finite and separates two jobs:

* ecological eligibility: determine whether a candidate belongs to the same
  ecological reference population; and
* disturbance ordering: among eligible candidates, retain the least-disturbed
  contemporary population using HMI.

HMI is therefore never allowed to compensate for ecological mismatch, and an
arbitrary weighted ecological-vs-HMI score is not used to select a winner.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ReferenceProfile:
    name: str
    realm: str
    ecological_gate: str
    pressure_variable: str = "hmi"
    default_reference_state: str = "least_disturbed_contemporary"
    supports_manual_hmi_fallback: bool = True


AQUATIC_LAKE_PROFILE = ReferenceProfile(
    name="aquatic_lake",
    realm="aquatic",
    ecological_gate="ecoregion + hydrological_regime",
)

TERRESTRIAL_PROFILE = ReferenceProfile(
    name="terrestrial",
    realm="terrestrial",
    ecological_gate="ecoregion + habitat_stratum",
)

MIXED_PROFILE = ReferenceProfile(
    name="mixed",
    realm="mixed",
    ecological_gate="separate_domain_specific_reference_populations",
)


class ReferenceSelectionPolicy:
    """Finite decision contract for contemporary reference selection.

    There are exactly three possible contemporary stages:

    1. strict low-pressure;
    2. least-disturbed contemporary (configured HMI quantile);
    3. one explicitly configured manual HMI threshold.

    Ecological eligibility is a gate at every stage. The policy never trades
    ecological mismatch against lower HMI through a weighted score.
    """

    STAGES = (
        "strict_low_pressure",
        "least_disturbed_quantile",
        "manual_hmi_threshold",
    )

    def __init__(self, config):
        self.config = config

    def stage_plan(self):
        plan = [
            {
                "stage": self.STAGES[0],
                "enabled": bool(self.config.reference.automatic_enabled),
                "threshold_source": "configured_strict_hmi_threshold",
                "reference_state": "least_disturbed_contemporary",
            },
            {
                "stage": self.STAGES[1],
                "enabled": bool(self.config.reference.automatic_enabled and self.config.reference.least_disturbed_enabled),
                "threshold_source": "empirical_low_hmi_quantile_within_ecologically_eligible_population",
                "reference_state": "least_disturbed_contemporary",
            },
            {
                "stage": self.STAGES[2],
                "enabled": bool(self.config.reference.manual_hmi_fallback_enabled and self.config.reference.manual_hmi_threshold is not None),
                "threshold_source": "explicit_colab_hmi_threshold",
                "reference_state": self.config.reference.manual_hmi_reference_state,
            },
        ]
        return plan

    @staticmethod
    def ecological_gate_diagnostics(*, profile: ReferenceProfile, passed: bool,
                                    rule: str, components: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "reference_profile": profile.name,
            "reference_realm": profile.realm,
            "ecological_eligibility_rule": rule,
            "ecological_eligibility_pass": bool(passed),
            "ecological_match_score_used_for_selection": False,
            "ecological_hmi_tradeoff_used": False,
            "ecological_gate_components": components or {},
        }

    def terminal_status(self, population, strict, least=None, manual=None):
        """Annotate a terminal rejected population without adding another stage."""
        d = dict(population.diagnostics or {})
        d.update({
            "strict_candidate_status": getattr(strict, "status", None),
            "least_disturbed_candidate_status": getattr(least, "status", None) if least is not None else None,
            "manual_candidate_status": getattr(manual, "status", None) if manual is not None else None,
            "finite_reference_selection": True,
            "reference_selection_terminal": True,
            "reference_selection_next_stage": None,
        })
        population.status = "candidate_rejected_reference_unavailable"
        population.diagnostics = d
        return population
