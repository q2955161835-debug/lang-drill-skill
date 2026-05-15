from __future__ import annotations

import argparse
import re
from pathlib import Path

from study_core import DIARY_DIR, WRONG_NOTEBOOK, connect_db, emit_json
from tool_logging import run_tool_main


def normalize_record_labels(text: str, session_ids: list[str]) -> str:
    updated = text
    for session_id in session_ids:
        updated = re.sub(
            rf"(## 会话 {re.escape(session_id)}\n\n)(- 记录类型：[^\n]+\n)?",
            rf"\1- 记录类型：测试\n",
            updated,
        )
        updated = re.sub(
            rf"(- 会话：{re.escape(session_id)}\n)(- 记录类型：[^\n]+\n)?",
            rf"\1- 记录类型：测试\n",
            updated,
        )
    updated = updated.replace("### 作答更新｜题目 ", "### 作答更新｜测试｜题目 ")
    return updated


def update_diary(path: Path, session_ids: list[str]) -> bool:
    if not path.exists():
        return False
    original = path.read_text(encoding="utf-8")
    updated = normalize_record_labels(original, session_ids)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def update_wrong_notebook(session_ids: list[str]) -> bool:
    if not WRONG_NOTEBOOK.exists():
        return False
    original = WRONG_NOTEBOOK.read_text(encoding="utf-8")
    updated = original
    for session_id in session_ids:
        updated = re.sub(
            rf"^## ([0-9-]+)｜会话 {re.escape(session_id)}｜第 ",
            r"## \1｜测试｜会话 " + session_id + "｜第 ",
            updated,
            flags=re.MULTILINE,
        )
    if updated == original:
        return False
    WRONG_NOTEBOOK.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark generated study records as test data.")
    parser.add_argument("--session-date", default=None, help="Mark all sessions on this date as test.")
    parser.add_argument("--session-id", action="append", dest="session_ids", default=None, help="Specific session id to mark.")
    args = parser.parse_args()

    conn = connect_db()
    target_ids = list(args.session_ids or [])
    if args.session_date:
        rows = conn.execute(
            "SELECT id FROM sessions WHERE session_date = ? ORDER BY created_at ASC, id ASC",
            (args.session_date,),
        ).fetchall()
        target_ids.extend(str(row["id"]) for row in rows)
    target_ids = list(dict.fromkeys(target_ids))
    if not target_ids:
        raise SystemExit("No sessions matched the requested test-data scope.")

    placeholders = ",".join("?" for _ in target_ids)
    stamp = conn.execute("SELECT datetime('now', 'localtime')").fetchone()[0]
    conn.execute(
        f"UPDATE sessions SET record_kind = 'test', updated_at = COALESCE(updated_at, ?) WHERE id IN ({placeholders})",
        (stamp, *target_ids),
    )
    conn.execute(
        f"UPDATE questions SET record_kind = 'test', updated_at = COALESCE(updated_at, ?) WHERE session_id IN ({placeholders})",
        (stamp, *target_ids),
    )
    conn.execute(
        f"""
        UPDATE attempts
        SET record_kind = 'test'
        WHERE question_id IN (
            SELECT id FROM questions WHERE session_id IN ({placeholders})
        )
        """,
        tuple(target_ids),
    )
    conn.execute(
        f"UPDATE mistakes SET record_kind = 'test' WHERE session_id IN ({placeholders})",
        tuple(target_ids),
    )
    conn.commit()

    touched_diaries: list[str] = []
    if args.session_date:
        diary_path = DIARY_DIR / f"{args.session_date}.md"
        if update_diary(diary_path, target_ids):
            touched_diaries.append(str(diary_path))
    else:
        day_rows = conn.execute(
            f"SELECT DISTINCT session_date FROM sessions WHERE id IN ({placeholders})",
            tuple(target_ids),
        ).fetchall()
        for row in day_rows:
            diary_path = DIARY_DIR / f"{row['session_date']}.md"
            if update_diary(diary_path, target_ids):
                touched_diaries.append(str(diary_path))
    wrong_notebook_changed = update_wrong_notebook(target_ids)

    emit_json(
        {
            "marked_sessions": target_ids,
            "diaries_updated": touched_diaries,
            "wrong_notebook_updated": wrong_notebook_changed,
        }
    )


if __name__ == "__main__":
    run_tool_main("mark_test_data", main)
