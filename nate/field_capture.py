"""Site-photo interpretation for MORGAN (field capture, workstream 5).

Pure Python, so the Streamlit app can call Claude directly without Node.js.

Advisory only: the suggested status is shown to the engineer, who decides.
"""
import io
import os
from datetime import datetime, timezone

from PIL import Image, ImageOps

DEFAULT_MODEL = 'claude-sonnet-5-5'
TOOL_NAME = 'record_photo_interpretation'
MAX_EDGE_PX = 1568
JPEG_QUALITY = 85
# API limit is 5 MB per image (decoded).
MAX_IMAGE_BYTES = 5 * 1024 * 1024

STATUSES = ('C', 'NC', 'N/A', 'U')
PERFORMANCE_NAMES = {'CP': 'Collapse Prevention', 'LS': 'Life Safety', 'IO': 'Immediate Occupancy'}

SYSTEM_PROMPT = f"""You are assisting a licensed structural engineer during a seismic site visit of an existing building, using the ASCE 41 Tier 1 screening approach.

You will be shown one photo taken on site, plus whatever context the engineer has given (building type, performance level, the checklist item being evaluated, notes).

Your job:
- Describe what is actually visible. Identify structural and nonstructural components, materials and condition.
- Note observations relevant to seismic performance: damage, cracking, corrosion, deterioration, missing or inadequate connections, irregularities, pounding risk, unbraced elements, and similar.
- If a checklist item is given, say whether the photo supports Compliant (C), Noncompliant (NC), Not Applicable (N/A) or Unknown (U), and why. Use U whenever the photo alone cannot settle it. Most items need measurements, drawings or calculations, so U is often correct.
- Suggest concrete follow-up: what else to photograph, measure, or check in drawings.

Rules:
- Only report what the image shows. Do not invent dimensions, details or hidden conditions. Say when something is obscured or ambiguous.
- Be specific and terse, in the voice of a field note.
- Your output is advisory. The engineer makes every determination.
- Always respond by calling the {TOOL_NAME} tool."""

OUTPUT_SCHEMA = {
    'type': 'object',
    'properties': {
        'summary': {'type': 'string', 'description': 'One or two sentences describing what the photo shows.'},
        'components': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'name': {'type': 'string'}, 'material': {'type': 'string'}, 'condition': {'type': 'string'}},
                'required': ['name'],
            },
        },
        'observations': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'description': {'type': 'string'},
                    'severity': {'type': 'string', 'enum': ['info', 'minor', 'moderate', 'severe']},
                },
                'required': ['description', 'severity'],
            },
        },
        'possibleDeficiencies': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'description': {'type': 'string'},
                    'relatedChecklistItemId': {'type': 'string'},
                    'confidence': {'type': 'string', 'enum': ['low', 'medium', 'high']},
                },
                'required': ['description', 'confidence'],
            },
        },
        'suggestedStatus': {
            'type': ['string', 'null'],
            'enum': ['C', 'NC', 'N/A', 'U', None],
            'description': 'Null if no checklist item was given.',
        },
        'statusRationale': {'type': 'string'},
        'followUp': {'type': 'array', 'items': {'type': 'string'}},
        'imageQuality': {
            'type': 'object',
            'properties': {'usable': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['usable', 'issues'],
        },
    },
    'required': ['summary', 'components', 'observations', 'possibleDeficiencies', 'suggestedStatus', 'followUp', 'imageQuality'],
}


class InterpretError(Exception):
    """Raised when a photo can't be interpreted. `code` is a short machine-readable error code."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def prepare_photo(data: bytes) -> bytes:
    """Applies EXIF orientation, resizes to MAX_EDGE_PX on the long edge, and
    re-encodes as JPEG without metadata."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except Exception as e:
        raise InterpretError(f'Could not read image: {e}', 'bad_request') from e
    img = img.convert('RGB')
    img.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=JPEG_QUALITY)
    return out.getvalue()


