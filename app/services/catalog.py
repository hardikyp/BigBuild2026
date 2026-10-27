from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


LEVELS = ["very_low", "low", "moderate", "high"]
LEVEL_LABELS = {
    "very_low": "Very Low",
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
}
HEADER_LINES = {
    "Status Evaluation Statement",
    "Status Evaluation Statementa,b",
    "Tier 2",
    "Reference",
    "Commentary",
    "Reference Comments",
}
STATUS_RE = re.compile(r"^C NC N/A U\s*(.*)$")
REFERENCE_RE = re.compile(r"^(?:\d[\w.-]*|A\.?[\w.-]+)(?:\s+(?:\d[\w.-]*|A\.?[\w.-]+))+$")
SINGLE_REFERENCE_RE = re.compile(r"^(?:\d[\w.-]*|A\.?[\w.-]+)$")
REFERENCE_TOKEN_RE = re.compile(r"(?:\d[\w.-]*|A\.?[\w.-]+)")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def form_metadata(txt_path: Path, source_root: Path) -> dict[str, Any]:
    name = txt_path.stem
    if name == "17.19_Nonstructural":
        return {
            "form_id": "17.19-nonstructural",
            "performance_level": "CP",
            "building_type": "NONSTRUCTURAL",
            "building_type_label": "Nonstructural",
            "supported_levels": LEVELS,
            "source_pdf": str((source_root / "Nonstructural Form" / "17.19_Nonstructural.pdf").relative_to(source_root.parent.parent)),
        }
    if name == "17.1.1CPVery Low_Basic":
        return {
            "form_id": "17.1.1-cp-basic-very-low",
            "performance_level": "CP",
            "building_type": "BASIC",
            "building_type_label": "Basic Configuration",
            "supported_levels": ["very_low"],
            "source_pdf": str((source_root / "CP Forms" / "17.1.1CPVery Low_Basic.pdf").relative_to(source_root.parent.parent)),
        }
    performance = "IO" if "IO" in name else "CP"
    building_match = re.search(r"Type([A-Za-z0-9]+)", name)
    building_type = building_match.group(1).upper() if building_match else "BASIC"
    building_label = "Basic Configuration" if building_type == "BASIC" else building_type
    folder = "IO Forms" if performance == "IO" else "CP Forms"
    pdf_name = f"{name}.pdf"
    return {
        "form_id": slug(name),
        "performance_level": performance,
        "building_type": building_type,
        "building_type_label": building_label,
        "supported_levels": LEVELS if performance == "IO" and building_type == "BASIC" else LEVELS[1:],
        "source_pdf": str((source_root / folder / pdf_name).relative_to(source_root.parent.parent)),
    }


def level_scope(line: str) -> list[str] | None:
    if "Seismicity" not in line:
        return None
    if not re.match(r"^(?:Very Low|Low|Moderate|High)", line.strip()):
        return None
    lower = line.lower()
    if "very low" in lower:
        start = 0
    elif "moderate" in lower and "high" in lower and "low" not in lower:
        start = 2
    elif "low" in lower:
        start = 1
    elif "moderate" in lower:
        start = 2
    elif "high" in lower:
        start = 3
    else:
        return None
    return LEVELS[start:]


def is_header(line: str) -> bool:
    return line.strip() in HEADER_LINES or line.strip().startswith("Status Evaluation Statement")


def is_section_heading(line: str) -> bool:
    value = line.strip()
    if not value or is_header(value) or value.startswith("Table "):
        return False
    if level_scope(value):
        return False
    if ":" in value or value.endswith(".") or len(value) > 80:
        return False
    if REFERENCE_RE.match(value) or SINGLE_REFERENCE_RE.match(value) or not value[0].isupper():
        return False
    # Text extraction wraps statements at arbitrary points. Real section
    # labels are title-cased, while wrapped prose such as "Quick Check
    # procedure of Section" is not.
    return value == value.title() and not value.startswith(("C ", "N/A ", "U "))


