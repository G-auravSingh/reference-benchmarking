"""
test_bii_v1_1_upgrade.py
===========================

Real test for independent audit item 16: upgrade BII to v1.1.

Before implementing, the real asset (projects/ebx-data/assets/earthblox/IO/
BII_V1_1) was verified LIVE via a real web search against the GEE
community-catalog listing (Gassert, Mazzarello & Hyde 2026, Vizzuality/Impact
Observatory, confirmed annual 2017-2025 coverage) -- not assumed from the
audit's claim alone, same discipline used for the earlier CHM asset switch.

This test checks what's checkable without live GEE credentials: the citation
text names the real v1.1 source, and the registry still constructs cleanly
with the updated _img_bii (which now branches on config.ndvi_year -- this
test can't execute the GEE branch itself, but confirms the function is wired
in and the registration is intact).

Run with: python -m pytest tests/test_bii_v1_1_upgrade.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.indicators import create_default_registry


def test_bii_citation_names_the_verified_v1_1_asset():
    reg = create_default_registry()
    citation = reg.get("bii").citation
    assert "BII_V1_1" in citation
    assert "2026" in citation  # Gassert, Mazzarello & Hyde (2026)
    assert "2017-2025" in citation or "2017–2025" in citation


def test_bii_still_registered_and_scored():
    """The upgrade must not have broken bii's registration or its scoring
    eligibility (bii is a real, deliberately-promoted C3 fauna signal -- see
    Thread 01/03 history)."""
    reg = create_default_registry()
    spec = reg.get("bii")
    assert spec.registered
    assert spec.active
    assert spec.scoring_eligible


def test_ghm_citation_matches_the_real_live_asset():
    """Independent audit item 17: ghm's citation was still Kennedy et al. (2019),
    the source paper for the PRIOR CSP/HM asset -- but the real, live asset
    (_img_ghm) has used TNC/HM/v3/90m_s (2022) since a v0.2.5 fix. Verified
    live via PubMed/Nature before writing (Theobald et al. 2025, Scientific
    Data 12, 606, DOI:10.1038/s41597-025-04892-2)."""
    reg = create_default_registry()
    citation = reg.get("ghm").citation
    assert "10.1038/s41597-025-04892-2" in citation
    assert "Theobald" in citation
    assert citation.strip().startswith("Theobald")
    assert "10.1111/gcb.14549" not in citation  # the old Kennedy (2019) DOI is gone


if __name__ == "__main__":
    test_bii_citation_names_the_verified_v1_1_asset()
    test_bii_still_registered_and_scored()
    test_ghm_citation_matches_the_real_live_asset()
    print("All test_bii_v1_1_upgrade tests passed.")
