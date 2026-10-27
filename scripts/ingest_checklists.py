#!/usr/bin/env python3
"""Normalize the supplied ASCE checklist text into the app catalog."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.catalog import build_catalog  # noqa: E402


def main() -> None:
    source_root = ROOT / "src" / "ASCE 41-23 Tier 1 checklist for seismic evaluation and retrofit of existing buildings"
    output = ROOT / "app" / "data" / "checklists.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_catalog(source_root), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
