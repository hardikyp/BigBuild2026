from __future__ import annotations

import json
from pathlib import Path

from flask import Flask

from app.repositories.db import database_url, initialize_database, make_engine, make_session_factory
from app.services.catalog import build_catalog
from app.web.routes import bp


def create_app(test_config: dict | None = None) -> Flask:
    root = Path(__file__).resolve().parents[1]
    source_root = root / "src" / "ASCE 41-23 Tier 1 checklist for seismic evaluation and retrofit of existing buildings"
    catalog_path = root / "app" / "data" / "checklists.json"
    if not catalog_path.exists():
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(json.dumps(build_catalog(source_root), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY="morgan-local-development",
        DATABASE_PATH=Path(app.instance_path) / "morgan.sqlite3",
        UPLOAD_ROOT=Path(app.instance_path) / "uploads",
        CATALOG_PATH=catalog_path,
        # Room for several full-resolution phone photos in one section save.
        MAX_CONTENT_LENGTH=64 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_ROOT"]).mkdir(parents=True, exist_ok=True)
    engine = make_engine(database_url(Path(app.config["DATABASE_PATH"])))
    initialize_database(engine)
    app.extensions["morgan_session"] = make_session_factory(engine)
    app.extensions["morgan_catalog"] = json.loads(Path(app.config["CATALOG_PATH"]).read_text(encoding="utf-8"))
    app.register_blueprint(bp)
    return app
