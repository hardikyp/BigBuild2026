"""Opt-in, server-side advisory analysis of stored assessment photos."""

from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageOps

from app.domain.models import Assessment, Evidence, PhotoAnalysis
from app.services.photos import photo_mime_type


PHOTO_ANALYSIS_MODEL = "claude-opus-5-5"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_EDGE = 1568
SEVERITY_WEIGHTS = {"info": 1, "minor": 2, "moderate": 4, "severe": 8}
CONFIDENCE_WEIGHTS = {"low": 0.4, "medium": 0.7, "high": 1.0}
STATUSES = {"C", "NC", "N/A", "U"}


class PhotoAnalysisError(Exception):
    """An analysis could not be completed; the original evidence is retained."""


def _severity(value: Any, default: str = "moderate") -> str:
    return value if value in SEVERITY_WEIGHTS else default


def _confidence(value: Any, default: str = "medium") -> str:
    return value if value in CONFIDENCE_WEIGHTS else default


def normalize_interpretation(raw: dict[str, Any], model: str = PHOTO_ANALYSIS_MODEL) -> dict[str, Any]:
    """Normalize model output so templates and exports can trust its shape."""

    def objects(value: Any) -> list[dict[str, Any]]:
        return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []

    components = []
    for component in objects(raw.get("components")):
        name = str(component.get("name", "")).strip()
        if name:
            components.append({
                "name": name,
                "material": str(component.get("material", "") or "").strip(),
                "condition": str(component.get("condition", "") or "").strip(),
            })
    observations = []
    for observation in objects(raw.get("observations")):
        description = str(observation.get("description", "")).strip()
        if description:
            observations.append({
                "description": description,
                "severity": _severity(observation.get("severity")),
                "confidence": _confidence(observation.get("confidence")),
            })
    deficiencies = []
    for deficiency in objects(raw.get("possibleDeficiencies")):
        description = str(deficiency.get("description", "")).strip()
        if description:
            deficiencies.append({
                "description": description,
                "relatedChecklistItemId": str(deficiency.get("relatedChecklistItemId", "") or "").strip(),
                "severity": _severity(deficiency.get("severity")),
                "confidence": _confidence(deficiency.get("confidence"), "low"),
            })
    quality = raw.get("imageQuality") if isinstance(raw.get("imageQuality"), dict) else {}
    status = raw.get("suggestedStatus") if raw.get("suggestedStatus") in STATUSES else None
    follow_up = raw.get("followUp") if isinstance(raw.get("followUp"), list) else []
    return {
        "summary": str(raw.get("summary", "") or "").strip(),
        "components": components,
        "observations": observations,
        "possibleDeficiencies": deficiencies,
        "suggestedStatus": status,
        "statusRationale": str(raw.get("statusRationale", "") or "").strip(),
        "followUp": [str(entry).strip() for entry in follow_up if str(entry).strip()],
        "imageQuality": {
            "usable": quality.get("usable") is not False,
            "issues": [str(entry).strip() for entry in quality.get("issues", []) if str(entry).strip()]
            if isinstance(quality.get("issues", []), list) else [],
        },
        "model": model,
    }


def make_analysis_context(
    assessment: Assessment,
    *,
    item: dict[str, Any] | None,
    location: str,
    photo_description: str,
    user_note: str,
) -> dict[str, Any]:
    checklist_item = None
    if item:
        checklist_item = {
            "id": item.get("item_id", ""),
            "title": item.get("section_title", "Checklist item"),
            "text": item.get("statement", ""),
        }
    return {
        "building_type": assessment.building_type,
        "performance_level": assessment.performance_level,
        "seismicity": assessment.seismicity,
        "checklist_item": checklist_item,
        "location_in_building": location.strip(),
        "photo_description": photo_description.strip(),
        "user_note": user_note.strip(),
    }


