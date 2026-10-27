"""End-of-site-visit review and report for MORGAN.

review_visit() asks Claude to read everything recorded on the visit (checklist
responses and photo interpretations) and propose what still needs checking,
split into what must happen before leaving site and what can wait for the
office. build_report_html() turns the closed visit into a self-contained HTML
report with the photos embedded.

Advisory only: the engineer confirms the list and decides when the visit ends.
"""
import base64
import html
import os
from datetime import datetime, timezone

import field_capture as fc

TOOL_NAME = 'record_site_visit_review'
UNRESOLVED = ('Not reviewed', 'Unknown', 'Noncompliant')
PRIORITIES = ('high', 'medium', 'low')
WHERE = ('on_site', 'office')

REVIEW_SYSTEM_PROMPT = f"""You are assisting a licensed structural engineer who is about to end a seismic site visit of an existing building, using the ASCE 41 Tier 1 screening approach.

You will get the project setup, every applicable checklist item with the engineer's status, basis and follow-up notes, and the interpretation of each site photo.

Your job:
- Summarize the visit in 3 to 5 sentences: what was evaluated, key observations, and the main concerns.
- Propose a list of things still to check. Mark each one on_site if it can only be done while at the building (photos, measurements, access, observations) or office if it needs drawings, calculations, Tier 2 evaluation or research.
- Cover every item that is Not reviewed, Unknown or Noncompliant, and any follow-up suggested by photo interpretations, unless the notes already resolve it.
- Prioritize: high for anything that could change a Noncompliant or Unknown finding or that can't be revisited easily; low for nice-to-have.
- Say whether the visit looks ready to close, i.e. no high-priority on_site checks remain.

Rules:
- Only use the information given. Do not invent observations, dimensions or results.
- Be specific and terse, in the voice of a field note.
- Your output is advisory. The engineer decides what to check and when to leave.
- Always respond by calling the {TOOL_NAME} tool."""

REVIEW_SCHEMA = {
    'type': 'object',
    'properties': {
        'summary': {'type': 'string', 'description': '3 to 5 sentence summary of the visit.'},
        'readyToClose': {'type': 'boolean', 'description': 'True when no high-priority on_site checks remain.'},
        'closeRationale': {'type': 'string'},
        'checks': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'itemId': {'type': 'string', 'description': 'Checklist item id, or empty for a general check.'},
                    'title': {'type': 'string', 'description': 'What to check, as a short instruction.'},
                    'reason': {'type': 'string'},
                    'priority': {'type': 'string', 'enum': list(PRIORITIES)},
                    'where': {'type': 'string', 'enum': list(WHERE)},
                },
                'required': ['title', 'priority', 'where'],
            },
        },
    },
    'required': ['summary', 'readyToClose', 'checks'],
}


def baseline_checks(records: list[dict], photos: dict) -> list[dict]:
    """Checks that follow directly from the data, without a model: unresolved
    items and photo follow-ups. Used as a fallback and to backfill the model's list."""
    checks = []
    for r in records:
        if r.get('status') in UNRESOLVED:
            checks.append({'itemId': r['id'], 'title': f"Resolve {r['id']} ({r.get('topic', '')}): currently {r['status']}",
                           'reason': r.get('action') or 'Item has no final status.',
                           'priority': 'high' if r['status'] == 'Noncompliant' else 'medium',
                           'where': 'on_site' if r['status'] == 'Not reviewed' else 'office'})
    for item_id, p in photos.items():
        for f in ((p.get('interpretation') or {}).get('followUp') or []):
            checks.append({'itemId': item_id, 'title': f, 'reason': f"Suggested by interpretation of {p.get('name', 'photo')}.",
                           'priority': 'medium', 'where': 'on_site'})
    return checks


