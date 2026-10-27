from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Callable

from PIL import Image, ImageOps

from app.domain.models import Assessment
from app.services.photos import photo_mime_type


MODEL = "claude-opus-5-5"
DRAWING_ROLES = {"plan": "Floor / framing plan", "elevation": "Building elevation"}
CONFIDENCE_LEVELS = ["high", "medium", "low"]
BUILDING_TYPES = [
    "W1", "W2", "S1", "S2", "S3", "S4", "S5", "CFS1", "CFS2", "C1", "C2", "C3",
    "PC1", "PC2", "PC2A", "RM1", "URM",
]
# Intake fields a set of plans and elevations can reasonably show, with the
# guidance Claude gets for each. Seismicity, performance objective, condition
# and evaluation notes stay with the engineer and are never inferred.
DRAWING_FIELDS = {
    "project_name": "Project name from the title block.",
    "project_number": "Project or job number from the title block.",
    "building_name": "Building name from the title block or drawing titles.",
    "address": "Street address of the building from the title block.",
    "year_built": "Year of the original drawings (issue or seal date), only if shown.",
    "original_design_code": "Design code named in general notes, e.g. '1979 UBC'.",
    "area": "Gross floor area with units, e.g. '12,400 sf'. Compute from plan dimensions only if they are clear.",
    "length": "Overall plan dimension in the longitudinal (longer) direction, with units.",
    "width": "Overall plan dimension in the transverse (shorter) direction, with units.",
    "stories": "Number of stories above grade.",
    "story_height": "Typical floor-to-floor height with units; list each if they differ.",
    "total_height": "Height from grade to roof with units.",
    "use": "Occupancy or use, e.g. 'Office', 'School', 'Residential'.",
    "gravity_system": "Gravity load-carrying system.",
    "transverse_walls": "Exterior walls in the transverse direction: material and construction.",
    "longitudinal_walls": "Exterior walls in the longitudinal direction: material and construction.",
    "roof_framing": "Roof materials and framing.",
    "floor_framing": "Intermediate floor materials and framing.",
    "ground_floor": "Ground floor construction, e.g. slab on grade.",
    "columns": "Column material and typical size.",
    "foundation": "Foundation type.",
    "levels_below_grade": "Number of levels below grade (0 if none are shown and the elevation shows grade at the ground floor).",
    "special_features": "Configuration features relevant to a Tier 1 screen: setbacks, soft or weak stories, re-entrant corners, mezzanines, openings in diaphragms, adjacent buildings.",
    "longitudinal_lateral_system": "Seismic-force-resisting system in the longitudinal direction.",
    "transverse_lateral_system": "Seismic-force-resisting system in the transverse direction.",
    "building_type": "ASCE 41 common building type code. Must be one of: " + ", ".join(BUILDING_TYPES) + ".",
}

SYSTEM_PROMPT = """You help a structural engineer start an ASCE 41-23 Tier 1 seismic evaluation by reading the building's existing drawings.

Report only what the drawings show or what follows directly from dimensions, notes, schedules or sections on them. Leave a field out rather than guess. For each value, say where on the drawings it came from (sheet, note, dimension string or detail) and how sure you are:
- high: stated directly on the drawings
- medium: derived from clear dimensions or strongly implied by details
- low: an informed reading of ambiguous or partial information

Give lengths and areas with units as drawn. Keep each value short enough to drop into a form field. The engineer reviews and owns every value; your output is a draft, not a determination."""


@dataclass
class Drawing:
    role: str
    filename: str
    mime_type: str
    data: bytes


@dataclass
class InterpretedField:
    field: str
    value: str
    confidence: str
    basis: str


@dataclass
class Interpretation:
    fields: list[InterpretedField]
    notes: str = ""
    model: str = MODEL
    raw: dict[str, Any] = field(default_factory=dict)


class DrawingError(Exception):
    """A drawing could not be read or interpreted; the message is safe to show the user."""


Interpreter = Callable[[list[Drawing]], Interpretation]

# The Messages API takes images up to 5 MB and requests up to 32 MB; base64
# grows payloads by a third, so the raw upload budget is about 22 MB.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_EDGE = 2576
MAX_TOTAL_BYTES = 22 * 1024 * 1024


def read_drawing(role: str, filename: str, data: bytes) -> Drawing:
    """Identify an uploaded drawing from its bytes, not its name or browser-supplied type."""
    if data.startswith(b"%PDF-"):
        return Drawing(role, filename, "application/pdf", data)
    mime_type = photo_mime_type(data)
    if mime_type is None:
        raise DrawingError(f"{filename} is not a PDF, JPEG, PNG, WebP or GIF drawing.")
    return Drawing(role, filename, mime_type, data)


def fit_image(drawing: Drawing) -> tuple[str, bytes]:
    """Return a copy of an image drawing small enough for the API, keeping line work legible."""
    with Image.open(BytesIO(drawing.data)) as source:
        if len(drawing.data) <= MAX_IMAGE_BYTES and max(source.size) <= MAX_IMAGE_EDGE:
            return drawing.mime_type, drawing.data
        image = ImageOps.exif_transpose(source)
        image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    if buffer.tell() <= MAX_IMAGE_BYTES:
        return "image/png", buffer.getvalue()
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return "image/jpeg", buffer.getvalue()


