"""
06_reporting / report_builder.py
===================================

Site selection report matching the depth and structure of the Pimpri
methodology document: purpose/scope, the site as
measured, design principles, site selection methodology (with the real
MMU/clustering diagnostics this run actually produced, not illustrative
numbers), stratification result, position pool status per EMU, deployment
regime and schedule, declared caveats, and references — rather than the
earlier lighter summary.

Every number in this report is read directly from a prior stage's JSON
output. Nothing here should ever say something the pipeline's own data
doesn't support — if a section would need to state something not present
in the underlying JSON, it says "not available" rather than inventing it.
This is also why the interactive map lives in the separate `field_map.html`
(see docs/OUTPUT_FILE_GUIDE.md) rather than being duplicated here — this
report links to it, the same relationship the Pimpri doc itself describes
between its methodology document and its own field_map.html.

No new template engine dependency — plain Python string building,
regenerated wholesale every run.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import config_schema  # noqa: E402
import crs              # noqa: E402

logger = logging.getLogger(__name__)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    return json.load(open(path)) if path.exists() else None


def _load_fc(path: Path) -> List[Dict[str, Any]]:
    fc = _load_json(path)
    return fc["features"] if fc else []


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    if not rows:
        return "<p><em>No data yet.</em></p>"
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def build_report(project_dir: Path, cfg: Dict[str, Any]) -> str:
    is_contiguous = cfg["archetype"] in ("conservation", "industrial")
    ing_dir = project_dir / "outputs" / "01_ingestion"
    cov_dir = project_dir / "outputs" / "02_covariates"
    emu_dir = project_dir / "outputs" / "03_emu_delineation"
    pos_dir = project_dir / "outputs" / "03b_position_scoring"
    dep_dir = project_dir / "outputs" / "04_deployment_planning"
    roll_dir = project_dir / "outputs" / "05_metrics_rollup"

    ingestion_report = _load_json(ing_dir / "ingestion_report.json") or {}
    grid_report = ingestion_report.get("candidate_grid")
    covariate_report = _load_json(cov_dir / "covariate_ingestion_report.json")
    emu_report = _load_json(emu_dir / "emu_delineation_report.json") or {}
    position_report = _load_json(pos_dir / "position_scoring_report.json")
    deployment_report = _load_json(dep_dir / "deployment_schedule.json") or {}
    rollup_report = _load_json(roll_dir / "metrics_rollup_report.json") or {}

    emu_source = emu_dir / ("emus.geojson" if is_contiguous else "candidates_with_emu.geojson")
    emu_fc_features = _load_fc(emu_source)
    anchors = _load_fc(ing_dir / "ecological_anchors.geojson")
    exclusions = _load_fc(ing_dir / "exclusion_zones.geojson")
    aoi_features = _load_fc(ing_dir / "aoi_boundary.geojson")

    purpose_html = f"""
    <p>This document states what will be measured, where, when, how often,
    and with what pipeline settings for <b>{cfg['project_name']}</b>
    ({cfg['client_name']}) — and what this design can and cannot support as
    a conclusion. It is paired with <code>field_map.html</code>, the
    interactive map: this document explains and constrains what the
    pipeline is allowed to do; the map is the fastest way to see what it
    actually did.</p>
    <p><b>Archetype:</b> {cfg['archetype']} ({'contiguous single-perimeter site, EMUs delineated by image segmentation' if is_contiguous else 'scattered multi-parcel site, EMUs delineated by ecological clustering'}).</p>
    """

    aoi_area_ha = None
    projected_crs = None
    if aoi_features:
        aoi_geom = shape(aoi_features[0]["geometry"])
        projected_crs = crs.resolve(aoi_geom)
        aoi_area_ha = round(crs.to_m(aoi_geom, projected_crs).area / 10_000, 2)
    elif emu_fc_features:
        projected_crs = crs.resolve(shape(emu_fc_features[0]["geometry"]))

    # For a contiguous archetype, "n_candidates" is the pre-tessellation
    # KML placemark count (often 0 or 1 — everything else is
    # anchor/exclusion/boundary), not a meaningful number to show next to
    # "Tessellated grid cells". The grid cell count is the real candidate
    # count for this archetype.
    site_rows = [] if grid_report else [["Total candidates ingested", ingestion_report.get("n_candidates", "\u2014")]]
    if aoi_area_ha is not None:
        site_rows.insert(0, ["AOI area (ha)", aoi_area_ha])
    if grid_report:
        site_rows.append(["Total candidates (tessellated grid cells)", grid_report.get("n_cells", "\u2014")])
        site_rows.append(["Grid cell size", f"{grid_report.get('cell_size_m', '\u2014')} m"])
        site_rows.append(["Hard exclusion area (ha)", grid_report.get("hard_exclusion_area_ha", "\u2014")])
        site_rows.append(["Soft exclusion area, tessellated (ha)",
                          grid_report.get("soft_exclusion_area_ha_included_in_matrix", "\u2014")])
        site_rows.append(["Anchor area (ha)", grid_report.get("anchor_area_ha", "\u2014")])
    site_rows.append(["Ecological anchors", len(anchors)])
    site_rows.append(["Exclusion zones (hard + soft)", len(exclusions)])
    if covariate_report:
        site_rows.append(["Candidates matched to real GEE covariates",
                          f"{covariate_report.get('n_matched', '\u2014')}/{covariate_report.get('n_candidates', '\u2014')}"])
        site_rows.append(["Filtered \u2014 built-up", covariate_report.get("n_hard_filtered_builtup", "\u2014")])
        site_rows.append(["Filtered \u2014 permanent water", covariate_report.get("n_hard_filtered_water", "\u2014")])

    contiguity_principle = (
        "<li><b>Spatial contiguity is a structural guarantee</b> for segmentation-derived EMUs &mdash; verified by a hard runtime check, not assumed.</li>"
        if is_contiguous else
        "<li><b>EMU membership stays real and complete, even when scattered.</b> A farm parcel that's geographically far from most of its EMU is never split into a separate unit just for tidiness &mdash; it keeps contributing to that EMU's ecological metrics. It's simply excluded from device-position eligibility if it's too isolated for a field visit to be practical (see &sect;6).</li>"
    )
    principles_html = f"""
    <ul>
      <li><b>Segment/cluster before logistics.</b> The ecological unit (EMU) is decided on ecological grounds first, then fitted to devices, days, and access.</li>
      {contiguity_principle}
      <li><b>Device coverage is a hard guarantee.</b> An EMU this pipeline delineates and cannot cover with available devices is treated as an internal error to fix, never a client-facing "uncovered EMU" finding.</li>
      <li><b>Distribution shown alongside the worst-case flag, never the flag alone</b> &mdash; a single declining tile inside an otherwise-healthy EMU should never read as "no improvement happening" project-wide.</li>
    </ul>
    
    """

    method_html = ""
    if is_contiguous:
        mmu = emu_report.get("mmu_diagnostics")
        method_html += "<p><b>Method:</b> GEE SNIC image segmentation over the tessellated grid, reconciled with client-declared ecological anchors.</p>"
        if mmu and mmu.get("per_zone"):
            # Zone-partitioned: each real ecological zone tuned its own
            # segment count independently, so there's no single search
            # trace to show — a per-zone summary table instead.
            zone_rows = [[zone, str(z["target"]), str(z["min_mapping_unit_used"]), str(z["n_final"]),
                         "yes" if z["converged"] else "best available"]
                        for zone, z in mmu["per_zone"].items()]
            method_html += (
                f"<p><b>Minimum-mapping-unit auto-tune (per real ecological zone):</b> "
                f"{mmu.get('n_raw_segments', '\u2014')} raw SNIC segments (after connected-component "
                f"splitting: {mmu.get('n_contiguous_pieces_after_split', '\u2014')} genuinely contiguous "
                f"pieces) &rarr; {emu_report.get('n_segmentation_emus', '\u2014')} final segments across "
                f"every zone.</p>"
                + _table(["Zone", "Device-share target", "Min. mapping unit used", "Final segment count", "Converged"], zone_rows)
            )
        elif mmu:
            trace_rows = [[t["min_mapping_unit"], t["n_segments"]] for t in mmu.get("search_trace", [])[:15]]
            method_html += (
                f"<p><b>Minimum-mapping-unit auto-tune:</b> {mmu.get('n_raw_segments', '\u2014')} raw "
                f"SNIC segments (after connected-component splitting: "
                f"{mmu.get('n_contiguous_pieces_after_split', '\u2014')} genuinely contiguous pieces) "
                f"&rarr; auto-tuned threshold {mmu.get('min_mapping_unit_used', '\u2014')} "
                f"&rarr; {emu_report.get('n_segmentation_emus', '\u2014')} final segments "
                f"({'converged to target' if mmu.get('converged') else 'best available &mdash; did not fully converge to target, see caveats'}).</p>"
                + _table(["Min. mapping unit tried", "Resulting segment count"], trace_rows)
            )
        method_html += (
            f"<p><b>Residual unclassified area:</b> {emu_report.get('residual_unclassified_ha', '\u2014')} ha "
            "(real leftover land not covered by any anchor, exclusion, or EMU &mdash; reported explicitly, not dropped).</p>"
        )
    else:
        method_html += "<p><b>Method:</b> Gower-distance ecological clustering with a spatial k-nearest-neighbour connectivity constraint, so ecologically-similar candidates can only group together if they're geographically reachable through a chain of nearby candidates.</p>"
        k_bounds = emu_report.get("k_bounds", {})
        method_html += (
            f"<p><b>K bounds this run:</b> k_min={k_bounds.get('k_min','\u2014')}, "
            f"k_max={k_bounds.get('k_max','\u2014')} "
            f"(logistics ceiling {k_bounds.get('k_max_logistics','\u2014')}, "
            f"replication ceiling {k_bounds.get('k_max_replication','\u2014')}, "
            f"achievable cycles {k_bounds.get('achievable_cycles','\u2014')}).</p>"
        )
        partition_rows = [
            [pv, pr.get("n_candidates"), pr.get("k_selected"), pr.get("n_emus_after_compactness_split", "\u2014")]
            for pv, pr in emu_report.get("partition_reports", {}).items()
        ]
        method_html += _table(
            ["Partition (barrier group)", "N candidates", "K selected", "Final EMU count"], partition_rows)

    if position_report:
        weights_sorted = sorted(position_report.get("critic_weights", {}).items(),
                                 key=lambda kv: -kv[1])[:8]
        method_html += (
            f"<p><b>Within-EMU position ranking:</b> CRITIC-weighted typicality "
            f"(feature tier: {position_report.get('feature_tier','\u2014')}). "
            "Top-weighted covariates this run: "
            + ", ".join(f"{k} ({v:.3f})" for k, v in weights_sorted) + ".</p>"
        )

    if is_contiguous:
        type_labels = {"ecological_anchor": "Client-identified ecological feature",
                       "segmentation_derived": "Derived from image segmentation"}
        strat_rows = []
        for f in emu_fc_features:
            geom_m = crs.to_m(shape(f["geometry"]), projected_crs) if projected_crs else None
            area_ha = round(geom_m.area / 10_000, 2) if geom_m else "\u2014"
            strat_rows.append([
                f["properties"]["emu_id"],
                type_labels.get(f["properties"].get("emu_type"), "\u2014"),
                area_ha,
            ])
        strat_headers = ["EMU ID", "How it was identified", "Area (ha)"]
    else:
        emu_summary = emu_report.get("emu_summary", [])
        strat_rows = [[e["emu_id"], e["total_area_ha"], e["n_tiles"]] for e in emu_summary]
        strat_headers = ["EMU ID", "Area (ha)", "Number of farm parcels"]
    n_emus = emu_report.get("n_emus_total") or emu_report.get("n_emus") or len(strat_rows)

    pool_html = "<p><em>Not available &mdash; run 03b_position_scoring.</em></p>"
    if position_report:
        pool_rows = [[eid, r["n_candidates"], r["pool_size"], r["medoid_name"],
                     r.get("n_deployment_outliers_excluded", 0) or "\u2014"]
                     for eid, r in position_report.get("emu_reports", {}).items()]
        pool_html = _table(["EMU ID", "N candidates", "Position pool size", "Medoid",
                            "Spatial outliers excluded from device eligibility"], pool_rows)
        total_outliers = sum(r.get("n_deployment_outliers_excluded", 0)
                             for r in position_report.get("emu_reports", {}).values())
        if total_outliers:
            pool_html += (f'<p class="note">{total_outliers} candidate(s) are kept as real EMU '
                          "members (they still count toward that EMU's ex-situ metrics) but are "
                          "too geographically isolated from the rest of their EMU to be a "
                          "practical device position &mdash; see Declared Caveats.</p>")

    regime = deployment_report.get("regime", "\u2014")
    regime_note = {
        "continuous_proportional": "Every EMU keeps its allocated device(s) for the whole project; the exact position rotates weekly through that EMU's position pool.",
        "stratified_single_pass": "Each EMU is sampled once, in a single assigned week, with devices allocated proportional to its size — not every EMU is visited every week.",
        "sequential_cluster": "EMUs are grouped into geographic panels; each panel is visited in a different cycle, capped at what the project timeline can achieve.",
    }.get(regime, "")
    schedule_rows = []
    for c in deployment_report.get("schedule", []):
        # sequential_cluster can carry position_assignments for
        # individual under-filled panels — checking per-row rather than
        # per-regime means every cycle renders whatever detail it
        # actually has.
        if c.get("position_assignments"):
            positions_str = "; ".join(
                f"{a['emu_id']}: " + ", ".join(p["name"] for p in a["positions"])
                for a in c["position_assignments"])
            schedule_rows.append([c["cycle_number"], f"day {c['start_day_offset']}\u2013{c['recording_end_day_offset']}",
                                  positions_str])
        else:
            schedule_rows.append([c["cycle_number"], f"day {c['start_day_offset']}\u2013{c['recording_end_day_offset']}",
                                  ", ".join(c["emu_ids"])])
    schedule_headers = (["Week", "Days", "Active position per EMU"]
                        if regime in ("continuous_proportional", "stratified_single_pass")
                        else ["Cycle", "Days", "EMUs / positions visited"])
    device_alloc = deployment_report.get("device_allocation")
    device_alloc_html = ""
    if device_alloc:
        device_alloc_html = _table(["EMU ID", "Devices allocated"], list(device_alloc.items()))

    # Only rendered when a project actually has a real soil chemistry
    # design (soil_chemistry_points.geojson) — every other project's
    # report is unaffected. A separate "7b" section rather than folding
    # into 7, since this is a genuinely different, one-time (not
    # week-rotated)
    # sampling design that shouldn't be read as part of the weekly
    # rotation schedule above it.
    soil_chem_html = ""
    soil_chem_path = project_dir / "outputs" / "06_reporting" / "soil_chemistry_points.geojson"
    if soil_chem_path.exists():
        with open(soil_chem_path) as f:
            soil_chem_fc = json.load(f)
        n_points = len(soil_chem_fc["features"])
        emu_ids_covered = sorted(set(f["properties"]["emu_id"] for f in soil_chem_fc["features"]))
        n_corners_by_emu = {}
        n_emus_covered = len(emu_ids_covered)
        substitution_note = ""
        if soil_chem_fc.get("substitutions"):
            sub_list = ", ".join(f"{eid.replace('EMU_ANCHOR_', '').replace('EMU_', '').replace('_', ' ')}: {msg}"
                                 for eid, msg in soil_chem_fc["substitutions"].items())
            substitution_note = f"""
    <li><b>Noted substitution:</b> {sub_list}.</li>"""
        soil_chem_html = f"""
  <h2>7b. Soil chemistry sampling design</h2>
  <p>A real, one-time composite sampling design, collected once during the
  final deployment week &mdash; not part of the weekly audiomoth/camera
  trap rotation above, and not repeated across seasons.</p>
  <ul>
    <li><b>Design:</b> 4-5 corner points + 1 centre point per EMU,
    composited into real soil chemistry samples (NPK, pH, EC and similar
    parameters).</li>
    <li><b>Corner placement:</b> manually specified, real candidate
    locations &mdash; every point named directly rather than
    algorithmically selected, verified to be a real, already-tessellated
    candidate belonging to its stated EMU. The centre is each EMU's own
    manually specified candidate, or its real geometric centroid where
    noted below.</li>{substitution_note}
    <li><b>Coverage:</b> {n_points} real points across {n_emus_covered}
    EMUs ({", ".join(e.replace("EMU_ANCHOR_", "").replace("EMU_", "").replace("_", " ") for e in emu_ids_covered)}).</li>
  </ul>