def build_review_prompt(metadata: dict, records: list[dict], photos: dict) -> str:
    lines = ['Project setup:']
    for k in ('project', 'address', 'edition', 'objective', 'seismicity', 'building_type', 'stories', 'area_ft2'):
        if metadata.get(k) not in (None, ''):
            lines.append(f'- {k}: {metadata[k]}')
    lines.append('\nChecklist items:')
    for r in records:
        lines.append(f"- [{r['id']}] {r.get('topic', '')} | status: {r.get('status', 'Not reviewed')}")
        if r.get('statement'): lines.append(f"  statement: {r['statement']}")
        if r.get('basis'): lines.append(f"  basis: {r['basis']}")
        if r.get('action'): lines.append(f"  follow-up noted: {r['action']}")
    lines.append('\nPhoto interpretations:' if photos else '\nNo photos were taken.')
    for item_id, p in photos.items():
        i = p.get('interpretation')
        where = f", location: {p['location']}" if p.get('location') else ''
        if not i:
            lines.append(f"- {p.get('name')} (item {item_id}{where}): not interpreted")
            continue
        lines.append(f"- {p.get('name')} (item {item_id}{where}): {i.get('summary', '')}")
        if i.get('suggestedStatus'): lines.append(f"  suggested status: {i['suggestedStatus']}")
        for d in i.get('possibleDeficiencies') or []:
            lines.append(f"  possible deficiency ({d.get('confidence', 'low')}): {d.get('description', '')}")
        for f in i.get('followUp') or []:
            lines.append(f'  follow-up: {f}')
    lines.append('\nReview the visit and propose what is still to check.')
    return '\n'.join(lines)


def normalize_review(raw: dict, model: str) -> dict:
    checks = []
    for c in raw.get('checks') if isinstance(raw.get('checks'), list) else []:
        if not isinstance(c, dict) or not isinstance(c.get('title'), str) or not c['title'].strip():
            continue
        checks.append({'itemId': c.get('itemId') if isinstance(c.get('itemId'), str) else '',
                       'title': c['title'],
                       'reason': c.get('reason') if isinstance(c.get('reason'), str) else '',
                       'priority': c.get('priority') if c.get('priority') in PRIORITIES else 'medium',
                       'where': c.get('where') if c.get('where') in WHERE else 'office'})
    return {
        'summary': raw.get('summary') if isinstance(raw.get('summary'), str) else '',
        'readyToClose': raw.get('readyToClose') is True,
        'closeRationale': raw.get('closeRationale') if isinstance(raw.get('closeRationale'), str) else '',
        'checks': checks,
        'model': model,
        'createdAt': datetime.now(timezone.utc).isoformat(),
    }


def add_missing_baseline(review: dict, records: list[dict]) -> dict:
    """Makes sure every unresolved checklist item appears in the list, even if the model skipped it."""
    covered = {c['itemId'] for c in review['checks']}
    extra = [c for c in baseline_checks(records, {}) if c['itemId'] not in covered]
    return {**review, 'checks': review['checks'] + extra}


def fallback_review(records: list[dict], photos: dict) -> dict:
    checks = baseline_checks(records, photos)
    return {'summary': '', 'readyToClose': not any(c['priority'] == 'high' and c['where'] == 'on_site' for c in checks),
            'closeRationale': '', 'checks': checks, 'model': None, 'createdAt': datetime.now(timezone.utc).isoformat()}


def review_visit(metadata: dict, records: list[dict], photos: dict, *, client=None, model: str | None = None,
                 api_key: str | None = None, max_tokens: int = 4096) -> dict:
    """Asks Claude to review the visit. Raises fc.InterpretError on failure; callers can fall back to fallback_review()."""
    import anthropic

    model = model or os.environ.get('ANTHROPIC_MODEL') or fc.DEFAULT_MODEL
    if client is None:
        api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise fc.InterpretError('ANTHROPIC_API_KEY is not set', 'server_misconfigured')
        client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=REVIEW_SYSTEM_PROMPT,
            tools=[{'name': TOOL_NAME, 'description': 'Record the end-of-visit review.', 'input_schema': REVIEW_SCHEMA}],
            tool_choice={'type': 'tool', 'name': TOOL_NAME},
            messages=[{'role': 'user', 'content': build_review_prompt(metadata, records, photos)}],
        )
    except anthropic.APIError as e:
        raise fc.InterpretError(f'Model API error: {e}', 'upstream_error') from e
    tool_use = next((b for b in msg.content if getattr(b, 'type', None) == 'tool_use' and b.name == TOOL_NAME), None)
    if tool_use is None or not isinstance(tool_use.input, dict):
        raise fc.InterpretError('Model did not return a structured review', 'invalid_model_output')
    return add_missing_baseline(normalize_review(tool_use.input, model), records)


