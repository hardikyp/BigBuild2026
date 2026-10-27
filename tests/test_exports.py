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


def test_pdf_export_is_downloadable_and_summary_link_opts_out_of_htmx(client):
    assessment_id = create_assessment(client)
    response = client.get(f"/assessments/{assessment_id}/export.pdf")
    assert response.headers["Content-Disposition"] == f"attachment; filename=assessment-{assessment_id}.pdf"
    summary = client.get(f"/assessments/{assessment_id}/summary")
    assert f'download="assessment-{assessment_id}.pdf"'.encode() in summary.data
    assert b'hx-boost="false"' in summary.data
