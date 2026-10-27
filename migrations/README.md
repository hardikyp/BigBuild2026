# MORGAN database migrations

The application records applied schema versions in the SQLite `schema_migrations` table. `001_initial` creates the SQLAlchemy domain tables and is applied automatically when the local database is first opened. Future schema changes should add a new numbered migration and preserve existing assessment data.
