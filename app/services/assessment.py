from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Assessment, AssessmentChecklist, Evidence, Response
from app.services.catalog import applicable_forms


ASSESSMENT_FIELDS = [
    "firm", "project_name", "project_number", "building_name", "address", "latitude", "longitude",
    "year_built", "years_remodeled", "original_design_code", "area", "length", "width", "stories",
    "story_height", "total_height", "use", "gravity_system", "transverse_walls", "longitudinal_walls",
    "roof_framing", "floor_framing", "ground_floor", "columns", "foundation", "general_condition",
    "levels_below_grade", "special_features", "longitudinal_lateral_system", "transverse_lateral_system",
    "evaluation_data", "seismicity", "performance_level", "building_type", "reviewer_notes",
]


def update_assessment_from_form(assessment: Assessment, form: Any) -> None:
    for field in ASSESSMENT_FIELDS:
        if field in form:
            setattr(assessment, field, (form.get(field) or "").strip())
    assessment.include_basic = form.get("include_basic") == "on"
    assessment.include_structural = form.get("include_structural") == "on"
    assessment.include_nonstructural = form.get("include_nonstructural") == "on"


def sync_checklists(session: Session, assessment: Assessment, catalog: dict[str, Any]) -> list[dict[str, Any]]:
    desired = applicable_forms(
        catalog,
        assessment.performance_level,
        assessment.building_type,
        assessment.seismicity,
        assessment.include_basic,
        assessment.include_structural,
        assessment.include_nonstructural,
    )
    existing = {checklist.form_id: checklist for checklist in assessment.checklists}
    desired_ids = {form["form_id"] for form in desired}
    for form_id, checklist in list(existing.items()):
        if form_id not in desired_ids:
            session.delete(checklist)
    for form in desired:
        if form["form_id"] not in existing:
            assessment.checklists.append(
                AssessmentChecklist(
                    form_id=form["form_id"],
                    source_pdf=form["source_pdf"],
                    source_hash=form["source_hash"],
                    title=form["title"],
                )
            )
    session.flush()
    return desired


def get_catalog_form(catalog: dict[str, Any], form_id: str) -> dict[str, Any] | None:
    return next((form for form in catalog["forms"] if form["form_id"] == form_id), None)


def applicable_sections(form: dict[str, Any], seismicity: str) -> list[dict[str, Any]]:
    item_by_section: dict[str, list[dict[str, Any]]] = {}
    for item in form["items"]:
        if seismicity in item["seismicity_levels"]:
            item_by_section.setdefault(item["section_id"], []).append(item)
    sections = []
    for section in form["sections"]:
        items = item_by_section.get(section["section_id"], [])
        if items:
            sections.append({**section, "items": items})
    return sections


def response_map(assessment: Assessment) -> dict[str, Response]:
    return {
        response.item_id: response
        for checklist in assessment.checklists
        for response in checklist.responses
    }


def response_for(session: Session, checklist: AssessmentChecklist, item_id: str) -> Response:
    response = session.scalar(
        select(Response).where(Response.assessment_checklist_id == checklist.id, Response.item_id == item_id)
    )
    if response is None:
        response = Response(assessment_checklist=checklist, item_id=item_id)
        session.add(response)
        session.flush()
    return response


def summary(catalog: dict[str, Any], assessment: Assessment) -> dict[str, Any]:
    counters = Counter()
    rows = []
    evidence_by_item: dict[str, list[Evidence]] = {}
    for evidence in assessment.evidence:
        evidence_by_item.setdefault(evidence.item_id, []).append(evidence)
    for checklist in assessment.checklists:
        form = get_catalog_form(catalog, checklist.form_id)
        if not form:
            continue
        responses = {response.item_id: response for response in checklist.responses}
        for section in applicable_sections(form, assessment.seismicity):
            for item in section["items"]:
                status = responses.get(item["item_id"], Response()).status or "incomplete"
                counters[status] += 1
                rows.append({
                    "checklist": checklist,
                    "form": form,
                    "section": section,
                    "item": item,
                    "response": responses.get(item["item_id"]),
                    "evidence": evidence_by_item.get(item["item_id"], []),
                })
    counters["reviewed"] = counters["C"] + counters["NC"] + counters["N/A"] + counters["U"]
    counters["total"] = sum(counters[key] for key in ("C", "NC", "N/A", "U", "incomplete"))
    return {"counters": counters, "rows": rows}
