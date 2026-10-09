from darukaa_adaptive.registry import INDICATORS
from darukaa_adaptive.legacy_reference.indicators import _annualized_rate_pct


def _spec(name):
    return next(x for x in INDICATORS if x.name == name)


def test_forest_loss_windows_use_inclusive_year_counts():
    # 2001-2025 inclusive = 25 annual observations; the package must not divide by 24.
    assert round(_annualized_rate_pct(25.0, 100.0, 25), 6) == 1.0
    assert round(_annualized_rate_pct(6.0, 100.0, 6), 6) == 1.0
    assert round(_annualized_rate_pct(3.0, 100.0, 3), 6) == 1.0


def test_pressure_metrics_are_separate_from_condition_axis():
    for name in ("ghm", "light_pollution", "built_fraction"):
        assert _spec(name).pillar == "P4_pressure"


def test_scoreable_aquatic_metrics_are_runtime_score_selectable():
    from darukaa_adaptive.registry import metric_scoreability
    for name in ("water_extent", "water_persistence", "riparian_ndvi", "shoreline_disturbance_fraction"):
        assert metric_scoreability(_spec(name)) == "default_scored"
    for name in ("ndci_proxy", "surface_algal_bloom_frequency", "shdi"):
        assert metric_scoreability(_spec(name)) == "context_only"


def test_bii_and_flii_have_explicit_scientific_gates():
    assert _spec("bii").scoring_role == "SCORED"
    assert _spec("bii").reference_estimator == "robust_z"
    assert _spec("flii").scoring_role == "SCORED"
    assert _spec("flii").reference_estimator == "robust_z"


def test_chm_uses_meta_wri_primary_product_contract():
    spec = _spec("chm")
    assert spec.scoring_role == "SCORED"
    assert spec.native_scale_m == 1.0
    assert "meta_wri_canopy_height" in spec.input_layers
    assert "meta-forest-monitoring-okw37/assets/CanopyHeight" in spec.source_type


def test_eii_parent_and_components_are_mutually_exclusive():
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.registry import effective_scoring_role
    cfg = AssessmentConfig()
    cfg.scoring.eii_mode = "components"
    assert effective_scoring_role(_spec("eii"), cfg) == "CONTEXTUAL"
    for name in ("eii_structural", "eii_compositional", "eii_functional"):
        assert effective_scoring_role(_spec(name), cfg) == "SCORED"

    cfg.scoring.eii_mode = "parent"
    assert effective_scoring_role(_spec("eii"), cfg) == "SCORED"
    for name in ("eii_structural", "eii_compositional", "eii_functional"):
        assert effective_scoring_role(_spec(name), cfg) == "CONTEXTUAL"

    cfg.scoring.eii_mode = "none"
    for name in ("eii","eii_structural","eii_compositional","eii_functional"):
        assert effective_scoring_role(_spec(name), cfg) == "CONTEXTUAL"


def test_bii_is_independent_of_eii_compositional_source():
    spec = _spec("bii")
    assert "BII_V1_1" in spec.source_type
    assert "landbanking_eii" not in spec.input_layers


def test_eii_override_cannot_bypass_hierarchy_gate():
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.registry import effective_scoring_role
    cfg = AssessmentConfig()
    cfg.scoring.eii_mode = "components"
    cfg.scoring.metric_overrides = {"eii": "scored"}
    assert effective_scoring_role(_spec("eii"), cfg) == "CONTEXTUAL"

    cfg.scoring.eii_mode = "parent"
    cfg.scoring.metric_overrides = {"eii_structural": "scored"}
    assert effective_scoring_role(_spec("eii_structural"), cfg) == "CONTEXTUAL"


