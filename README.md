# MORGAN: Methodical Observation and Review Guided Assessment Navigator

MORGAN is a web app that walks users through the process of performing a Tier 1 checklist for the seismic retrofit assessment of existing buildings.

This project is a minimum viable web app build created as part of the Big Build 2026 hackathon during the NCSEA Summit 2026.

## Team Members

- Astrid Fischer
- Hardik Patil
- Jerry Zhai
- Luke Demo
- Jaewon Saw
- Yingjie Wu
- Nate Levine

## Current phase

The first usable workflow is implemented: source checklist normalization, guided assessment intake, cumulative checklist navigation, item responses, evidence uploads, progress summaries, and PDF/JSON export. Authentication, collaboration, and hosted storage remain out of scope for this local MVP.

## Run locally with Conda

Create and activate the project environment:

```bash
conda create -n py-bigbuild python=3.11 pip
conda activate py-bigbuild
python -m pip install -r requirements.txt
```

Initialize the checklist catalog and start the application:

```bash
python scripts/ingest_checklists.py
python run.py
```

Open <http://127.0.0.1:5000>. The default SQLite database and uploaded evidence are stored under `instance/`.

When the environment already exists, use:

```bash
conda activate py-bigbuild
python -m pip install -r requirements.txt
python scripts/ingest_checklists.py
python run.py
```

## Test

```bash
conda activate py-bigbuild
PYTHONDONTWRITEBYTECODE=1 pytest -q
```

The source PDFs remain authoritative visual references. The normalized catalog in `app/data/checklists.json` is generated from the supplied text extractions and records each source hash and source path for traceability.
