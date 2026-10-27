import json
from pathlib import Path

from app.services.assessment import applicable_sections
from app.services.catalog import build_catalog, applicable_forms


SOURCE_ROOT = Path("src/ASCE 41-23 Tier 1 checklist for seismic evaluation and retrofit of existing buildings")


def test_catalog_covers_all_supplied_forms():
    catalog = build_catalog(SOURCE_ROOT)
    assert catalog["catalog_version"]
    assert len(catalog["forms"]) == 38
    assert sum(len(form["items"]) for form in catalog["forms"]) >= 850
    assert all(form["source_hash"] for form in catalog["forms"])
    assert all(item["statement"] for form in catalog["forms"] for item in form["items"])
    item_ids = [item["item_id"] for form in catalog["forms"] for item in form["items"]]
    assert len(item_ids) == len(set(item_ids))


def test_parser_preserves_references_and_sections():
    catalog = build_catalog(SOURCE_ROOT)
    basic = next(form for form in catalog["forms"] if form["form_id"] == "17-1-2cp-basic")
    assert basic["sections"][0]["title"] == "Building System—General"
    load_path = basic["items"][0]
    assert load_path["statement"].startswith("LOAD PATH:")
    assert load_path["tier2_reference"] == "5.4.1.1"
    assert load_path["commentary_reference"] == "A.2.1.1"


def test_applicability_is_cumulative_by_seismicity():
    catalog = build_catalog(SOURCE_ROOT)
    low = applicable_forms(catalog, "CP", "C1", "low", True, True, False)
    high = applicable_forms(catalog, "CP", "C1", "high", True, True, False)
    low_basic = next(form for form in low if form["building_type"] == "BASIC")
    high_basic = next(form for form in high if form["building_type"] == "BASIC")
    assert low_basic["form_id"] == "17-1-2cp-basic"
    assert high_basic["form_id"] == "17-1-2cp-basic"
    high_sections = applicable_sections(high_basic, "high")
    assert sum(len(section["items"]) for section in high_sections) == len(high_basic["items"])


def test_nonstructural_is_optional():
    catalog = build_catalog(SOURCE_ROOT)
    without = applicable_forms(catalog, "IO", "S1", "high", True, True, False)
    with_form = applicable_forms(catalog, "IO", "S1", "high", True, True, True)
    assert not any(form["building_type"] == "NONSTRUCTURAL" for form in without)
    assert any(form["building_type"] == "NONSTRUCTURAL" for form in with_form)
