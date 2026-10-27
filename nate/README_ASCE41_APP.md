# MORGAN - ASCE 41 Tier 1 Navigator

## Run
```bash
python -m pip install streamlit pandas
streamlit run asce41_tier1_app.py
```

## What the prototype does
- Captures project metadata, building type, seismicity, and performance objective.
- Filters checklist statements by applicability.
- Records C / NC / N/A / Unknown plus basis, evidence, and follow-up.
- Highlights unresolved items and exports CSV and JSON.
- Accepts a verified checklist CSV so the licensed standard content is separated from application code.

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