def test_active_legacy_inventory_excludes_retired_metrics():
    from darukaa_adaptive.registry import FULL_INDICATORS, INDICATORS
    names = [x.name for x in FULL_INDICATORS]
    all_names = {x.name for x in INDICATORS}
    assert len(names) == len(set(names))
    assert len(names) < 46
    for retired in ("pdf", "tspi", "wcpi", "wsdi", "hsas", "edpp", "mspl", "rci", "stsi", "iri", "ivsi", "flagship_habitat", "ceri", "hdi", "sdi", "shi", "net_forest_change_rate"):
        assert retired not in all_names


def test_habitat_health_and_eii_parent_are_core_defaults():
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.registry import get_indicator_spec, effective_scoring_role
    cfg = AssessmentConfig()
    assert cfg.scoring.eii_mode == "parent"
    assert effective_scoring_role(get_indicator_spec("eii"), cfg) == "SCORED"
    assert effective_scoring_role(get_indicator_spec("habitat_health"), cfg) == "SCORED"


def test_star_t_requires_canonical_asset_and_is_context_only():
    from darukaa_adaptive.registry import get_indicator_spec, metric_scoreability
    spec = get_indicator_spec("star_t")
    assert metric_scoreability(spec) == "context_only"
    assert "canonical STAR-T data" in spec.contract_note


def test_msa_is_explicitly_modelled_context_not_direct_observation():
    from darukaa_adaptive.registry import get_indicator_spec, metric_scoreability
    spec = get_indicator_spec("msa")
    assert metric_scoreability(spec) == "context_only"
    assert "2015" in spec.contract_note or "2015" in spec.notes or "2015" in spec.citation


def test_temporally_asymmetric_net_tree_cover_proxy_is_retired():
    from darukaa_adaptive.registry import INDICATORS
    assert "net_forest_change_rate" not in {x.name for x in INDICATORS}


def test_pipeline_pressure_filter_uses_explicit_boolean_parentheses():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "darukaa_adaptive" / "pipeline.py"
    text = source.read_text()
    assert '(pillar_agg["pillar"] == "P4_pressure") & (pillar_agg["project_score_0_to_100"].notna())' in text


def test_flii_uses_canonical_asset_and_not_local_reconstruction():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "darukaa_adaptive" / "legacy_reference" / "indicators" / "__init__.py").read_text()
    start = source.index("def _img_flii(c):")
    end = source.index("_EII_LAST_PATH_USED = {}", start)
    builder = source[start:end]
    assert "projects/darukaa-earth-product/assets/flii_global_2019" in builder
    assert "total_pressure" not in builder
    assert "focal_max" not in builder


def test_active_registry_has_no_retired_metric_names():
    from darukaa_adaptive.registry import INDICATORS
    active = {x.name for x in INDICATORS}
    retired = {"pdf", "tspi", "wcpi", "wsdi", "hsas", "edpp", "mspl", "rci", "jrc_water_persistence", "stsi", "iri", "ivsi", "flagship_habitat", "ceri", "hdi", "sdi", "shi", "net_forest_change_rate", "natural_landcover", "natural_landcover_fraction", "terrestrial_ndvi", "red_reflectance_turbidity_proxy", "edna_persistence_potential"}
    assert not (active & retired)


def test_retired_metric_ids_are_blocked_at_registry_boundary():
    from darukaa_adaptive.registry import REMOVED_METRICS, get_indicator_spec, INDICATORS
    active = {spec.name for spec in INDICATORS}
    assert not (active & REMOVED_METRICS)
    for name in ("natural_landcover_fraction", "terrestrial_ndvi", "natural_landcover"):
        try:
            get_indicator_spec(name)
        except KeyError as exc:
            assert "Retired metric" in str(exc)
        else:
            raise AssertionError(f"Retired metric unexpectedly resolved: {name}")


def test_terrestrial_calculator_source_only_emits_active_current_metric():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "darukaa_adaptive" / "terrestrial.py").read_text()
    assert 'self._make("built_fraction"' in source
    assert 'self._make("natural_landcover_fraction"' not in source
    assert 'self._make("terrestrial_ndvi"' not in source


