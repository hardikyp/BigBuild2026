from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Assessment, AssessmentChecklist, CalculationRecord
from app.services.assessment import applicable_sections, get_catalog_form


def checklist_item_context(session: Session, assessment: Assessment, catalog: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    """Find an applicable item and its source form for a calculation window."""

    for checklist in assessment.checklists:
        form = get_catalog_form(catalog, checklist.form_id)
        if not form:
            continue
        for section in applicable_sections(form, assessment.seismicity):
            for item in section["items"]:
                if item["item_id"] == item_id:
                    return {"checklist": checklist, "form": form, "section": section, "item": item}
    return None


def calculations_for_item(session: Session, assessment_id: int, item_id: str) -> list[CalculationRecord]:
    return list(session.scalars(
        select(CalculationRecord)
        .where(CalculationRecord.assessment_id == assessment_id, CalculationRecord.item_id == item_id)
        .order_by(CalculationRecord.created_at.desc())
    ).all())


def calculation_to_dict(record: CalculationRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "calculation_type": record.calculation_type,
        "item_id": record.item_id,
        "source_reference": record.source_reference,
        "inputs": json.loads(record.inputs_json or "{}"),
        "result": json.loads(record.result_json or "{}"),
        "engineer_determination": record.engineer_determination,
        "notes": record.notes,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