def _prompt(context: dict[str, Any]) -> str:
    item = context.get("checklist_item") or {}
    lines = [
        "You are assisting a licensed structural engineer during an existing-building seismic site visit using ASCE 41 Tier 1.",
        "Describe only visible conditions. This is advisory decision support, not a certification or retrofit design.",
        "Return only JSON matching the requested schema. Use Unknown when the image cannot settle an issue.",
        f"Building type: {context.get('building_type') or 'not provided'}",
        f"Performance level: {context.get('performance_level') or 'not provided'}",
        f"Seismicity: {context.get('seismicity') or 'not provided'}",
        f"Location in building: {context.get('location_in_building') or 'not provided'}",
        f"Photo description: {context.get('photo_description') or 'not provided'}",
        f"Engineer note: {context.get('user_note') or 'not provided'}",
    ]
    if item:
        lines.extend([f"Checklist item: [{item.get('id')}] {item.get('title')}", f"Statement: {item.get('text')}" , "Give a suggested status only as an advisory suggestion."])
    else:
        lines.append("No checklist item is attached; set suggestedStatus to null.")
    lines.append("Report summary, visible components, observations with severity/confidence, possible deficiencies with severity/confidence, image limitations, and follow-up checks.")
    return "\n".join(lines)


OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "components": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "name": {"type": "string"}, "material": {"type": ["string", "null"]}, "condition": {"type": ["string", "null"]},
        }, "required": ["name", "material", "condition"]}},
        "observations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "description": {"type": "string"}, "severity": {"type": "string", "enum": list(SEVERITY_WEIGHTS)}, "confidence": {"type": "string", "enum": list(CONFIDENCE_WEIGHTS)},
        }, "required": ["description", "severity", "confidence"]}},
        "possibleDeficiencies": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "description": {"type": "string"}, "relatedChecklistItemId": {"type": ["string", "null"]}, "severity": {"type": "string", "enum": list(SEVERITY_WEIGHTS)}, "confidence": {"type": "string", "enum": list(CONFIDENCE_WEIGHTS)},
        }, "required": ["description", "relatedChecklistItemId", "severity", "confidence"]}},
        "suggestedStatus": {"type": ["string", "null"], "enum": ["C", "NC", "N/A", "U", None]},
        "statusRationale": {"type": ["string", "null"]},
        "followUp": {"type": "array", "items": {"type": "string"}},
        "imageQuality": {"type": "object", "additionalProperties": False, "properties": {"usable": {"type": "boolean"}, "issues": {"type": "array", "items": {"type": "string"}}}, "required": ["usable", "issues"]},
    },
    "required": ["summary", "components", "observations", "possibleDeficiencies", "suggestedStatus", "statusRationale", "followUp", "imageQuality"],
}


def analysis_image(path: Path, mime_type: str) -> tuple[str, bytes]:
    """Prepare a bounded, upright JPEG for the remote model without changing evidence."""

    data = path.read_bytes()
    if len(data) <= MAX_IMAGE_BYTES:
        with Image.open(BytesIO(data)) as source:
            if max(source.size) <= MAX_IMAGE_EDGE and mime_type in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                return mime_type, data
    try:
        with Image.open(BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=85, optimize=True)
    except (OSError, ValueError) as error:
        raise PhotoAnalysisError("This evidence photo could not be prepared for analysis.") from error
    return "image/jpeg", buffer.getvalue()


def claude_analyzer(evidence: Evidence, context: dict[str, Any], upload_root: Path) -> dict[str, Any]:
    """Call Claude from the server; credentials never enter the browser."""

    path = upload_root / str(evidence.assessment_id) / evidence.stored_name
    if not path.is_file() or not evidence.is_image:
        raise PhotoAnalysisError("The stored evidence photo is unavailable for analysis.")
    mime_type, data = analysis_image(path, evidence.mime_type)
    try:
        import anthropic

        client = anthropic.Anthropic()
        if not (client.api_key or client.auth_token or getattr(client, "_token_cache", None)):
            raise PhotoAnalysisError("Photo analysis needs Claude API credentials. Set ANTHROPIC_API_KEY and restart MORGAN.")
        response = client.beta.messages.create(
            model=PHOTO_ANALYSIS_MODEL,
            max_tokens=5000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            system="Return concise, structured, advisory field-photo observations. Never claim a photo certifies compliance.",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": _prompt(context)},
                {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": base64.b64encode(data).decode("ascii")}},
            ]}],
        )
    except PhotoAnalysisError:
        raise
    except anthropic.AuthenticationError as error:
        raise PhotoAnalysisError("Photo analysis authentication failed. Set ANTHROPIC_API_KEY and restart MORGAN.") from error
    except anthropic.RateLimitError as error:
        raise PhotoAnalysisError("Claude is rate limiting photo analysis. Try again shortly.") from error
    except anthropic.APIConnectionError as error:
        raise PhotoAnalysisError("Could not reach the Claude API. Check the network connection.") from error
    except anthropic.AnthropicError as error:
        raise PhotoAnalysisError(f"Photo analysis failed: {error}") from error
    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise PhotoAnalysisError("The photo analysis response was not valid structured JSON. Try again.") from error
    if not isinstance(payload, dict):
        raise PhotoAnalysisError("The photo analysis response was not a JSON object. Try again.")
    return normalize_interpretation(payload, getattr(response, "model", PHOTO_ANALYSIS_MODEL))