def test_runtime_guard_is_before_metric_qa_scoring_and_reporting():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "darukaa_adaptive" / "pipeline.py").read_text()
    guard = source.index("# Enforce the production registry at the calculator/runtime boundary.")
    qa = source.index("metric_qa=qa_metrics(metric_results)")
    scoring = source.index("build_scorecard(metric_results,benchmarks,self.config)")
    reporting = source.index("write_assessment(")
    assert guard < qa < scoring < reporting
    assert "Calculator emitted unregistered metric" in source


def test_colab_clone_cell_supports_commit_sha_without_git_clone_branch_flag():
    import json
    from pathlib import Path
    notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks" / "Darukaa_Adaptive_Biodiversity_Assessment_Colab.ipynb").read_text())
    source = "\n".join("".join(c.get("source", [])) for c in notebook["cells"])
    assert "def clone_exact_ref" in source
    assert "git_ref,REPO_URL,REPO_DIR" not in source
    assert '"fetch", "--depth", "1", "origin", git_ref' in source
    assert "Pinned repository commit" in source


def test_terrestrial_runtime_no_data_path_does_not_lookup_retired_metrics(monkeypatch):
    """Reproduce the old KeyError path with a no-observation Earth Engine stub."""
    import sys
    from types import SimpleNamespace
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.terrestrial import TerrestrialMetrics

    class _Size:
        def getInfo(self):
            return 0

    class _Collection:
        def filterBounds(self, *_a, **_k): return self
        def filterDate(self, *_a, **_k): return self
        def filter(self, *_a, **_k): return self
        def map(self, *_a, **_k): return self
        def select(self, *_a, **_k): return self
        def size(self): return _Size()

    class _Filter:
        @staticmethod
        def lte(*_a, **_k): return object()

    fake_ee = SimpleNamespace(ImageCollection=lambda *_a, **_k: _Collection(), Filter=_Filter)
    monkeypatch.setitem(sys.modules, "ee", fake_ee)
    result = TerrestrialMetrics(AssessmentConfig()).run(object(), "2025-08-01", "2026-08-01")
    assert [m.metric for m in result] == ["built_fraction"]
    assert result[0].status == "no_valid_observation"


def test_aquatic_runtime_does_not_emit_retired_red_reflectance_metric(monkeypatch):
    from darukaa_adaptive.metrics import LakeMetrics, MetricResult
    from darukaa_adaptive.config import AssessmentConfig

    def fake_metric(name):
        def run(*_args, **_kwargs):
            return MetricResult(name, "P2_ecosystem_condition", "test", "test", "aquatic",
                                None, "", "insufficient_data", "2025:2026", "test", 10,
                                "context_dependent", "EO_proxy", "none", False)
        return run

    class _Water:
        def area_summary(self, *_a, **_k):
            return {"water_fraction_pct": None, "status": "insufficient_data", "images_used": 0, "method": "stub"}
        def persistence(self, *_a, **_k):
            return {"water_occurrence_fraction": None, "status": "insufficient_data", "n_images": 0, "method": "stub", "stats": {}}

    runner = LakeMetrics(AssessmentConfig(), _Water())
    for attr, name in [("ndci", "ndci_proxy"), ("bloom_frequency", "surface_algal_bloom_frequency"),
                       ("riparian_ndvi", "riparian_ndvi"), ("shoreline_disturbance", "shoreline_disturbance_fraction"),
                       ("riparian_ndvi_trend", "riparian_ndvi_sen_slope")]:
        setattr(runner, attr, fake_metric(name))
    runner.water_extent = fake_metric("water_extent")
    runner.water_persistence = fake_metric("water_persistence")
    rows = runner.run(object(), object(), "2025-08-01", "2026-08-01")
    names = {m.metric for m in rows}
    assert "red_reflectance_turbidity_proxy" not in names
    assert "ndci_proxy" in names
