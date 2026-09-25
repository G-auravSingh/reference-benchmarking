"""
generate_indicator_register.py
================================

Real generator for INDICATOR_REGISTER.md — the file's own header has always
said "Generated programmatically from create_default_registry()... Do not
hand-edit" but no such generator actually existed in this repo (checked
directly before writing this) -- the file had drifted stale as a result
(this session found it still claiming 44 registered / 31 contextual / 6
screening-only against a live registry that's actually 45 / 27 / 5, and a
missing realm-applicability column for the whole real-water-body-realm
work done this session).

Queries the live registry for every structural fact (disposition, scored
status, evidence tier, measurement scale, estimator, reference type, input
layers, and the new applicable_realms) rather than re-deriving any of it by
hand. PRESERVES each indicator's existing hand-written "Note" column text
from the current file (real methodological context that isn't stored
anywhere in the registry object itself) rather than discarding it --
parses the current file first, keyed by indicator name, and only replaces
the structural columns.

Run this after any real registry/contract change, per the file's own
stated intent:
    python generate_indicator_register.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from darukaa_reference.indicators import create_default_registry
from darukaa_reference import contracts

OUT_PATH = Path(__file__).resolve().parent / "INDICATOR_REGISTER.md"

CONSTRUCT_HEADERS = {
    "C1_landscape": "## C1 · Landscape context & extent",
    "C2_vegetation": "## C2 · Vegetation condition",
    "C3_fauna": "## C3 · Faunal condition",
    "C4_pressure": "## C4 · Pressures & human interface",
}


def _parse_existing_notes(path: Path) -> dict:
    """Real hand-written "Note" text per indicator, from whatever the file
    currently says — preserved, never regenerated from scratch, since this
    real methodological context isn't stored in the registry object."""
    notes = {}
    if not path.exists():
        return notes
    for line in path.read_text().splitlines():
        m = re.match(r"\|\s*`(\w+)`\s*\|.*\|\s*([^|]*)\s*\|\s*$", line)
        if m:
            notes[m.group(1)] = m.group(2).strip()
    return notes


def _disposition_of(spec) -> str:
    """The real disposition word (retain/redefine/context/screening/remove) —
    derived the same way contracts.py's own C table keys it, from evidence_tier
    + scoring_eligible, since IndicatorSpec doesn't store the original
    disposition word directly."""
    if not getattr(spec, "registered", True):
        return "remove"
    if spec.evidence_tier == "screening":
        return "screening"
    if spec.evidence_tier != "contextual" and spec.scoring_eligible:
        return "retain"
    if spec.evidence_tier != "contextual":
        return "redefine"
    return "context"


def main():
    registry = create_default_registry()
    contracts.apply_contracts(registry)
    existing_notes = _parse_existing_notes(OUT_PATH)

    by_construct = defaultdict(list)
    for spec in registry.all():
        by_construct[spec.construct].append(spec)

    total = len(registry.all())
    scored = sum(1 for s in registry.all() if s.scoring_eligible)
    contextual = sum(1 for s in registry.all() if s.evidence_tier == "contextual")
    screening = sum(1 for s in registry.all() if s.evidence_tier == "screening")
    removed = sum(1 for s in registry.all() if not getattr(s, "registered", True))

    lines = [
        "# Indicator Register — darukaa_reference",
        "",
        "Generated programmatically from `create_default_registry()` by "
        "`generate_indicator_register.py` — the authoritative, machine-readable "
        "source. Do not hand-edit the table columns; re-run the generator after "
        "any registry/contract change (it preserves the free-text Note column "
        "from whatever is currently on disk).",
        "",
        f"**Totals:** {total} registered · {scored} scored · {contextual} contextual · "
        f"{screening} screening-only · {removed} removed.",
        "",
        "Scored = active AND computed-eligible (has reference + uncertainty + baseline "
        "tier, no unmet dependencies). Eligibility is computed, never hand-set. "
        "**Realms** = which of terrestrial/aquatic/mixed this indicator is valid for — "
        "checked directly against real extraction logic for every indicator (not assumed "
        "from a module tag); see CHANGELOG.md's real per-indicator classification.",
        "",
    ]

    for construct, header in CONSTRUCT_HEADERS.items():
        specs = sorted(by_construct.get(construct, []), key=lambda s: (s.subdimension or "", s.name))
        if not specs:
            continue
        lines.append("")
        lines.append(header)
        lines.append("")
        lines.append("| Indicator | Subdim | Disposition | Scored | Evidence | Scale | "
                     "Estimator | Ref type | Realms | Inputs | Note |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for s in specs:
            scored_mark = "✅" if s.scoring_eligible else "—"
            estimator = s.reference_estimator or "—"
            ref_type = s.reference_type or "—"
            realms = "/".join(r[:4] for r in s.applicable_realms)  # terr/aqua/mixe, compact
            inputs = ", ".join(s.input_layers) if getattr(s, "input_layers", None) else "—"
            note = existing_notes.get(s.name, "")
            lines.append(f"| `{s.name}` | {s.subdimension or '—'} | {_disposition_of(s)} "
                        f"| {scored_mark} | {s.evidence_tier} | {s.measurement_scale or '—'} | "
                        f"{estimator} | {ref_type} | {realms} | {inputs} | {note} |")

    OUT_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT_PATH} — {total} indicators, {scored} scored.")


if __name__ == "__main__":
    main()
