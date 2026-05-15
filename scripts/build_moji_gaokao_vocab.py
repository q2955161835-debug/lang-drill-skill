from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path

import fitz

from study_core import ROOT, connect_db, import_vocab_entries
from tool_logging import run_tool_main


MATERIAL_DIR = ROOT / "data" / "kb" / "material-inbox" / "moji"
SOURCE_PDFS = [
    MATERIAL_DIR / "MOJi辞書 - 高考大纲词汇 1~1000.pdf",
    MATERIAL_DIR / "MOJi辞書 - 高考大纲词汇 1001~2000.pdf",
    MATERIAL_DIR / "MOJi辞書 - 高考大纲词汇 2001~2289.pdf",
]
TARGET_JSON = ROOT / "data" / "kb" / "gaokao-japanese" / "moji_vocab_2289.json"
TARGET_CSV = ROOT / "data" / "kb" / "gaokao-japanese" / "moji_vocab_2289.csv"
ENTRY_START = re.compile(r"^\d+$")
FOOTER_PREFIXES = ("词单：高考大纲词汇",)


def clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    skip_next_digit = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in {"序号", "发音", "单词", "释义"}:
            continue
        if skip_next_digit and line.isdigit():
            skip_next_digit = False
            continue
        if any(line.startswith(prefix) for prefix in FOOTER_PREFIXES):
            skip_next_digit = True
            continue
        lines.append(line)
    return lines


def parse_pdf(path: Path) -> list[dict]:
    lines: list[str] = []
    doc = fitz.open(path)
    for page in doc:
        lines.extend(clean_lines(page.get_text()))

    entries: list[dict] = []
    i = 0
    while i < len(lines):
        if not ENTRY_START.match(lines[i]):
            i += 1
            continue
        serial = int(lines[i])
        if i + 3 >= len(lines):
            break
        reading = lines[i + 1]
        term = lines[i + 2]
        i += 3
        meaning_parts: list[str] = []
        while i < len(lines) and not ENTRY_START.match(lines[i]):
            meaning_parts.append(lines[i])
            i += 1
        meaning = " ".join(meaning_parts).strip()
        entries.append(
            {
                "serial": serial,
                "term": term,
                "reading": reading,
                "meaning": meaning,
                "pos": meaning.split("]", 1)[0].lstrip("[") if meaning.startswith("[") and "]" in meaning else "",
                "source_scope": "gaokao",
                "source_type": "moji_pdf",
                "notes": f"来源：{path.name}",
            }
        )
    return entries


def write_outputs(entries: list[dict]) -> None:
    TARGET_JSON.parent.mkdir(parents=True, exist_ok=True)
    TARGET_JSON.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with TARGET_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["serial", "term", "reading", "meaning", "pos", "source_scope", "source_type", "notes"])
        writer.writeheader()
        writer.writerows(entries)


def sync_source_pdfs() -> list[str]:
    MATERIAL_DIR.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for path in SOURCE_PDFS:
        if not path.exists():
            continue
        target = MATERIAL_DIR / path.name
        shutil.copy2(path, target)
        copied.append(str(target))
    return copied


def main() -> None:
    all_entries: list[dict] = []
    for path in SOURCE_PDFS:
        if not path.exists():
            raise FileNotFoundError(path)
        all_entries.extend(parse_pdf(path))
    all_entries.sort(key=lambda item: item["serial"])
    write_outputs(all_entries)
    copied = sync_source_pdfs()
    conn = connect_db()
    result = import_vocab_entries(
        conn,
        all_entries,
        source_scope="gaokao",
        source_type="moji_pdf",
        memorize=False,
    )
    print(
        json.dumps(
            {
                "entries": len(all_entries),
                "inserted": result.inserted,
                "updated": result.updated,
                "json": str(TARGET_JSON),
                "csv": str(TARGET_CSV),
                "copied_pdfs": copied,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run_tool_main("build_moji_gaokao_vocab", main)
