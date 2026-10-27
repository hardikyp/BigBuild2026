# MORGAN - ASCE 41 Tier 1 Navigator

## Run
```bash
python -m pip install streamlit pandas anthropic pillow pytest
export ANTHROPIC_API_KEY=sk-ant-...   # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
streamlit run asce41_tier1_app.py
python -m pytest                      # field_capture tests
```

Without `ANTHROPIC_API_KEY`, the app still runs and keeps photos, but photo interpretation is off. Set `ANTHROPIC_MODEL` to override the default model (`claude-sonnet-5-5`).

## What the prototype does
- Captures project metadata, building type, seismicity, and performance objective.
- Filters checklist statements by applicability.
- Records C / NC / N/A / Unknown plus basis, evidence, and follow-up.
- Highlights unresolved items and exports CSV and JSON.
- Accepts a verified checklist CSV so the licensed standard content is separated from application code.
- Site photos per checklist item (camera or upload). Claude interprets each photo in the context of the building and item, and suggests an **advisory** status the engineer can apply with "Use this status". Photos export as a ZIP, and interpretations go into the CSV and JSON exports.
- Loads checklist items from the team's checklist file `src/ASCE 41.txt` at startup (`checklist_text.py`); falls back to the starter rows if it's missing. Set `MORGAN_CHECKLIST_TXT` to use another file.
- **End site visit** (sidebar): Claude reviews all responses and photo interpretations and proposes what is still to check, split into "before leaving site" and "office follow-up". The engineer ticks off checks, then confirms to close the project (read-only, reopenable) and downloads a self-contained HTML report with the findings, checks and photo log. Without an API key, the list comes from unresolved items and photo follow-ups.

## Field capture (`field_capture.py`)
Pure Python, no Node.js needed. It resizes photos to 1568 px JPEG, applies EXIF orientation and strips metadata, then asks Claude for a structured interpretation via a forced tool call.

## Production backlog
1. Populate and independently QA every Chapter 17 table against the licensed ASCE 41-17 PDF.
2. Implement the exact Table 4-6 applicability matrix and all building-type limitations.
3. Add guided Quick Check calculators with units, assumptions, equations, and calculation audit trails.
4. Add multi-component instances (each wall line, diaphragm, frame, connection, etc.).
5. Add evidence uploads, drawing/photo markup, revision history, reviewer sign-off, and immutable exports.
6. Add report generation with source page/table references and explicit exceptions.
7. Add tests for every combination of building type, objective, seismicity, and checklist branch.

## Checklist CSV fields
`id, checklist, building_types, performance, seismicity, section, topic, statement, tier2_ref, commentary_ref`

The included rows are only a starter demonstration. Verify all wording, references, applicability, and calculations before engineering use.
