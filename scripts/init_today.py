from __future__ import annotations

import argparse
import re
from datetime import datetime

from study_core import PROFILE_PATH, connect_db, due_clause, emit_json, ts
from tool_logging import run_tool_main


def resolve_now(raw: str | None) -> datetime:
    if raw:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    return datetime.now().replace(second=0, microsecond=0)


def profile_value(content: str, label: str, default: str = "待确认") -> str:
    match = re.search(rf"{re.escape(label)}[:：]\s*(.+)", content)
    if not match:
        return default
    value = match.group(1).strip()
    if not value or value in {"待确认", "未设置", "TBD"}:
        return default
    return value


def parse_exam_datetime(content: str) -> datetime | None:
    raw = profile_value(content, "考试时间", "")
    match = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", raw)
    if not match:
        return None
    return datetime.strptime(f"{match.group(1)} {match.group(2)}:00", "%Y-%m-%d %H:%M:%S")


def format_countdown(now_dt: datetime, exam_dt: datetime | None) -> str:
    if exam_dt is None:
        return "待确认"
    delta_seconds = int((exam_dt - now_dt).total_seconds())
    if delta_seconds <= 0:
        return "已到目标时间"
    days = delta_seconds // 86400
    hours = (delta_seconds % 86400) // 3600
    minutes = (delta_seconds % 3600) // 60
    return f"{days} 天 {hours} 小时 {minutes} 分钟"


def count_rows(conn, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0] or 0)


def build_due_counts(conn, now_stamp: str) -> tuple[int, int, int]:
    vocab_due = count_rows(conn, f"SELECT COUNT(*) FROM vocab_items WHERE {due_clause()}", (now_stamp,))
    grammar_due = count_rows(conn, f"SELECT COUNT(*) FROM grammar_items WHERE {due_clause()}", (now_stamp,))
    mistakes_due = count_rows(
        conn,
        """
        SELECT COUNT(*)
        FROM mistakes
        WHERE status = 'open' AND COALESCE(record_kind, 'actual') = 'actual'
        """,
    )
    return vocab_due, grammar_due, mistakes_due


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize a language-drill study session.")
    parser.add_argument("--now", default=None, help="Current local time in YYYY-MM-DD HH:MM:SS.")
    args = parser.parse_args()

    now_dt = resolve_now(args.now)
    content = PROFILE_PATH.read_text(encoding="utf-8") if PROFILE_PATH.exists() else ""
    target_language = profile_value(content, "目标语言")
    exam_goal = profile_value(content, "考试目标")
    daily_load = profile_value(content, "每日题量")
    preferences = profile_value(content, "个人偏好")
    exam_dt = parse_exam_datetime(content)

    conn = connect_db()
    user_vocab = count_rows(conn, "SELECT COUNT(*) FROM vocab_items WHERE source_scope = 'user'")
    user_grammar = count_rows(conn, "SELECT COUNT(*) FROM grammar_items WHERE source_scope = 'user'")
    syllabus_vocab = count_rows(conn, "SELECT COUNT(*) FROM vocab_items WHERE source_scope <> 'user'")
    syllabus_grammar = count_rows(conn, "SELECT COUNT(*) FROM grammar_items WHERE source_scope <> 'user'")
    checkin_days = count_rows(
        conn,
        """
        SELECT COUNT(DISTINCT session_date)
        FROM sessions
        WHERE COALESCE(record_kind, 'actual') = 'actual'
        """,
    )
    vocab_due, grammar_due, mistakes_due = build_due_counts(conn, ts(now_dt))
    countdown = format_countdown(now_dt, exam_dt)

    needs_onboarding = any(
        value == "待确认"
        for value in (target_language, exam_goal, daily_load)
    )
    onboarding_questions = [
        "目标语言是什么？暂时支持日语和英语，其他语言也可先按同一流程建档。",
        "考试目标或能力目标是什么？请给出考试名、级别、目标分或目标能力描述。",
        "考试/阶段截止时间是什么？格式建议为 YYYY-MM-DD HH:MM。",
        "你的学习背景和当前阶段是什么？例如刚开始背词、已学完一轮、薄弱项等。",
        "每天希望做多少题或学习多久？是否需要每日提醒？",
        "是否允许我主动搜索/导入考纲，并收集近年真题作为题型参考？",
    ]

    message_lines = [
        f"今天是 {now_dt.strftime('%Y-%m-%d')}。",
        f"目标语言：{target_language}；考试目标：{exam_goal}。",
        f"距离目标时间还剩：{countdown}。",
        f"当前学习库：用户词汇 {user_vocab}，用户语法 {user_grammar}。",
        f"已入库考纲/资料范围：词汇 {syllabus_vocab}，语法 {syllabus_grammar}。",
        f"实际打卡天数：{checkin_days} 天。",
        f"今日到期复习：词汇 {vocab_due}，语法 {grammar_due}，错题 {mistakes_due}。",
        f"每日题量：{daily_load}；个人偏好：{preferences}。",
    ]
    if needs_onboarding:
        message_lines.append("初始化信息还不完整，请先补齐：")
        message_lines.extend(f"- {item}" for item in onboarding_questions)
    else:
        message_lines.append("可以发送今日新词、语法、资料或直接要求生成本轮完整题单。")

    emit_json(
        {
            "now": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "target_language": target_language,
            "exam_goal": exam_goal,
            "exam_datetime": exam_dt.strftime("%Y-%m-%d %H:%M:%S") if exam_dt else None,
            "countdown": countdown,
            "user_progress": {"vocab": user_vocab, "grammar": user_grammar},
            "syllabus_scope": {"vocab": syllabus_vocab, "grammar": syllabus_grammar},
            "checkin_days": checkin_days,
            "due": {"vocab": vocab_due, "grammar": grammar_due, "mistakes": mistakes_due},
            "needs_onboarding": needs_onboarding,
            "onboarding_questions": onboarding_questions if needs_onboarding else [],
            "message": "\n".join(message_lines),
        }
    )


if __name__ == "__main__":
    run_tool_main("init_today", main)
