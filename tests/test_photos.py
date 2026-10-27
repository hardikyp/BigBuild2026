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


def test_photo_thumbnails_open_in_lightbox_on_each_page(client):
    assessment_id = create_assessment(client)
    save_section(client, assessment_id, {
        f"photo_{ITEM_ID}": (BytesIO(image_bytes()), "beam.png"),
        f"caption_{ITEM_ID}": "Beam seat at grid C",
    })
    review = client.get(f"/assessments/{assessment_id}/review/0/0").data
    assert b'class="thumb-strip item-thumbs"' in review
    assert f'data-lightbox="item-{ITEM_ID}"'.encode() in review
    listing = client.get("/assessments").data
    assert f'data-lightbox="assessment-{assessment_id}"'.encode() in listing
    assert b'data-caption="Beam seat at grid C"' in listing
    summary = client.get(f"/assessments/{assessment_id}/summary").data
    assert b'data-lightbox="summary"' in summary


def test_assessment_card_hides_extra_photos_behind_more_link(client):
    assessment_id = create_assessment(client)
    photos = [(BytesIO(image_bytes()), f"photo-{n}.png") for n in range(8)]
    save_section(client, assessment_id, {f"photo_{ITEM_ID}": photos})
    listing = client.get("/assessments").data.decode()
    assert listing.count(f'data-lightbox="assessment-{assessment_id}"') == 8
    assert listing.count(" hidden><img") == 2
    assert "+2 more" in listing


def test_non_image_evidence_has_no_thumbnail(client):
    assessment_id = create_assessment(client)
    save_section(client, assessment_id, {f"file_{ITEM_ID}": (BytesIO(b"calc notes"), "calcs.txt")})
    assert b"data-lightbox" not in client.get("/assessments").data
    assert b"item-thumbs" not in client.get(f"/assessments/{assessment_id}/review/0/0").data


def test_thumbnail_endpoint_serves_small_upright_jpeg(client):
    assessment_id = create_assessment(client)
    exif = Image.Exif()
    exif[0x0112] = 6
    save_section(client, assessment_id, {
        f"photo_{ITEM_ID}": (BytesIO(image_bytes("JPEG", size=(3000, 1500), exif=exif)), "phone.jpg"),
    })
    evidence = client.get(f"/assessments/{assessment_id}/export.json").get_json()["evidence"][0]
    page = client.get(f"/assessments/{assessment_id}/review/0/0").data.decode()
    assert f"/assessments/{assessment_id}/evidence-thumb/" in page
    thumb_url = page.split(f'src="/assessments/{assessment_id}/evidence-thumb/', 1)[1].split('"', 1)[0]
    response = client.get(f"/assessments/{assessment_id}/evidence-thumb/{thumb_url}")
    assert response.status_code == 200
    thumb = Image.open(BytesIO(response.data))
    assert thumb.format == "JPEG"
    assert thumb.size == (160, 320)
    assert evidence["original_name"] == "phone.jpg"


def test_thumbnail_endpoint_rejects_missing_and_escaping_paths(client):
    assessment_id = create_assessment(client)
    assert client.get(f"/assessments/{assessment_id}/evidence-thumb/nope.jpg").status_code == 404
    assert client.get(f"/assessments/{assessment_id}/evidence-thumb/../../secret.jpg").status_code == 404


def test_delete_photo_removes_row_file_and_thumbnail(app, client):
    assessment_id = create_assessment(client)
    save_section(client, assessment_id, {f"photo_{ITEM_ID}": (BytesIO(image_bytes()), "delete-me.png")})
    evidence = client.get(f"/assessments/{assessment_id}/export.json").get_json()["evidence"][0]
    folder = app.config["UPLOAD_ROOT"] / str(assessment_id)
    page = client.get(f"/assessments/{assessment_id}/review/0/0").data.decode()
    assert f'id="thumb-{evidence["id"]}"' in page
    assert f'/evidence/{evidence["id"]}/delete' in page
    stored = next(path.name for path in folder.iterdir() if path.is_file())
    assert client.get(f"/assessments/{assessment_id}/evidence-thumb/{stored}").status_code == 200

    response = client.post(f"/assessments/{assessment_id}/evidence/{evidence['id']}/delete", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.data == b""
    assert client.get(f"/assessments/{assessment_id}/export.json").get_json()["evidence"] == []
    assert not (folder / stored).exists()
    assert not any((folder / "thumbs").iterdir())


def test_delete_photo_rejects_wrong_assessment(client):
    first = create_assessment(client)
    save_section(client, first, {f"photo_{ITEM_ID}": (BytesIO(image_bytes()), "keep.png")})
    evidence_id = client.get(f"/assessments/{first}/export.json").get_json()["evidence"][0]["id"]
    client.post("/assessments/new", data={"project_name": "Other"})
    assert client.post(f"/assessments/2/evidence/{evidence_id}/delete").status_code == 404
    assert client.post(f"/assessments/{first}/evidence/999/delete").status_code == 404
    assert len(client.get(f"/assessments/{first}/export.json").get_json()["evidence"]) == 1


def test_delete_assessment_removes_everything_and_returns_home(app, client):
    assessment_id = create_assessment(client)
    save_section(client, assessment_id, {
        f"status_{ITEM_ID}": "NC",
        f"photo_{ITEM_ID}": (BytesIO(image_bytes()), "gone.png"),
    })
    folder = app.config["UPLOAD_ROOT"] / str(assessment_id)
    assert folder.exists()
    for page in (f"/assessments/{assessment_id}/review/0/0", f"/assessments/{assessment_id}/summary", f"/assessments/{assessment_id}/intake"):
        assert f"/assessments/{assessment_id}/delete".encode() in client.get(page).data

    response = client.post(f"/assessments/{assessment_id}/delete")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/assessments")
    assert not folder.exists()
    assert client.get(f"/assessments/{assessment_id}/export.json").status_code == 404
    listing = client.get("/assessments").data
    assert f"/assessments/{assessment_id}/intake".encode() not in listing
    assert f"Deleted assessment #{assessment_id}".encode() in listing
