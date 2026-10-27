from __future__ import annotations

import json
from typing import Any

from app.services.assessment import applicable_sections, get_catalog_form, summary


def assessment_json(catalog: dict[str, Any], assessment) -> dict[str, Any]:
    rollup = summary(catalog, assessment)
    response_map = {response.item_id: response for checklist in assessment.checklists for response in checklist.responses}
    evidence_by_item: dict[str, list[Any]] = {}
    for evidence in assessment.evidence:
        evidence_by_item.setdefault(evidence.item_id, []).append(evidence)
    assessment_fields = {
        column.name: getattr(assessment, column.name)
        for column in assessment.__table__.columns
        if column.name not in {"id", "created_at", "updated_at"}
    }
    forms = []
    for checklist in assessment.checklists:
        form = get_catalog_form(catalog, checklist.form_id)
        if not form:
            continue
        sections = []
        for section in applicable_sections(form, assessment.seismicity):
            sections.append({
                "section_id": section["section_id"],
                "order": section["order"],
                "title": section["title"],
                "items": [
                    {
                        **{key: item[key] for key in ("item_id", "order", "statement", "tier2_reference", "commentary_reference")},
                        "response": {
                            "status": response_map.get(item["item_id"]).status if response_map.get(item["item_id"]) else "",
                            "comment": response_map.get(item["item_id"]).comment if response_map.get(item["item_id"]) else "",
                            "reviewer_note": response_map.get(item["item_id"]).reviewer_note if response_map.get(item["item_id"]) else "",
                        },
                        "evidence": [
                            {
                                "id": evidence.id,
                                "original_name": evidence.original_name,
                                "mime_type": evidence.mime_type,
                                "caption": evidence.caption,
                                "sha256": evidence.sha256,
                                "include_in_report": evidence.include_in_report,
                            }
                            for evidence in evidence_by_item.get(item["item_id"], [])
                        ],
                    }
                    for item in section["items"]
                ],
            })
        forms.append({
            "form_id": form["form_id"],
            "title": form["title"],
            "performance_level": form["performance_level"],
            "building_type": form["building_type"],
            "source_pdf": form["source_pdf"],
            "source_text": form["source_text"],
            "source_hash": form["source_hash"],
            "sections": sections,
        })
    return {
        "schema_version": "1.0",
        "catalog_version": catalog["catalog_version"],
        "decision_support_notice": "This package is decision support only and does not certify a building or prescribe a retrofit.",
        "assessment": {"id": assessment.id, **assessment_fields},
        "summary": dict(rollup["counters"]),
        "checklists": forms,
        "evidence": [
            {
                "id": evidence.id,
                "item_id": evidence.item_id,
                "original_name": evidence.original_name,
                "mime_type": evidence.mime_type,
                "caption": evidence.caption,
                "sha256": evidence.sha256,
                "include_in_report": evidence.include_in_report,
                "created_at": evidence.created_at.isoformat() if evidence.created_at else None,
            }
            for evidence in assessment.evidence
        ],
        "drawing_interpretations": [
            {
                "id": record.id,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "model": record.model,
                "evidence_ids": json.loads(record.evidence_ids or "[]"),
                "applied_fields": record.applied,
                "kept_fields": record.kept,
                **record.result,
            }
            for record in assessment.drawing_interpretations
        ],
    }
