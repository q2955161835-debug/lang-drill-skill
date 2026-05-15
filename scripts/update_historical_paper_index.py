from __future__ import annotations

import json
from pathlib import Path

from study_core import connect_db, ts
from tool_logging import run_tool_main


ROOT = Path(__file__).resolve().parent.parent


def load_sources() -> list[dict]:
    files = [
        ROOT / "data" / "kb" / "cjt4" / "historical_external_sources.json",
        ROOT / "data" / "kb" / "gaokao-japanese" / "historical_external_sources.json",
    ]
    items: list[dict] = []
    for path in files:
        if path.exists():
            items.extend(json.loads(path.read_text(encoding="utf-8")))
    return items


def upsert(items: list[dict]) -> None:
    conn = connect_db()
    stamp = ts()
    for item in items:
        row = conn.execute(
            "SELECT id FROM paper_index WHERE exam_name = ? AND year = ? AND level = ? AND section = ?",
            (item["exam_name"], item["year"], item["level"], item["section"]),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE paper_index
                SET source_status = ?, source_path = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (item["source_status"], item["source_path"], item["notes"], stamp, row["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO paper_index (exam_name, year, level, section, source_status, source_path, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["exam_name"],
                    item["year"],
                    item["level"],
                    item["section"],
                    item["source_status"],
                    item["source_path"],
                    item["notes"],
                    stamp,
                    stamp,
                ),
            )
    conn.commit()


def main() -> None:
    items = load_sources()
    upsert(items)
    print(json.dumps({"historical_sources_indexed": len(items)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_tool_main("update_historical_paper_index", main)
