from pathlib import Path

import pytest

from app.factory import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_PATH": tmp_path / "test.sqlite3",
        "UPLOAD_ROOT": tmp_path / "uploads",
    })


@pytest.fixture()
def client(app):
    return app.test_client()


def create_assessment(client, *, performance="IO", building_type="S1", seismicity="high", nonstructural=False):
    client.post("/assessments/new", data={"project_name": "Test Project", "building_name": "Test Building"})
    data = {
        "project_name": "Test Project",
        "building_name": "Test Building",
        "performance_level": performance,
        "building_type": building_type,
        "seismicity": seismicity,
        "include_basic": "on",
        "include_structural": "on",
    }
    if nonstructural:
        data["include_nonstructural"] = "on"
    response = client.post("/assessments/1/intake", data=data)
    assert response.status_code == 302
    return 1
