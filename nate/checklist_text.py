"""Loads Tier 1 checklist items from the team's checklist text file (src/ASCE 41.txt).

The file is the team's own data. This module only parses its layout; no
checklist wording lives in code. Expected layout, one form after another:

    <form><CP|IO> <title>               e.g. "17.1.2CP Basic Configuration Checklist"
    Table ... / column header lines     ignored
    <Low|Moderate|High> Seismicity ...  sets applicable seismicity (cumulative)
    <section heading>                   any other line between items
    C NC N/A U TOPIC: statement...      starts an item; continues over following lines
    <tier 2 ref> [<commentary ref>]     e.g. "5.4.1.1 A.2.1.1"; ends the item
"""
import re
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'src' / 'ASCE 41.txt'

FORM_RE = re.compile(r'^(17\.\d+(?:\.\d+)?)(CP|IO)\s+(.+)$')
SEISMICITY_RE = re.compile(r'^(Low|Moderate|High) Seismicity\b')
ITEM_RE = re.compile(r'^C NC N/A U\s+(.*)$')
REFS_RE = re.compile(r'^(\d+(?:\.\d+)+)(?:\s+(A\.[\d.]*))?\s*$')
TOPIC_RE = re.compile(r'^([^:a-z]+):\s*(.*)$', re.S)
HEADER_LINES = {'Status Evaluation Statement', 'Tier 2', 'Reference', 'Commentary', 'Reference Comments'}
BUILDING_TYPE_RE = re.compile(r'\b(W1A?|W2|S[1-5]A?|CFS[12]|C[1-3]A?|PC[12]A?|RM[12]|URMA?)\b', re.I)
# Items listed under a seismicity heading also apply to the higher levels.
CUMULATIVE = {'Low': 'Low,Moderate,High', 'Moderate': 'Moderate,High', 'High': 'High'}


def _join(parts):
    text = ''
    for p in parts:
        text = text[:-1] + p if text.endswith('-') and not text.endswith(' -') else (f'{text} {p}' if text else p)
    return text


def parse_checklist_text(text: str) -> list[dict]:
    """Returns rows with MORGAN's checklist columns (see COLS in asce41_tier1_app.py)."""
    rows = []
    form = perf = title = section = ''
    seismicity = None
    buf = None  # lines of the item being read

    def finish(tier2='', commentary=''):
        nonlocal buf
        if buf is None:
            return
        body = _join(buf)
        m = TOPIC_RE.match(body)
        topic, statement = (m.group(1).strip().title(), m.group(2).strip()) if m else ('', body)
        types = sorted({t.upper() for t in BUILDING_TYPE_RE.findall(title)}) or ['ALL']
        rows.append({
            'id': f'{form}{perf}-{sum(1 for r in rows if r["checklist"] == title) + 1:02d}',
            'checklist': title,
            'building_types': ','.join(types),
            'performance': perf,
            'seismicity': 'Very Low' if 'very low' in title.lower() else CUMULATIVE.get(seismicity, 'Low,Moderate,High'),
            'section': section,
            'topic': topic,
            'statement': statement,
            'tier2_ref': tier2,
            'commentary_ref': commentary,
        })
        buf = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            finish()
            continue
        if m := FORM_RE.match(line):
            finish()
            form, perf, title = m.group(1), m.group(2), m.group(3).strip()
            section, seismicity = '', None
        elif m := ITEM_RE.match(line):
            finish()
            buf = [m.group(1)]
        elif buf is not None and (m := REFS_RE.match(line)):
            finish(m.group(1), m.group(2) or '')
        elif line in HEADER_LINES or line.startswith('Table '):
            finish()
        elif m := SEISMICITY_RE.match(line):
            finish()
            seismicity = m.group(1)
        elif buf is not None:
            buf.append(line)
        elif form:
            section = line
    finish()
    return rows


def load_checklist(path: Path | str = DEFAULT_PATH) -> list[dict]:
    """Rows from the text file, or [] if it doesn't exist."""
    path = Path(path)
    return parse_checklist_text(path.read_text(encoding='utf-8')) if path.exists() else []
