from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from study_core import ROOT, connect_db, emit_json
from tool_logging import run_tool_main


DEFAULT_SOURCE = ROOT / "data" / "intake" / "moji_vocab_2026-04-19.json"


def parse_anchor_day(raw: str | None) -> datetime:
    if raw:
        return datetime.strptime(raw, "%Y-%m-%d")
    return datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill first memorized dates from ordered vocabulary input.")
    parser.add_argument("--file", default=str(DEFAULT_SOURCE))
    parser.add_argument("--anchor-date", default=None, help="Last batch date in YYYY-MM-DD.")
    parser.add_argument("--batch-size", type=int, default=35)
    parser.add_argument("--day-step", type=int, default=2)
    parser.add_argument("--source-scope", default="user")
    args = parser.parse_args()

    source = Path(args.file)
    entries = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise SystemExit("Input must be a JSON array of vocabulary entries.")

    anchor_day = parse_anchor_day(args.anchor_date)
    batch_count = max(1, (len(entries) + args.batch_size - 1) // args.batch_size)
    start_day = anchor_day - timedelta(days=args.day_step * (batch_count - 1))

    conn = connect_db()
    updated = 0
    unmatched: list[dict[str, str]] = []
    for index, entry in enumerate(entries):
        term = (entry.get("term") or "").strip()
        reading = (entry.get("reading") or "").strip()
        if not term:
            continue
        batch_index = index // args.batch_size
        learned_at = (start_day + timedelta(days=batch_index * args.day_step)).replace(
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
        )
        stamp = learned_at.strftime("%Y-%m-%d %H:%M:%S")
        row = None
        if reading:
            row = conn.execute(
                """
                SELECT id FROM vocab_items
                WHERE term = ? AND reading = ? AND source_scope = ?
                LIMIT 1
                """,
                (term, reading, args.source_scope),
            ).fetchone()
        if not row:
            row = conn.execute(
                """
                SELECT id FROM vocab_items
                WHERE term = ? AND source_scope = ?
                ORDER BY CASE WHEN reading = ? THEN 0 ELSE 1 END, id ASC
                LIMIT 1
                """,
                (term, args.source_scope, reading),
            ).fetchone()
        if not row:
            unmatched.append({"term": term, "reading": reading})
            continue
        conn.execute(
            """
            UPDATE vocab_items
            SET first_memorized_at = ?,
                first_seen_at = COALESCE(NULLIF(first_seen_at, ''), ?),
                updated_at = ?
            WHERE id = ?
            """,
            (stamp, stamp, stamp, row["id"]),
        )
        updated += 1
    conn.commit()

    emit_json(
        {
            "updated": updated,
            "unmatched": unmatched,
            "batch_size": args.batch_size,
            "day_step": args.day_step,
            "start_date": start_day.strftime("%Y-%m-%d"),
            "end_date": anchor_day.strftime("%Y-%m-%d"),
        }
    )


if __name__ == "__main__":
    run_tool_main("backfill_learning_history", main)