def content_blocks(drawings: list[Drawing]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    total = 0
    for index, drawing in enumerate(drawings, start=1):
        label = f"Drawing {index}: {DRAWING_ROLES.get(drawing.role, drawing.role)} ({drawing.filename})"
        blocks.append({"type": "text", "text": label})
        if drawing.mime_type == "application/pdf":
            mime_type, data = drawing.mime_type, drawing.data
            source = {"type": "base64", "media_type": mime_type, "data": base64.standard_b64encode(data).decode("ascii")}
            blocks.append({"type": "document", "source": source, "title": drawing.filename})
        else:
            mime_type, data = fit_image(drawing)
            source = {"type": "base64", "media_type": mime_type, "data": base64.standard_b64encode(data).decode("ascii")}
            blocks.append({"type": "image", "source": source})
        total += len(data)
    if total > MAX_TOTAL_BYTES:
        raise DrawingError("The drawings are too large to interpret together (over 22 MB). Upload only the relevant sheets.")
    field_guide = "\n".join(f"- {name}: {hint}" for name, hint in DRAWING_FIELDS.items())
    blocks.append({
        "type": "text",
        "text": f"Fill in what these drawings support for the following intake fields:\n{field_guide}\n\n"
                "In notes, flag anything the engineer should check in person or on other sheets.",
    })
    return blocks


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": list(DRAWING_FIELDS)},
                    "value": {"type": "string"},
                    "confidence": {"type": "string", "enum": CONFIDENCE_LEVELS},
                    "basis": {"type": "string"},
                },
                "required": ["field", "value", "confidence", "basis"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["fields", "notes"],
    "additionalProperties": False,
}


def parse_interpretation(payload: dict[str, Any], model: str = MODEL) -> Interpretation:
    fields: dict[str, InterpretedField] = {}
    for entry in payload.get("fields", []):
        name = entry.get("field")
        value = " ".join(str(entry.get("value", "")).split())
        if name not in DRAWING_FIELDS or not value:
            continue
        if name == "building_type":
            value = value.upper().replace("C2A", "C2")
            if value not in BUILDING_TYPES:
                continue
        confidence = entry.get("confidence") if entry.get("confidence") in CONFIDENCE_LEVELS else "low"
        # Keep the first answer for a field; the schema allows repeats.
        fields.setdefault(name, InterpretedField(name, value, confidence, str(entry.get("basis", "")).strip()))
    return Interpretation(list(fields.values()), str(payload.get("notes", "")).strip(), model, payload)


MISSING_CREDENTIALS = "Drawing interpretation needs Claude API credentials. Set ANTHROPIC_API_KEY (or run `ant auth login`) and restart MORGAN."


def has_credentials(client) -> bool:
    # The SDK resolves an API key, auth token or `ant auth login` profile at
    # construction and only fails, with a TypeError, once a request is built.
    return bool(client.api_key or client.auth_token or getattr(client, "_token_cache", None))


def claude_interpreter(drawings: list[Drawing]) -> Interpretation:
    import anthropic

    try:
        client = anthropic.Anthropic()
        if not has_credentials(client):
            raise DrawingError(MISSING_CREDENTIALS)
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content_blocks(drawings)}],
        )
    except anthropic.AuthenticationError as error:
        raise DrawingError(MISSING_CREDENTIALS) from error
    except anthropic.RateLimitError as error:
        raise DrawingError("Claude is rate limiting requests. Try the drawings again in a minute.") from error
    except anthropic.BadRequestError as error:
        raise DrawingError(f"Claude could not read these drawings: {error.message}") from error
    except anthropic.APIStatusError as error:
        raise DrawingError(f"Claude returned an error ({error.status_code}). Try again shortly.") from error
    except anthropic.APIConnectionError as error:
        raise DrawingError("Could not reach the Claude API. Check the network connection.") from error
    except anthropic.AnthropicError as error:
        raise DrawingError(f"Drawing interpretation failed: {error}") from error
    if response.stop_reason == "refusal":
        raise DrawingError("Claude declined to interpret these drawings.")
    if response.stop_reason == "max_tokens":
        raise DrawingError("Claude's answer was cut off. Try fewer sheets at a time.")
    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise DrawingError("Claude's answer could not be read. Try again.") from error
    return parse_interpretation(payload, response.model)


@dataclass
class ApplyResult:
    applied: list[str]
    kept: list[str]


def apply_interpretation(assessment: Assessment, interpretation: Interpretation, *, overwrite: bool = False) -> ApplyResult:
    """Copy interpreted values onto the assessment.

    Fields the engineer already filled in are kept unless overwrite is set,
    and identical values count as neither applied nor kept.
    """
    applied: list[str] = []
    kept: list[str] = []
    for entry in interpretation.fields:
        current = (getattr(assessment, entry.field) or "").strip()
        if current == entry.value:
            continue
        if current and not overwrite:
            kept.append(entry.field)
            continue
        setattr(assessment, entry.field, entry.value)
        applied.append(entry.field)
    return ApplyResult(applied, kept)


def interpretation_record(interpretation: Interpretation, result: ApplyResult, evidence_ids: list[int]) -> dict[str, str]:
    return {
        "model": interpretation.model,
        "evidence_ids": json.dumps(evidence_ids),
        "result_json": json.dumps({
            "fields": [entry.__dict__ for entry in interpretation.fields],
            "notes": interpretation.notes,
        }),
        "applied_fields": json.dumps(result.applied),
        "kept_fields": json.dumps(result.kept),
    }
