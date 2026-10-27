from pathlib import Path

from tests.conftest import create_assessment


def test_json_export_contains_source_and_warning_metadata(client):
    assessment_id = create_assessment(client)
    response = client.get(f"/assessments/{assessment_id}/export.json")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["schema_version"] == "1.0"
    assert payload["catalog_version"] == "2026.10.27"
    assert "decision support only" in payload["decision_support_notice"]
    assert payload["summary"]["incomplete"] > 0
    assert payload["checklists"][0]["source_hash"]
    assert payload["checklists"][0]["sections"]


def test_pdf_export_is_valid_pdf(client):
    assessment_id = create_assessment(client, performance="CP", building_type="C1", seismicity="moderate")
    response = client.get(f"/assessments/{assessment_id}/export.pdf")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert len(response.data) > 2000