# Report

REPORT_CSS = """
:root{--bg:#fff;--fg:#1d2329;--muted:#5d6670;--line:#d9dee3;--soft:#f4f6f8;--accent:#1f4e79;--bad:#a4262c;--warn:#8a5a00;--ok:#2e6b30}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15191d;--fg:#e6e9ec;--muted:#9aa3ab;--line:#2f363d;--soft:#1e2328;--accent:#8cb8e6;--bad:#f1878c;--warn:#e7b555;--ok:#8ccf8f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:920px;margin:0 auto;padding:32px 16px 64px}h1{margin:0 0 4px;font-size:26px}h2{margin:36px 0 12px;font-size:19px;color:var(--accent);border-bottom:1px solid var(--line);padding-bottom:6px}
h3{margin:0 0 6px;font-size:16px}.muted{color:var(--muted)}.note{background:var(--soft);border-left:3px solid var(--accent);padding:10px 14px;margin:16px 0}
table{width:100%;border-collapse:collapse;margin:8px 0}th,td{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:600;font-size:13px}
.meta td:first-child{color:var(--muted);width:200px}.item{border:1px solid var(--line);border-radius:6px;padding:14px;margin:12px 0;break-inside:avoid}
.tag{display:inline-block;font-size:12px;padding:1px 8px;border-radius:10px;background:var(--soft);border:1px solid var(--line)}
.Noncompliant,.high{color:var(--bad)}.Unknown,.Not.reviewed,.medium{color:var(--warn)}.Compliant{color:var(--ok)}
.photo{display:grid;grid-template-columns:minmax(0,320px) 1fr;gap:16px;margin:16px 0;break-inside:avoid}.photo img{width:100%;border-radius:4px;border:1px solid var(--line)}
@media (max-width:640px){.photo{grid-template-columns:1fr}.meta td:first-child{width:auto}}
@media print{main{padding:0}h2{break-after:avoid}}
"""


def _e(v) -> str:
    return html.escape('' if v is None else str(v))


def _lines(text: str) -> str:
    return '<br>'.join(_e(l) for l in str(text).splitlines())


