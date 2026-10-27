# AGENTS.md

## App description

A Python web application that helps engineers:

- Identify the applicable Tier-1 checklist and building type.
- Work through checklist items in a structured workflow.
- Record findings, evidence, comments, photos, and reviewer notes.
- Track incomplete, failed, or investigation-required items.
- Export a traceable review package.

The app is decision support only. It must not replace a licensed professional’s judgment, certify a building, or independently prescribe a retrofit.

## Project status and priorities

Document the current phase:

- Source checklist ingestion and preservation.
- Domain model and checklist navigation.
- Review workflow and persistence.
- Reporting/export.
- Authentication and collaboration, if applicable.

## Current toolchain

The project currently uses the following development and runtime toolchain:

- Conda environment: `py-bigbuild`
- Python: 3.11
- Web framework: Flask 3.1.3
- Templates and frontend enhancement: Jinja2 with HTMX 1.9.12
- Persistence: SQLAlchemy 2.1.6 with SQLite
- PDF generation: ReportLab 4.5.1
- Test runner: pytest 8.4.2
- PDF rendering/visual QA: Poppler `pdftoppm`
- Dependency source of truth: `requirements.txt`

Anyone working on this project must use the `py-bigbuild` Conda environment and the same toolchain when implementing new features. Keep new dependencies compatible with the versions and constraints in `requirements.txt`, update that file when a dependency is intentionally changed, and run the existing test suite before handoff.

## Repository structure

Document the intended layout, for example:

```text
src/
  ASCE 41-23 Tier 1 checklist for seismic evaluation and retrofit of existing buildings/
    CP Forms/
    IO Forms/
    Nonstructural Form/
    Summary Data Sheet/
    Txt_files/

app/
  web/              # Routes, views, templates
  domain/           # Checklist and assessment models
  services/         # Application workflows
  repositories/     # Persistence
  exports/          # PDF/JSON/report generation

tests/
  unit/
  integration/
  fixtures/

scripts/
docs/
