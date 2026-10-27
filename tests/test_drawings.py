from io import BytesIO

import pytest
from PIL import Image

from app.domain.models import Assessment
from app.services.drawings import (
    DrawingError, Interpretation, InterpretedField, apply_interpretation, content_blocks,
    parse_interpretation, read_drawing,
)


PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def png_bytes(size=(40, 30)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def fake_interpreter(calls):
    def interpret(drawings):
        calls.append(drawings)
        return Interpretation(
            fields=[
                InterpretedField("stories", "3", "high", "Elevation A-201 level markers"),
                InterpretedField("length", "120 ft", "high", "Overall dimension, plan S-101"),
                InterpretedField("building_name", "North Annex", "high", "Title block"),
                InterpretedField("building_type", "C2", "medium", "Concrete shear walls on S-101"),
            ],
            notes="Confirm wall reinforcing on site.",
            model="test-model",
        )
    return interpret


def test_parse_interpretation_drops_unknown_and_invalid_values():
    result = parse_interpretation({
        "fields": [
            {"field": "stories", "value": " 2 ", "confidence": "high", "basis": "Elevation"},
            {"field": "stories", "value": "5", "confidence": "low", "basis": "Duplicate"},
            {"field": "seismicity", "value": "high", "confidence": "high", "basis": "Not allowed"},
            {"field": "building_type", "value": "c2a", "confidence": "medium", "basis": "Walls"},
            {"field": "use", "value": "", "confidence": "high", "basis": "Empty"},
            {"field": "foundation", "value": "Spread footings", "confidence": "certain", "basis": "S-001"},
        ],
        "notes": "n",
    })
    values = {entry.field: entry for entry in result.fields}
    assert values["stories"].value == "2"
    assert values["building_type"].value == "C2"
    assert values["foundation"].confidence == "low"
    assert set(values) == {"stories", "building_type", "foundation"}


def test_apply_keeps_engineer_values_unless_overwriting():
    assessment = Assessment(stories="4", length="")
    interpretation = Interpretation([
        InterpretedField("stories", "3", "high", "A-201"),
        InterpretedField("length", "120 ft", "high", "S-101"),
    ])
    result = apply_interpretation(assessment, interpretation)
    assert result.applied == ["length"] and result.kept == ["stories"]
    assert assessment.stories == "4" and assessment.length == "120 ft"
    result = apply_interpretation(assessment, interpretation, overwrite=True)
    assert result.applied == ["stories"]
    assert assessment.stories == "3"


def test_read_drawing_checks_content_not_name():
    assert read_drawing("plan", "sheet.png", PDF_BYTES).mime_type == "application/pdf"
    assert read_drawing("plan", "sheet.pdf", png_bytes()).mime_type == "image/png"
    with pytest.raises(DrawingError):
        read_drawing("plan", "sheet.pdf", b"not a drawing")


def test_large_images_are_downscaled_for_the_api():
    drawing = read_drawing("elevation", "big.png", png_bytes((5000, 3000)))
    blocks = content_blocks([drawing])
    image = next(block for block in blocks if block["type"] == "image")
    import base64
    with Image.open(BytesIO(base64.b64decode(image["source"]["data"]))) as fitted:
        assert max(fitted.size) <= 2576


def test_interpret_drawings_fills_intake(app, client):
    calls = []
    app.config["DRAWING_INTERPRETER"] = fake_interpreter(calls)
    client.post("/assessments/new", data={"project_name": "P"})
    response = client.post(
        "/assessments/1/intake",
        data={
            "project_name": "P",
            "building_name": "Engineer's name",
            "action": "interpret",
            "drawing_plan": (BytesIO(PDF_BYTES), "S-101.pdf"),
            "drawing_elevation": (BytesIO(png_bytes()), "A-201.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    assert "/intake" in response.headers["Location"]
    assert [d.role for d in calls[0]] == ["plan", "elevation"]

    page = client.get("/assessments/1/intake")
    assert b'value="3"' in page.data
    assert b'value="120 ft"' in page.data
    assert b'value="Engineer&#39;s name"' in page.data
    assert b'<option value="C2" selected' in page.data
    assert b"Plan drawings" not in page.data
    assert b"Elevation drawings" not in page.data
    assert b"Interpret drawings" not in page.data

    data = client.get("/assessments/1/export.json").get_json()
    record = data["drawing_interpretations"][0]
    assert record["model"] == "test-model"
    assert set(record["applied_fields"]) == {"stories", "length", "building_type"}
    assert record["kept_fields"] == ["building_name"]
    drawings = [e for e in data["evidence"] if e["item_id"].startswith("drawings:")]
    assert {e["original_name"] for e in drawings} == {"S-101.pdf", "A-201.png"}
    assert {e["id"] for e in drawings} == set(record["evidence_ids"])
    assert not any(e["include_in_report"] for e in drawings)


def test_interpret_from_new_assessment_creates_it(app, client):
    app.config["DRAWING_INTERPRETER"] = fake_interpreter([])
    response = client.post(
        "/assessments/new",
        data={"action": "interpret", "drawing_plan": (BytesIO(PDF_BYTES), "S-101.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    page = client.get(response.headers["Location"])
    assert b'value="North Annex"' in page.data


def test_interpret_without_files_or_with_bad_files_reports_error(app, client):
    calls = []
    app.config["DRAWING_INTERPRETER"] = fake_interpreter(calls)
    client.post("/assessments/new", data={"project_name": "P"})
    client.post("/assessments/1/intake", data={"action": "interpret"}, content_type="multipart/form-data")
    page = client.get("/assessments/1/intake")
    assert b"Choose at least one plan or elevation drawing" in page.data
    client.post(
        "/assessments/1/intake",
        data={"action": "interpret", "drawing_plan": (BytesIO(b"hello"), "notes.txt")},
        content_type="multipart/form-data",
    )
    page = client.get("/assessments/1/intake")
    assert b"is not a PDF, JPEG, PNG, WebP or GIF drawing" in page.data
    assert calls == []
    assert client.get("/assessments/1/export.json").get_json()["evidence"] == []


def test_missing_credentials_is_reported_not_raised(monkeypatch):
    import anthropic
    from types import SimpleNamespace
    from app.services.drawings import claude_interpreter

    monkeypatch.setattr(anthropic, "Anthropic", lambda: SimpleNamespace(api_key=None, auth_token=None, _token_cache=None))
    with pytest.raises(DrawingError, match="ANTHROPIC_API_KEY"):
        claude_interpreter([read_drawing("plan", "S-101.pdf", PDF_BYTES)])


def test_new_assessment_form_does_not_prefill_none(client):
    page = client.get("/assessments/new")
    assert b'value="None"' not in page.data
    assert b">None</textarea>" not in page.data
