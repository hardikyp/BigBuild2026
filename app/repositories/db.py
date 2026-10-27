from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.domain.models import Base


def make_engine(database_url: str):
    return create_engine(database_url, future=True)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database(engine) -> None:
    # The first local migration is intentionally small and idempotent. Future
    # schema changes can add numbered migrations without changing app startup.
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(32) PRIMARY KEY)"))
        applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
        if "001_initial" not in applied:
            Base.metadata.create_all(connection)
            connection.execute(text("INSERT INTO schema_migrations(version) VALUES ('001_initial')"))
        if "002_evidence_report_flag" not in applied:
            # Databases created after this column was added already have it
            # from create_all; older databases need it added in place.
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(evidence)"))}
            if "include_in_report" not in columns:
                connection.execute(text("ALTER TABLE evidence ADD COLUMN include_in_report BOOLEAN NOT NULL DEFAULT 1"))
            connection.execute(text("INSERT INTO schema_migrations(version) VALUES ('002_evidence_report_flag')"))
        if "003_drawing_interpretations" not in applied:
            # create_all only adds tables that are missing.
            Base.metadata.create_all(connection)
            connection.execute(text("INSERT INTO schema_migrations(version) VALUES ('003_drawing_interpretations')"))


def database_url(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"