def build_user_prompt(context: dict | None = None) -> str:
    """Turns the app's context into the text that accompanies the image.

    context keys (all optional): building_type, performance_level, seismicity,
    location_in_building, user_note, checklist_item = {id, title, text}.
    """
    c = context or {}
    lines = []
    if c.get('building_type'): lines.append(f"Building type: {c['building_type']}")
    if c.get('performance_level'):
        p = c['performance_level']
        lines.append(f"Performance level: {p} ({PERFORMANCE_NAMES.get(p, p)})")
    if c.get('seismicity'): lines.append(f"Level of seismicity: {c['seismicity']}")
    if c.get('location_in_building'): lines.append(f"Location in building: {c['location_in_building']}")
    item = c.get('checklist_item')
    if item:
        lines.append(f"Checklist item being evaluated: [{item['id']}] {item['title']}")
        if item.get('text'): lines.append(f"Item statement: {item['text']}")
    else:
        lines.append('No specific checklist item: give a general seismic-relevant interpretation and set suggestedStatus to null.')
    if c.get('user_note'): lines.append(f"Engineer's note: {c['user_note']}")
    return 'Site-visit photo context:\n' + '\n'.join(f'- {l}' for l in lines) + '\n\nInterpret the photo.'


def normalize_interpretation(raw: dict, model: str) -> dict:
    """Fills defaults so callers can rely on every field being present."""
    def arr(v): return v if isinstance(v, list) else []
    quality = raw.get('imageQuality') if isinstance(raw.get('imageQuality'), dict) else {}
    status = raw.get('suggestedStatus')
    rationale = raw.get('statusRationale')
    return {
        'summary': raw.get('summary') if isinstance(raw.get('summary'), str) else '',
        'components': arr(raw.get('components')),
        'observations': arr(raw.get('observations')),
        'possibleDeficiencies': arr(raw.get('possibleDeficiencies')),
        'suggestedStatus': status if status in STATUSES else None,
        'statusRationale': rationale if isinstance(rationale, str) else None,
        'followUp': [s for s in arr(raw.get('followUp')) if isinstance(s, str)],
        'imageQuality': {'usable': quality.get('usable') is not False, 'issues': arr(quality.get('issues'))},
        'model': model,
        'createdAt': datetime.now(timezone.utc).isoformat(),
    }


def interpret_photo(jpeg: bytes, context: dict | None = None, *, client=None, model: str | None = None,
                    api_key: str | None = None, max_tokens: int = 2048) -> dict:
    """Sends a prepared JPEG to Claude and returns a normalized interpretation.

    Pass `client` (an anthropic.Anthropic) to reuse one or to inject a fake in tests.
    """
    import base64
    import anthropic

    if len(jpeg) > MAX_IMAGE_BYTES:
        raise InterpretError('Image exceeds 5 MB. Run it through prepare_photo() first.', 'image_too_large')
    model = model or os.environ.get('ANTHROPIC_MODEL') or DEFAULT_MODEL
    if client is None:
        api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise InterpretError('ANTHROPIC_API_KEY is not set', 'server_misconfigured')
        client = anthropic.Anthropic(api_key=api_key)

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            tools=[{'name': TOOL_NAME, 'description': 'Record the structured interpretation of the site-visit photo.',
                    'input_schema': OUTPUT_SCHEMA}],
            tool_choice={'type': 'tool', 'name': TOOL_NAME},
            messages=[{'role': 'user', 'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                             'data': base64.b64encode(jpeg).decode()}},
                {'type': 'text', 'text': build_user_prompt(context)},
            ]}],
        )
    except anthropic.APIError as e:
        raise InterpretError(f'Model API error: {e}', 'upstream_error') from e

    tool_use = next((b for b in msg.content if getattr(b, 'type', None) == 'tool_use' and b.name == TOOL_NAME), None)
    if tool_use is None or not isinstance(tool_use.input, dict):
        raise InterpretError('Model did not return a structured interpretation', 'invalid_model_output')
    return normalize_interpretation(tool_use.input, model)
