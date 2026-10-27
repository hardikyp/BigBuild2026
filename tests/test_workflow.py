from io import BytesIO

from tests.conftest import create_assessment


def test_intake_review_and_advisory_findings(client):
    assessment_id = create_assessment(client)
    response = client.get(f"/assessments/{assessment_id}/review/0/0")
    assert response.status_code == 200
    assert b"LOAD PATH" in response.data
    response = client.post(
        f"/assessments/{assessment_id}/review/0/0",
        data={
            "status_17-1-2io-basic-item-001": "NC",
            "comment_17-1-2io-basic-item-001": "Observed condition requires review.",
            "status_17-1-2io-basic-item-002": "U",
            "action": "summary",
        },
    )
    assert response.status_code == 302
    summary = client.get(f"/assessments/{assessment_id}/summary")
    assert summary.status_code == 200
    assert b"Observed condition requires review." in summary.data
    assert b"noncompliant" in summary.data.lower()


def test_evidence_upload_and_download(client):
    assessment_id = create_assessment(client)
    item_id = "17-1-2io-basic-item-001"
    response = client.post(
        f"/assessments/{assessment_id}/review/0/0",
        data={
            f"status_{item_id}": "NC",
            f"file_{item_id}": (BytesIO(b"photo evidence"), "west-wall.txt"),
            f"caption_{item_id}": "West wall observation",
            "action": "summary",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    data = client.get(f"/assessments/{assessment_id}/export.json").get_json()
    evidence = data["evidence"]
    assert evidence[0]["original_name"] == "west-wall.txt"
    assert evidence[0]["caption"] == "West wall observation"
    assert len(evidence[0]["sha256"]) == 64


def test_resume_and_navigation(client):
    assessment_id = create_assessment(client, performance="CP", building_type="C1", seismicity="moderate")
    first = client.get(f"/assessments/{assessment_id}/review/0/0")
    assert first.status_code == 200
    next_page = client.post(
        f"/assessments/{assessment_id}/review/0/0",
        data={"action": "next"},
    )
    assert next_page.status_code == 302
    assert "/review/0/1" in next_page.headers["Location"]
    resumed = client.get(next_page.headers["Location"])
    assert resumed.status_code == 200


def test_last_checklist_page_uses_review_summary_action(client):
    assessment_id = create_assessment(client, performance="CP", building_type="C1", seismicity="moderate")
    # CP/C1 has a basic form followed by the structural form; the final
    # checklist page is the last section of the final form.
    last_page = client.get(f"/assessments/{assessment_id}/review/1/999")
    assert last_page.status_code == 200
    assert b">Review Summary<" in last_page.data
    assert b"Save and continue" not in last_page.data