def analysis_to_dict(record: PhotoAnalysis) -> dict[str, Any]:
    return {
        "id": record.id,
        "evidence_id": record.evidence_id,
        "attempt_number": record.attempt_number,
        "status": record.status,
        "model": record.model,
        "context": record.context,
        "result": record.result,
        "error_message": record.error_message,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


def build_ongoing_considerations(analyses: Iterable[PhotoAnalysis]) -> list[dict[str, Any]]:
    """Deduplicate and rank advisory findings from successful photo analyses."""

    candidates: list[dict[str, Any]] = []
    for analysis in analyses:
        if analysis.status != "succeeded":
            continue
        context = analysis.context
        result = analysis.result
        location = str(context.get("location_in_building", "")).strip()
        source = analysis.evidence
        for finding in list(result.get("observations", [])) + list(result.get("possibleDeficiencies", [])):
            if not isinstance(finding, dict) or not str(finding.get("description", "")).strip():
                continue
            candidates.append({
                "description": str(finding["description"]).strip(),
                "severity": _severity(finding.get("severity")),
                "confidence": _confidence(finding.get("confidence"), "low"),
                "evidence_id": analysis.evidence_id,
                "original_name": source.original_name if source else "",
                "stored_name": source.stored_name if source else "",
                "item_id": source.item_id if source else "",
                "location": location,
                "kind": "finding",
            })
        related = list(result.get("observations", [])) + list(result.get("possibleDeficiencies", []))
        strongest = max((
            (_severity(item.get("severity")), _confidence(item.get("confidence"), "low"))
            for item in related if isinstance(item, dict)
        ), key=lambda pair: SEVERITY_WEIGHTS[pair[0]] * CONFIDENCE_WEIGHTS[pair[1]], default=("minor", "low"))
        for follow_up in result.get("followUp", []):
            if str(follow_up).strip():
                candidates.append({
                    "description": str(follow_up).strip(),
                    "severity": strongest[0],
                    "confidence": strongest[1],
                    "evidence_id": analysis.evidence_id,
                    "original_name": source.original_name if source else "",
                    "stored_name": source.stored_name if source else "",
                    "item_id": source.item_id if source else "",
                    "location": location,
                    "kind": "follow-up",
                })

    groups: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]+", " ", candidate["description"].lower()).strip()
        if key:
            groups.setdefault(key, []).append(candidate)

    considerations = []
    for group in groups.values():
        strongest = max(group, key=lambda item: SEVERITY_WEIGHTS[item["severity"]] * CONFIDENCE_WEIGHTS[item["confidence"]])
        evidence_ids = list(dict.fromkeys(item["evidence_id"] for item in group))
        recurrence_multiplier = min(1.8, 1 + 0.2 * (len(evidence_ids) - 1))
        score = round(SEVERITY_WEIGHTS[strongest["severity"]] * CONFIDENCE_WEIGHTS[strongest["confidence"]] * recurrence_multiplier, 2)
        priority = "urgent" if score >= 6 else "high" if score >= 3 else "monitor" if score >= 1.5 else "routine"
        considerations.append({
            "description": strongest["description"],
            "severity": strongest["severity"],
            "confidence": strongest["confidence"],
            "priority_score": score,
            "priority": priority,
            "supporting_photos": len(evidence_ids),
            "locations": list(dict.fromkeys(item["location"] for item in group if item["location"])),
            "kinds": sorted(set(item["kind"] for item in group)),
            "supporting_evidence": [
                {"id": item["evidence_id"], "original_name": item["original_name"], "stored_name": item["stored_name"], "item_id": item["item_id"]}
                for evidence_id in evidence_ids
                for item in group if item["evidence_id"] == evidence_id
            ],
        })
    return sorted(considerations, key=lambda item: (-item["priority_score"], item["description"].lower()))