def split_references(lines: list[str]) -> tuple[str, str, str]:
    statement: list[str] = []
    refs: list[str] = []
    in_refs = False
    for line in lines:
        value = " ".join(line.split())
        if not value:
            continue
        inline = re.search(r"\s+(\d[\w.-]*)\s+(A\.?[\w.-]+)$", value)
        if inline:
            statement.append(value[:inline.start()].rstrip())
            refs.extend([inline.group(1), inline.group(2)])
            in_refs = True
            continue
        tokens = REFERENCE_TOKEN_RE.findall(value)
        looks_ref = bool(tokens) and bool(REFERENCE_RE.match(value) or SINGLE_REFERENCE_RE.match(value))
        if looks_ref:
            in_refs = True
            refs.extend(tokens)
        elif not in_refs:
            statement.append(value)
    numeric = [token for token in refs if not token.upper().startswith("A")]
    commentary = [token for token in refs if token.upper().startswith("A")]
    return " ".join(statement).strip(), " ".join(numeric).strip(), " ".join(commentary).strip()


def parse_form(txt_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    raw_lines = txt_path.read_text(encoding="utf-8", errors="replace").replace("\r", "").splitlines()
    lines = [line.strip() for line in raw_lines]
    title = lines[0] if lines else txt_path.stem
    sections: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    current_level_scope = metadata["supported_levels"]
    active: list[str] | None = None
    active_section: dict[str, Any] | None = None
    active_levels: list[str] = current_level_scope

    def finish_item() -> None:
        nonlocal active
        if not active:
            return
        statement, tier2, commentary = split_references(active)
        if statement:
            item_number = len(items) + 1
            items.append(
                {
                    "item_id": f"{metadata['form_id']}-item-{item_number:03d}",
                    "order": item_number,
                    "section_id": active_section["section_id"] if active_section else f"{metadata['form_id']}-general",
                    "seismicity_levels": active_levels,
                    "statement": statement,
                    "tier2_reference": tier2,
                    "commentary_reference": commentary,
                }
            )
        active = None

    for line in lines:
        if not line:
            continue
        match = STATUS_RE.match(line)
        if match:
            finish_item()
            active = [match.group(1)]
            active_section = current_section
            active_levels = list(current_level_scope)
            continue
        if active is not None:
            if is_header(line) or is_section_heading(line) or level_scope(line):
                # A section boundary follows the previous item. This is safe
                # because wrapped evaluation statements contain punctuation.
                finish_item()
            else:
                active.append(line)
                continue
        if is_header(line) or line.startswith("Table ") or line == title:
            continue
        parsed_levels = level_scope(line)
        if parsed_levels:
            current_level_scope = [level for level in parsed_levels if level in metadata["supported_levels"]]
            if not current_level_scope:
                current_level_scope = metadata["supported_levels"]
            continue
        if is_section_heading(line):
            section_number = len(sections) + 1
            current_section = {
                "section_id": f"{metadata['form_id']}-section-{section_number:03d}",
                "order": section_number,
                "title": " ".join(line.split()),
                "seismicity_levels": list(current_level_scope),
            }
            sections.append(current_section)

    finish_item()
    return {
        **metadata,
        "title": title,
        "source_text": str(txt_path),
        "source_hash": source_hash(txt_path),
        "sections": sections,
        "items": items,
    }


def build_catalog(source_root: Path) -> dict[str, Any]:
    txt_root = source_root / "Txt_files"
    forms = []
    for path in sorted(txt_root.glob("*.txt")):
        metadata = form_metadata(path, source_root)
        form = parse_form(path, metadata)
        form["source_text"] = str(path.relative_to(source_root.parent.parent))
        forms.append(form)
    return {"catalog_version": "2026.10.27", "forms": forms}


def load_catalog(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def applicable_forms(catalog: dict[str, Any], performance_level: str, building_type: str, seismicity: str, include_basic: bool, include_structural: bool, include_nonstructural: bool) -> list[dict[str, Any]]:
    selected = []
    for form in catalog["forms"]:
        if form["building_type"] == "NONSTRUCTURAL":
            if include_nonstructural and seismicity in form["supported_levels"]:
                selected.append(form)
            continue
        if form["performance_level"] != performance_level:
            continue
        if form["building_type"] == "BASIC":
            if include_basic and seismicity in form["supported_levels"]:
                selected.append(form)
        elif include_structural and form["building_type"] == building_type and seismicity in form["supported_levels"]:
            selected.append(form)
    return selected
