# MORGAN database migrations

The application records applied schema versions in the SQLite `schema_migrations` table. `001_initial` creates the SQLAlchemy domain tables and is applied automatically when the local database is first opened. `002_evidence_report_flag` adds `evidence.include_in_report` (default true) so reviewers can choose which photos appear in the PDF report; existing evidence rows are kept and default to included. Future schema changes should add a new numbered migration and preserve existing assessment data.
