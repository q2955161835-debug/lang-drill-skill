from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

from study_core import (
    connect_db,
    emit_json,
    schedule_days,
    score_to_proficiency,
    status_to_proficiency,
    status_to_score,
    ts,
    update_item_progress,
)
from tool_logging import run_tool_main


def resolve_base_metrics(row: dict, first_field: str) -> tuple[int | None, int | None, str | None]:
    external_score = row["external_score"]
    status_label = (row["status_label"] or "").strip()
    base_score = external_score if external_score is not None else status_to_score(status_label)
    base_prof = score_to_proficiency(base_score)
    if base_prof is None:
        base_prof = status_to_proficiency(status_label)
    base_due = None
    first_value = (row[first_field] or "").strip()
    if first_value and base_prof is not None:
        start_dt = datetime.strptime(first_value, "%Y-%m-%d %H:%M:%S")
        base_due = ts(start_dt + timedelta(days=schedule_days(base_prof, True)))
    return base_prof, base_score, base_due


def reset_table(conn, table: str, first_field: str) -> int:
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    reset_count = 0
    for row in rows:
        base_prof, base_score, base_due = resolve_base_metrics(row, first_field)
        conn.execute(
            f"""
            UPDATE {table}
            SET proficiency = ?,
                mastery_score = ?,
                last_review_at = NULL,
                times_seen = 0,
                correct_times = 0,
                incorrect_times = 0,
                correct_rate = NULL,
                next_due_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (base_prof, base_score, base_due, ts(), row["id"]),
        )
        reset_count += 1
    return reset_count


def replay_actual_attempts(conn) -> int:
    rows = conn.execute(
        """
        SELECT a.is_correct, q.knowledge_tags, q.is_new_knowledge
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE COALESCE(a.record_kind, COALESCE(q.record_kind, 'actual')) = 'actual'
        ORDER BY a.answered_at ASC, a.id ASC
        """
    ).fetchall()
    for row in rows:
        for tag in json.loads(row["knowledge_tags"]):
            update_item_progress(conn, tag, bool(row["is_correct"]), bool(row["is_new_knowledge"]))
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild derived study progress from non-test attempts.")
    parser.parse_args()

    conn = connect_db()
    reset_vocab = reset_table(conn, "vocab_items", "first_memorized_at")
    reset_grammar = reset_table(conn, "grammar_items", "first_studied_at")
    replayed_attempts = replay_actual_attempts(conn)
    conn.commit()

    emit_json(
        {
            "reset_vocab_items": reset_vocab,
            "reset_grammar_items": reset_grammar,
            "replayed_actual_attempts": replayed_attempts,
        }
    )


if __name__ == "__main__":
    run_tool_main("rebuild_progress_state", main)