"""

    proj_cov = rollup_report.get("project_covariates", {})
    if proj_cov:
        cov_rows = [[cov + (" \u26a0\ufe0f" if d.get("caveat") else ""),
                    d["median_of_emu_medians"], f"{d['min_emu_median']}\u2013{d['max_emu_median']}",
                    d.get("worst_emu_id") or "\u2014"]
                   for cov, d in proj_cov.items()]
        rollup_html = _table(["Covariate", "Median of EMU medians", "Range across EMUs", "Worst EMU (flag)"], cov_rows) + \
            '<p class="note">Distribution shown alongside the worst-EMU flag by design &mdash; never the flag alone. ' \
            '\u26a0\ufe0f = see Declared Caveats below for a known data-quality issue affecting this covariate.</p>'
    else:
        rollup_html = '<p><em>No satellite covariates yet &mdash; pending GEE run.</em></p>'

    files_html = """
    <table><thead><tr><th>File</th><th>What it is</th></tr></thead><tbody>
    <tr><td><code>field_map.html</code></td><td>The one file to open first &mdash; interactive map with EMUs, position pools, and deployment cycles. Works offline once downloaded. Open with Chrome browser for the best experience.</td></tr>
    <tr><td>This report</td><td>The site selection design and its scientific basis.</td></tr>
    <tr><td><code>deployment_schedule.csv</code> / <code>.xlsx</code></td><td>The field-ready schedule &mdash; real calendar dates, which position each device visits each cycle.</td></tr>
    <tr><td><code>stratum_profile.csv</code></td><td>What each EMU is, in covariate terms &mdash; the source data behind the stratification table above, at full resolution.</td></tr>
    </tbody></table>
    """

    all_warnings = []
    for stage_report in (ingestion_report, covariate_report or {}, emu_report,
                          position_report or {}, deployment_report, rollup_report):
        all_warnings.extend(stage_report.get("warnings", []))
    caveats_html = ("<ul>" + "".join(f"<li>{w}</li>" for w in all_warnings) + "</ul>") if all_warnings \
        else "<p>None flagged this run.</p>"

    # "Client" relabelled "Project"; devices split into their own real
    # rows per stream rather than one combined number; cycles shown as a
    # single, direct "Deployment Cycles" value now that achievable-cycles
    # correctly matches the real project timeline in every regime (an
    # earlier "available vs needed" split distinction
    # this replaced was added specifically for a case where those two
    # numbers had drifted apart — since fixed at the source, the simpler
    # single-number format is accurate again). A real extension is still
    # never silently hidden — it's already in all_warnings/caveats_html
    # above whenever deployment_report reports used_duration_extension.
    overview_rows = [
        ["Project", cfg["client_name"]],
        ["Archetype", cfg["archetype"]],
        ["EMUs delineated", n_emus],
        ["Terrestrial Acoustic Devices", cfg["n_devices"]],
    ]
    if "camera_trap" in cfg.get("streams_active", []):
        overview_rows.append(["Terrestrial Camera Traps", cfg.get("camera_trap_n_devices", 2)])
    overview_rows += [
        ["Deployment Cycles", f"{deployment_report.get('n_cycles_scheduled', cfg['project_duration_weeks'])} Weeks"],
        ["Deployment regime", regime],
    ]

    # A References section must stand on its own for anyone reading only
    # this HTML file — it never points to an internal repository file the
    # client won't have access to. Curated, client-appropriate citations
    # included directly, the same real sources behind the methods above.
    references_html = """
    <ul>
      <li>Diakoulaki, D., Mavrotas, G., &amp; Papayannakis, L. (1995). Determining objective weights in multiple criteria problems: The CRITIC method. <i>Computers &amp; Operations Research</i>, 22(7), 763&ndash;770. &mdash; the objective, data-driven covariate weighting method used to rank candidate positions within each EMU.</li>
      <li>Karra, K., Kontgis, C., et al. (2021). Global land use/land cover with Sentinel-2 and deep learning. <i>IGARSS 2021</i>. &mdash; the current, annually-updated land-cover classification used for landscape-context covariates.</li>
      <li>Achanta, R., &amp; S&uuml;sstrunk, S. (2017). Superpixels and polygons using simple non-iterative clustering (SNIC). <i>CVPR 2017</i>. &mdash; the image segmentation method used to delineate ecological monitoring units for contiguous sites.</li>
      <li>Hansen, M. C., et al. (2013, with ongoing annual updates). High-resolution global maps of 21st-century forest cover change. <i>Science</i>, 342(6160), 850&ndash;853. &mdash; global forest-loss reference dataset.</li>
    </ul>
    """

    return HTML_TEMPLATE.format(
        project_name=cfg["project_name"],
        client_name=cfg["client_name"],
        purpose_html=purpose_html,
        overview_table=_table(["Field", "Value"], overview_rows),
        site_table=_table(["Parameter", "Value"], site_rows),
        principles_html=principles_html,
        method_html=method_html,
        strat_table=_table(strat_headers, strat_rows),
        pool_html=pool_html,
        regime_note=regime_note,
        device_alloc_html=device_alloc_html,
        soil_chem_html=soil_chem_html,
        schedule_table=_table(schedule_headers, schedule_rows),
        rollup_html=rollup_html,
        files_html=files_html,
        caveats_html=caveats_html,
        references_html=references_html,
    )


HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"/>
<title>{project_name} \u2014 Site Selection Report</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 0 32px 48px; color: #1f2937; max-width: 980px; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #15803d; padding-bottom: 8px; }}
  h2 {{ font-size: 17px; margin-top: 32px; color: #14532d; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 13px; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 6px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #f0fdf4; }}
  .note {{ color: #6b7280; font-size: 12px; font-style: italic; }}
  ul {{ font-size: 13px; }}
  code {{ background: #f3f4f6; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
</style>
</head>
<body>
  <h1>{project_name} \u2014 Site Selection Report</h1>
  <p><strong>Client:</strong> {client_name}</p>

  <h2>1. Purpose and scope</h2>
  {purpose_html}

  <h2>Overview</h2>
  {overview_table}

  <h2>2. The site, as measured</h2>
  {site_table}

  <h2>3. Design principles</h2>
  {principles_html}

  <h2>4. Site selection methodology &mdash; this run</h2>
  {method_html}

  <h2>5. Ecological stratification &mdash; current result</h2>
  {strat_table}

  <h2>6. Position pool status per EMU</h2>
  {pool_html}

  <h2>7. Deployment regime and schedule</h2>
  <p>{regime_note}</p>
  {device_alloc_html}
  {schedule_table}
  {soil_chem_html}

  <h2>8. Covariate profile (project level)</h2>
  {rollup_html}

  <h2>9. Output files &mdash; what to open and when</h2>
  {files_html}

  <h2>10. Declared caveats</h2>
  {caveats_html}

  <h2>11. References</h2>
  {references_html}
</body></html>
"""


def run_report_build(project_dir):
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")
    html = build_report(project_dir, cfg)
    out_dir = project_dir / "outputs" / "06_reporting"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{cfg['project_name']}_site_selection_report.html"
    out_path.write_text(html)
    logger.info("Report written: %s", out_path)
    return out_path


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_report_build(args.project_dir)
