from io import BytesIO

from PIL import Image

from app.services.photo_analysis import PhotoAnalysisError, normalize_interpretation
from tests.conftest import create_assessment


ITEM_ID = "17-1-2io-basic-item-001"


def image_bytes():
    buffer = BytesIO()
    Image.new("RGB", (80, 50), (80, 120, 160)).save(buffer, format="JPEG")
    return buffer.getvalue()


def upload_photo(client, assessment_id, filename):
    response = client.post(
        f"/assessments/{assessment_id}/review/0/0",
        data={f"photo_{ITEM_ID}": (BytesIO(image_bytes()), filename), "action": "summary"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302


def result_for(description="Diagonal crack visible"):
    return {
        "summary": "A concrete wall is visible.",
        "components": [{"name": "Wall", "material": "Concrete", "condition": "Crack visible"}],
        "observations": [{"description": description, "severity": "severe", "confidence": "high"}],
        "possibleDeficiencies": [],
        "suggestedStatus": "NC",
        "statusRationale": "The image suggests a condition requiring engineer verification.",
        "followUp": ["Measure crack width and review adjacent connections."],
        "imageQuality": {"usable": True, "issues": []},
        "model": "test-model",
    }


def test_photo_analysis_is_opt_in_and_legacy_evidence_is_unchanged(client, app):
    assessment_id = create_assessment(client)
    upload_photo(client, assessment_id, "legacy.jpg")
    evidence = client.get(f"/assessments/{assessment_id}/export.json").get_json()["evidence"][0]
    page = client.get(f"/assessments/{assessment_id}/evidence/{evidence['id']}/analysis")

    assert page.status_code == 200
    assert b"Analyze photo" in page.data
    payload = client.get(f"/assessments/{assessment_id}/export.json").get_json()
    assert payload["photo_analyses"] == []
    assert evidence["sha256"]


def test_failed_photo_analysis_keeps_evidence_and_retry_succeeds(client, app):
    assessment_id = create_assessment(client)
    upload_photo(client, assessment_id, "retry.jpg")
    evidence = client.get(f"/assessments/{assessment_id}/export.json").get_json()["evidence"][0]

    def fail(_evidence, _context, _upload_root):
        raise PhotoAnalysisError("Temporary analyzer outage")

    app.config["PHOTO_ANALYZER"] = fail
    response = client.post(
        f"/assessments/{assessment_id}/evidence/{evidence['id']}/analysis",
        data={"photo_description": "Inspect wall crack", "location_in_building": "Level 1"},
    )
    assert response.status_code == 302
    failed = client.get(f"/assessments/{assessment_id}/export.json").get_json()
    assert failed["photo_analyses"][0]["status"] == "failed"
    assert failed["photo_analyses"][0]["error_message"] == "Temporary analyzer outage"
    assert len(failed["evidence"]) == 1

    app.config["PHOTO_ANALYZER"] = lambda _evidence, _context, _upload_root: result_for()
    response = client.post(
        f"/assessments/{assessment_id}/evidence/{evidence['id']}/analysis",
        data={"photo_description": "Inspect wall crack", "location_in_building": "Level 1"},
    )
    assert response.status_code == 302
    payload = client.get(f"/assessments/{assessment_id}/export.json").get_json()
    assert [record["status"] for record in payload["photo_analyses"]] == ["failed", "succeeded"]
    assert payload["photo_analyses"][1]["context"]["location_in_building"] == "Level 1"
    assert payload["photo_analyses"][1]["result"]["suggestedStatus"] == "NC"
    assert payload["summary"]["incomplete"] > 0  # The advisory suggestion never sets checklist status.


def test_repeated_photo_findings_are_ranked_and_linked(client, app):
    assessment_id = create_assessment(client)
    upload_photo(client, assessment_id, "north.jpg")
    upload_photo(client, assessment_id, "south.jpg")
    evidence = client.get(f"/assessments/{assessment_id}/export.json").get_json()["evidence"]
    app.config["PHOTO_ANALYZER"] = lambda _evidence, _context, _upload_root: result_for("Diagonal crack visible")

    for evidence_record, location in zip(evidence, ("Level 1 north", "Level 2 south")):
        response = client.post(
            f"/assessments/{assessment_id}/evidence/{evidence_record['id']}/analysis",
            data={"photo_description": "Look for diagonal cracking", "location_in_building": location},
        )
        assert response.status_code == 302

    payload = client.get(f"/assessments/{assessment_id}/export.json").get_json()
    considerations = payload["ongoing_considerations"]
    crack = next(item for item in considerations if item["description"] == "Diagonal crack visible")
    assert crack["supporting_photos"] == 2
    assert crack["priority_score"] == 9.6  # 8 * 1.0 * min(1.8, 1 + 0.2)
    assert crack["locations"] == ["Level 1 north", "Level 2 south"]
    assert len(crack["supporting_evidence"]) == 2
    assert b"Ongoing considerations" in client.get(f"/assessments/{assessment_id}/summary").data


def test_photo_analysis_cannot_cross_assessment_boundary(client, app):
    first = create_assessment(client)
    upload_photo(client, first, "private.jpg")
    evidence_id = client.get(f"/assessments/{first}/export.json").get_json()["evidence"][0]["id"]
    client.post("/assessments/new", data={"project_name": "Other"})
    assert client.get(f"/assessments/2/evidence/{evidence_id}/analysis").status_code == 404


def test_photo_output_normalization_preserves_advisory_shape():
    result = normalize_interpretation({"summary": "Visible beam", "suggestedStatus": "C", "observations": [{"description": "Corrosion", "severity": "bad", "confidence": "high"}]})

    assert result["summary"] == "Visible beam"
    assert result["suggestedStatus"] == "C"
    assert result["observations"][0]["severity"] == "moderate"
    assert result["imageQuality"] == {"usable": True, "issues": []}
