from io import BytesIO

from PIL import Image
from sqlalchemy import create_engine, text

from app.repositories.db import initialize_database
from app.services.photos import photo_mime_type, report_image
from tests.conftest import create_assessment


ITEM_ID = "17-1-2io-basic-item-001"


def image_bytes(fmt="PNG", size=(40, 20), exif=None):
    buffer = BytesIO()
    image = Image.new("RGB", size, (180, 60, 40))
    if exif is not None:
        image.save(buffer, format=fmt, exif=exif)
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


def save_section(client, assessment_id, data):
    return client.post(
        f"/assessments/{assessment_id}/review/0/0",
        data={**data, "action": "summary"},
        content_type="multipart/form-data",
    )


def test_photo_is_saved_shown_and_exported(client):
    assessment_id = create_assessment(client)
    response = save_section(client, assessment_id, {
        f"status_{ITEM_ID}": "NC",
        f"photo_{ITEM_ID}": (BytesIO(image_bytes()), "north-wall.png"),
        f"caption_{ITEM_ID}": "North wall crack",
        f"include_{ITEM_ID}": "on",
    })
    assert response.status_code == 302
    evidence = client.get(f"/assessments/{assessment_id}/export.json").get_json()["evidence"]
    assert evidence[0]["mime_type"] == "image/png"
    assert evidence[0]["include_in_report"] is True
    page = client.get(f"/assessments/{assessment_id}/review/0/0")
    assert b'class="evidence-thumb"' in page.data
    assert b"North wall crack" in page.data


def test_photo_mime_type_comes_from_file_contents(client):
    assessment_id = create_assessment(client)
    save_section(client, assessment_id, {
        f"photo_{ITEM_ID}": (BytesIO(image_bytes("JPEG")), "mislabeled.png", "image/png"),
    })
    evidence = client.get(f"/assessments/{assessment_id}/export.json").get_json()["evidence"]
    assert evidence[0]["mime_type"] == "image/jpeg"


def test_non_image_photo_is_rejected(client):
    assessment_id = create_assessment(client)
    response = save_section(client, assessment_id, {
        f"status_{ITEM_ID}": "C",
        f"photo_{ITEM_ID}": (BytesIO(b"not really a photo"), "fake.jpg", "image/jpeg"),
    })
    assert response.status_code == 302
    data = client.get(f"/assessments/{assessment_id}/export.json").get_json()
    assert data["evidence"] == []
    assert data["summary"]["C"] == 1
    page = client.get(response.headers["Location"])
    assert b"fake.jpg" in page.data


def test_report_toggle_controls_pdf_photos(client):
    assessment_id = create_assessment(client)
    save_section(client, assessment_id, {
        f"photo_{ITEM_ID}": (BytesIO(image_bytes()), "roof.png"),
        f"include_{ITEM_ID}": "on",
    })
    with_photo = client.get(f"/assessments/{assessment_id}/export.pdf").data
    assert b"/Subtype /Image" in with_photo

    evidence_id = client.get(f"/assessments/{assessment_id}/export.json").get_json()["evidence"][0]["id"]
    save_section(client, assessment_id, {"evidence_on_page": str(evidence_id)})
    data = client.get(f"/assessments/{assessment_id}/export.json").get_json()
    assert data["evidence"][0]["include_in_report"] is False
    without_photo = client.get(f"/assessments/{assessment_id}/export.pdf").data
    assert b"/Subtype /Image" not in without_photo


def test_pdf_tolerates_missing_photo_file(app, client):
    assessment_id = create_assessment(client)
    save_section(client, assessment_id, {
        f"photo_{ITEM_ID}": (BytesIO(image_bytes()), "gone.png"),
        f"include_{ITEM_ID}": "on",
    })
    for path in (app.config["UPLOAD_ROOT"] / str(assessment_id)).iterdir():
        path.unlink()
    response = client.get(f"/assessments/{assessment_id}/export.pdf")
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF")


def test_photo_mime_type_detects_supported_formats():
    assert photo_mime_type(image_bytes("JPEG")) == "image/jpeg"
    assert photo_mime_type(image_bytes("WEBP")) == "image/webp"
    assert photo_mime_type(image_bytes("BMP")) is None
    assert photo_mime_type(b"plain text") is None


def test_report_image_is_upright_and_downscaled(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees clockwise to display
    path = tmp_path / "phone.jpg"
    path.write_bytes(image_bytes("JPEG", size=(4000, 2000), exif=exif))
    _, width, height = report_image(path)
    assert (width, height) == (800, 1600)


def test_migration_adds_report_flag_to_existing_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.sqlite3'}")
    initialize_database(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE evidence"))
        connection.execute(text(
            "CREATE TABLE evidence (id INTEGER PRIMARY KEY, assessment_id INTEGER, item_id VARCHAR(160), "
            "stored_name VARCHAR(255), original_name VARCHAR(255), mime_type VARCHAR(120), caption TEXT, "
            "sha256 VARCHAR(64), created_at DATETIME)"
        ))
        connection.execute(text("INSERT INTO evidence (id, assessment_id, item_id, stored_name, original_name) VALUES (1, 1, 'x', 's', 'o')"))
        connection.execute(text("DELETE FROM schema_migrations WHERE version = '002_evidence_report_flag'"))
    initialize_database(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT include_in_report FROM evidence WHERE id = 1")).scalar() == 1