def build_report_html(metadata: dict, records: list[dict], photos: dict, review: dict, done: dict, closed_at: str) -> str:
    """Self-contained HTML report. `done` maps check index -> True when ticked off before closing."""
    title = metadata.get('project') or 'Untitled project'
    out = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>Site visit report – {_e(title)}</title><style>{REPORT_CSS}</style></head><body><main>',
           f'<h1>Site visit report: {_e(title)}</h1>',
           f'<div class="muted">ASCE 41 Tier 1 screening · closed {_e(closed_at)} · project {_e(metadata.get("project_id"))}</div>',
           '<div class="note">Engineering decision-support only. The registered design professional remains responsible for applicability, '
           'interpretation, calculations and conclusions. AI-generated content is marked and is advisory.</div>']

    out.append('<h2>Project</h2><table class="meta">')
    for label, k in (('Location', 'address'), ('Evaluator', 'evaluator'), ('Standard', 'edition'), ('Performance objective', 'objective'),
                     ('Seismicity', 'seismicity'), ('Building type', 'building_type'), ('Stories', 'stories'), ('Floor area (ft²)', 'area_ft2')):
        out.append(f'<tr><td>{label}</td><td>{_e(metadata.get(k))}</td></tr>')
    out.append('</table>')

    if review.get('summary'):
        out.append(f'<h2>Visit summary</h2><p>{_lines(review["summary"])}</p>'
                   f'<p class="muted">AI-drafted by {_e(review.get("model"))}. Review before relying on it.</p>')

    counts = {}
    for r in records: counts[r.get('status', 'Not reviewed')] = counts.get(r.get('status', 'Not reviewed'), 0) + 1
    out.append('<h2>Checklist status</h2><table><tr>' + ''.join(f'<th>{s}</th>' for s in ('Compliant', 'Noncompliant', 'Not applicable', 'Unknown', 'Not reviewed'))
               + '</tr><tr>' + ''.join(f'<td>{counts.get(s, 0)}</td>' for s in ('Compliant', 'Noncompliant', 'Not applicable', 'Unknown', 'Not reviewed')) + '</tr></table>')

    checks = review.get('checks') or []
    out.append('<h2>Things to check</h2>')
    if not checks:
        out.append('<p class="muted">None proposed.</p>')
    else:
        open_n = sum(1 for i in range(len(checks)) if not done.get(i))
        out.append(f'<p>{open_n} open, {len(checks) - open_n} done before leaving site.</p><table><tr><th>Status</th><th>Priority</th><th>Where</th><th>Item</th><th>Check</th></tr>')
        for i, c in enumerate(checks):
            out.append(f'<tr><td>{"Done" if done.get(i) else "Open"}</td><td class="{_e(c["priority"])}">{_e(c["priority"])}</td>'
                       f'<td>{"On site" if c["where"] == "on_site" else "Office"}</td><td>{_e(c.get("itemId"))}</td>'
                       f'<td>{_e(c["title"])}' + (f'<div class="muted">{_e(c["reason"])}</div>' if c.get('reason') else '') + '</td></tr>')
        out.append('</table>')

    out.append('<h2>Checklist findings</h2>')
    for r in records:
        status = r.get('status', 'Not reviewed')
        out.append(f'<div class="item"><h3>{_e(r["id"])} · {_e(r.get("topic"))} <span class="tag {_e(status)}">{_e(status)}</span></h3>')
        if r.get('statement'): out.append(f'<p>{_e(r["statement"])}</p>')
        rows = [('Basis', r.get('basis')), ('Follow-up', r.get('action')), ('Evidence', r.get('evidence')), ('Tier 2 ref', r.get('tier2_ref')), ('Photo', r.get('photo'))]
        out.append('<table class="meta">' + ''.join(f'<tr><td>{k}</td><td>{_lines(v)}</td></tr>' for k, v in rows if v) + '</table></div>')

    out.append('<h2>Photo log</h2>')
    if not photos: out.append('<p class="muted">No photos taken.</p>')
    for item_id, p in photos.items():
        img = base64.b64encode(p['jpeg']).decode() if p.get('jpeg') else ''
        i = p.get('interpretation') or {}
        out.append(f'<div class="photo"><div>' + (f'<img alt="{_e(p.get("name"))}" src="data:image/jpeg;base64,{img}">' if img else '') + '</div><div>'
                   f'<h3>{_e(p.get("name"))}</h3><div class="muted">Item {_e(item_id)} · {_e(p.get("takenAt"))}'
                   + (f' · {_e(p["location"])}' if p.get('location') else '') + '</div>')
        if p.get('note'): out.append(f'<p>Note: {_e(p["note"])}</p>')
        if i:
            out.append(f'<p>{_e(i.get("summary"))}</p>')
            if i.get('suggestedStatus'):
                out.append(f'<p>Suggested status (advisory): <b>{_e(i["suggestedStatus"])}</b>' + (f' – {_e(i["statusRationale"])}' if i.get('statusRationale') else '') + '</p>')
            if i.get('observations'):
                out.append('<ul>' + ''.join(f'<li>{_e(o.get("severity"))}: {_e(o.get("description"))}</li>' for o in i['observations']) + '</ul>')
            if i.get('possibleDeficiencies'):
                out.append('<p class="muted">Possible deficiencies</p><ul>' + ''.join(f'<li>{_e(d.get("description"))} ({_e(d.get("confidence"))} confidence)</li>' for d in i['possibleDeficiencies']) + '</ul>')
            out.append(f'<p class="muted">Interpreted by {_e(i.get("model"))}.</p>')
        else:
            out.append('<p class="muted">Not interpreted.</p>')
        out.append('</div></div>')

    out.append('</main></body></html>')
    return ''.join(out)
