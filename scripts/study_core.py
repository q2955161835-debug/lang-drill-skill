from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from tool_logging import note_tool_output, run_tool_main

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "study.db"
PROGRESS_LOG = ROOT / "doc" / "进展记录.md"
WRONG_NOTEBOOK = ROOT / "doc" / "错题集.md"
DIARY_DIR = ROOT / "doc" / "习题日记"
SUMMARY_DIR = ROOT / "doc" / "当日总结"
TRUE_PAPER_DIR = ROOT / "doc" / "真题"
LOCAL_RULES = ROOT / "doc" / "项目局部规则.md"
PROFILE_PATH = ROOT / "data" / "background" / "student_profile.md"
GLOBAL_RULES = ROOT / "AGENTS.md"
SKILL_SRC = ROOT / "skills" / "lang-drill-coach"
SKILL_PUBLISH_TARGET = Path(r"D:\2Folder\skills\lang-drill-coach")
DEFAULT_MOJI_BUNDLE = ROOT / "data" / "intake"
NOW_FMT = "%Y-%m-%d %H:%M"


@dataclass
class ImportResult:
    inserted: int
    updated: int
    touched_ids: list[int]


def now_local() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def ts(dt: datetime | None = None) -> str:
    return (dt or now_local()).strftime("%Y-%m-%d %H:%M:%S")


def minute(dt: datetime | None = None) -> str:
    return (dt or now_local()).strftime(NOW_FMT)


def parse_ts(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def japanese_fragments(text: str) -> list[str]:
    return re.findall(r"[ぁ-んァ-ヶー一-龯]+", text or "")


def mask_pattern_in_example(example: str, pattern: str) -> str:
    sentence = (example or "").strip()
    if not sentence:
        return "______"
    raw_pattern = (pattern or "").replace(" ", "").replace("　", "")
    candidates: list[str] = []
    if raw_pattern:
        cleaned = raw_pattern.replace("〜", "").replace("～", "")
        if cleaned:
            candidates.append(cleaned)
        candidates.extend(japanese_fragments(cleaned))
    seen: set[str] = set()
    for candidate in sorted(candidates, key=len, reverse=True):
        token = candidate.strip()
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        if token in sentence:
            return sentence.replace(token, "______", 1)
    punct = ""
    body = sentence
    if sentence[-1] in "。！？":
        punct = sentence[-1]
        body = sentence[:-1]
    if len(body) >= 4:
        return f"{body[:-4]}______{punct}"
    return f"______{punct}"


def ensure_dirs() -> None:
    for path in (DB_PATH.parent, DIARY_DIR, SUMMARY_DIR, TRUE_PAPER_DIR, WRONG_NOTEBOOK.parent, PROGRESS_LOG.parent):
        path.mkdir(parents=True, exist_ok=True)


def connect_db() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    seed_knowledge_base(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vocab_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL,
            reading TEXT NOT NULL DEFAULT '',
            meaning TEXT NOT NULL DEFAULT '',
            pos TEXT NOT NULL DEFAULT '',
            source_scope TEXT NOT NULL DEFAULT 'user',
            source_type TEXT NOT NULL DEFAULT 'chat',
            first_seen_at TEXT,
            first_memorized_at TEXT,
            last_review_at TEXT,
            proficiency INTEGER,
            difficulty INTEGER DEFAULT 2,
            times_seen INTEGER NOT NULL DEFAULT 0,
            correct_times INTEGER NOT NULL DEFAULT 0,
            incorrect_times INTEGER NOT NULL DEFAULT 0,
            correct_rate REAL,
            next_due_at TEXT,
            learned_from_exercise INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(term, reading, source_scope)
        );

        CREATE TABLE IF NOT EXISTS grammar_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            meaning_cn TEXT NOT NULL DEFAULT '',
            core_usage TEXT NOT NULL DEFAULT '',
            example TEXT NOT NULL DEFAULT '',
            source_scope TEXT NOT NULL DEFAULT 'user',
            source_type TEXT NOT NULL DEFAULT 'chat',
            first_seen_at TEXT,
            first_studied_at TEXT,
            last_review_at TEXT,
            proficiency INTEGER,
            difficulty INTEGER DEFAULT 2,
            times_seen INTEGER NOT NULL DEFAULT 0,
            correct_times INTEGER NOT NULL DEFAULT 0,
            incorrect_times INTEGER NOT NULL DEFAULT 0,
            correct_rate REAL,
            next_due_at TEXT,
            learned_from_exercise INTEGER NOT NULL DEFAULT 0,
            confusable_with TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(pattern, source_scope)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            session_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'generated',
            target_minutes INTEGER NOT NULL DEFAULT 30,
            question_count INTEGER NOT NULL DEFAULT 0,
            source_summary TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT '',
            started_at TEXT,
            completed_at TEXT,
            post_review_synced_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            section_name TEXT NOT NULL,
            question_type TEXT NOT NULL,
            difficulty INTEGER NOT NULL DEFAULT 2,
            prompt TEXT NOT NULL,
            answer TEXT NOT NULL,
            explanation TEXT NOT NULL,
            knowledge_tags TEXT NOT NULL DEFAULT '[]',
            is_new_knowledge INTEGER NOT NULL DEFAULT 0,
            source_scope TEXT NOT NULL DEFAULT 'mixed',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            answered_at TEXT NOT NULL,
            user_answer TEXT NOT NULL,
            normalized_answer TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            score REAL NOT NULL DEFAULT 0,
            feedback_summary TEXT NOT NULL DEFAULT '',
            response_seconds INTEGER,
            FOREIGN KEY(question_id) REFERENCES questions(id)
        );

        CREATE TABLE IF NOT EXISTS mistakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            attempt_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            session_id TEXT NOT NULL,
            mistake_type TEXT NOT NULL DEFAULT 'answer',
            user_answer TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            reason TEXT NOT NULL,
            review_suggestion TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            FOREIGN KEY(question_id) REFERENCES questions(id),
            FOREIGN KEY(attempt_id) REFERENCES attempts(id)
        );

        CREATE TABLE IF NOT EXISTS paper_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_name TEXT NOT NULL,
            year TEXT NOT NULL,
            level TEXT NOT NULL,
            section TEXT NOT NULL DEFAULT '',
            source_status TEXT NOT NULL DEFAULT 'indexed',
            source_path TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS material_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            source_scope TEXT NOT NULL DEFAULT 'external',
            sha1 TEXT NOT NULL DEFAULT '',
            import_status TEXT NOT NULL DEFAULT 'indexed',
            imported_at TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS mock_papers (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            paper_date TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'cjt4',
            target_minutes INTEGER NOT NULL DEFAULT 120,
            question_count INTEGER NOT NULL DEFAULT 0,
            blueprint_json TEXT NOT NULL DEFAULT '{}',
            source_summary TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'generated',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mock_paper_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            section_name TEXT NOT NULL,
            question_type TEXT NOT NULL,
            difficulty INTEGER NOT NULL DEFAULT 2,
            prompt TEXT NOT NULL,
            answer TEXT NOT NULL,
            explanation TEXT NOT NULL,
            knowledge_tags TEXT NOT NULL DEFAULT '[]',
            is_new_knowledge INTEGER NOT NULL DEFAULT 0,
            source_scope TEXT NOT NULL DEFAULT 'mixed',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(paper_id) REFERENCES mock_papers(id)
        );
        """
    )
    ensure_column(conn, "vocab_items", "status_label TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "vocab_items", "external_score INTEGER")
    ensure_column(conn, "vocab_items", "mastery_score INTEGER")
    ensure_column(conn, "vocab_items", "evidence_source TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "grammar_items", "status_label TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "grammar_items", "external_score INTEGER")
    ensure_column(conn, "grammar_items", "mastery_score INTEGER")
    ensure_column(conn, "grammar_items", "evidence_source TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "sessions", "record_kind TEXT NOT NULL DEFAULT 'actual'")
    ensure_column(conn, "sessions", "started_at TEXT")
    ensure_column(conn, "sessions", "completed_at TEXT")
    ensure_column(conn, "sessions", "post_review_synced_at TEXT")
    ensure_column(conn, "questions", "record_kind TEXT NOT NULL DEFAULT 'actual'")
    ensure_column(conn, "attempts", "record_kind TEXT NOT NULL DEFAULT 'actual'")
    ensure_column(conn, "mistakes", "record_kind TEXT NOT NULL DEFAULT 'actual'")
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    column_name = definition.split()[0]
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column_name in columns:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def seed_knowledge_base(conn: sqlite3.Connection) -> None:
    seed_pairs = [
        (ROOT / "data" / "kb" / "gaokao-japanese" / "official_vocab_2020.json", "vocab"),
        (ROOT / "data" / "kb" / "gaokao-japanese" / "official_grammar_2020.json", "grammar"),
        (ROOT / "data" / "kb" / "cjt4" / "official_vocab_2023.json", "vocab"),
        (ROOT / "data" / "kb" / "cjt4" / "official_grammar_2023.json", "grammar"),
        (ROOT / "data" / "kb" / "gaokao-japanese" / "seed_vocab.json", "vocab"),
        (ROOT / "data" / "kb" / "gaokao-japanese" / "seed_grammar.json", "grammar"),
        (ROOT / "data" / "kb" / "cjt4" / "seed_vocab.json", "vocab"),
        (ROOT / "data" / "kb" / "cjt4" / "seed_grammar.json", "grammar"),
    ]
    for path, mode in seed_pairs:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if mode == "vocab":
            import_vocab_entries(conn, data, imported_at=now_local(), memorize=False)
        else:
            import_grammar_entries(conn, data, imported_at=now_local(), study=False)


def load_entries(input_text: str | None, input_file: str | None, mode: str) -> list[dict[str, Any]]:
    if input_file:
        path = Path(input_file)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        input_text = path.read_text(encoding="utf-8")
    if not input_text:
        return []
    entries: list[dict[str, Any]] = []
    for raw_line in input_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if mode == "vocab":
            fields = ["term", "reading", "meaning", "pos", "notes"]
        else:
            fields = ["pattern", "meaning_cn", "core_usage", "example", "confusable_with"]
        row = {field: parts[idx] if idx < len(parts) else "" for idx, field in enumerate(fields)}
        entries.append(row)
    return entries


def status_to_proficiency(status_label: str) -> int | None:
    mapping = {
        "未学习": 0,
        "初学": 1,
        "复习中": 2,
        "已学习": 3,
        "已掌握": 4,
        "熟练": 5,
    }
    return mapping.get(status_label.strip(), None)


def status_to_score(status_label: str) -> int | None:
    mapping = {
        "未学习": 15,
        "初学": 35,
        "复习中": 65,
        "已学习": 78,
        "已掌握": 92,
        "熟练": 97,
    }
    return mapping.get(status_label.strip(), None)


def score_to_proficiency(score: int | None) -> int | None:
    if score is None:
        return None
    if score >= 95:
        return 5
    if score >= 85:
        return 4
    if score >= 70:
        return 3
    if score >= 55:
        return 2
    if score >= 40:
        return 1
    return 0


def adjust_mastery_score(current_score: int | None, is_correct: bool, similarity_score: float = 1.0) -> int:
    score = current_score
    if score is None:
        score = 60 if is_correct else 45
    delta = int(round((6 if is_correct else -12) * max(0.35, similarity_score)))
    return max(0, min(100, score + delta))


def mastery_order_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"COALESCE({prefix}mastery_score, COALESCE({prefix}proficiency, 0) * 20, 0)"


def source_priority_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"CASE {prefix}source_scope WHEN 'user' THEN 0 WHEN 'cjt4' THEN 1 WHEN 'gaokao' THEN 2 ELSE 3 END"


def resolve_vocab_reference(
    conn: sqlite3.Connection,
    term: str,
    reading: str,
) -> sqlite3.Row | None:
    if reading:
        row = conn.execute(
            """
            SELECT term, reading, meaning, pos, source_scope
            FROM vocab_items
            WHERE term = ? AND reading = ? AND source_scope <> 'user'
            ORDER BY CASE source_scope WHEN 'gaokao' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (term, reading),
        ).fetchone()
        if row:
            return row
    return conn.execute(
        """
        SELECT term, reading, meaning, pos, source_scope
        FROM vocab_items
        WHERE term = ? AND source_scope <> 'user'
        ORDER BY CASE source_scope WHEN 'gaokao' THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (term,),
    ).fetchone()


def import_vocab_entries(
    conn: sqlite3.Connection,
    entries: Iterable[dict[str, Any]],
    imported_at: datetime | None = None,
    source_scope: str | None = None,
    source_type: str | None = None,
    memorize: bool = True,
) -> ImportResult:
    imported_at = imported_at or now_local()
    stamp = ts(imported_at)
    inserted = 0
    updated = 0
    touched_ids: list[int] = []
    for entry in entries:
        term = (entry.get("term") or "").strip()
        if not term:
            continue
        reading = (entry.get("reading") or "").strip()
        meaning = (entry.get("meaning") or "").strip()
        pos = (entry.get("pos") or "").strip()
        scope = (source_scope or entry.get("source_scope") or "user").strip() or "user"
        source = (source_type or entry.get("source_type") or "chat").strip() or "chat"
        difficulty = int(entry.get("difficulty") or 2)
        notes = (entry.get("notes") or "").strip()
        status_label = (entry.get("status_label") or "").strip()
        evidence_source = (entry.get("evidence_source") or "").strip()
        raw_score = entry.get("external_score")
        external_score = int(raw_score) if raw_score not in (None, "", "null") else None
        reference = resolve_vocab_reference(conn, term, reading)
        if reference:
            if not reading:
                reading = (reference["reading"] or "").strip()
            if not meaning:
                meaning = (reference["meaning"] or "").strip()
            if not pos:
                pos = (reference["pos"] or "").strip()
            if not notes and source == "moji_screenshot":
                notes = f"参考 {reference['source_scope']} 官方词汇表自动补全义项"
        mastery_score = external_score
        if mastery_score is None:
            mastery_score = status_to_score(status_label)
        target_prof = score_to_proficiency(mastery_score)
        if target_prof is None:
            target_prof = status_to_proficiency(status_label)
        existing = conn.execute(
            "SELECT id, first_memorized_at, proficiency, external_score, mastery_score, status_label, evidence_source FROM vocab_items WHERE term = ? AND reading = ? AND source_scope = ?",
            (term, reading, scope),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE vocab_items
                SET meaning = COALESCE(NULLIF(?, ''), meaning),
                    pos = COALESCE(NULLIF(?, ''), pos),
                    source_type = ?,
                    difficulty = ?,
                    notes = CASE WHEN ? <> '' THEN ? ELSE notes END,
                    status_label = CASE WHEN ? <> '' THEN ? ELSE status_label END,
                    external_score = COALESCE(?, external_score),
                    mastery_score = COALESCE(?, mastery_score),
                    evidence_source = CASE WHEN ? <> '' THEN ? ELSE evidence_source END,
                    proficiency = CASE
                        WHEN ? IS NOT NULL AND (proficiency IS NULL OR ? > proficiency) THEN ?
                        ELSE proficiency
                    END,
                    first_memorized_at = CASE
                        WHEN ? = 1 AND (first_memorized_at IS NULL OR first_memorized_at = '') THEN ?
                        ELSE first_memorized_at
                    END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    meaning,
                    pos,
                    source,
                    difficulty,
                    notes,
                    notes,
                    status_label,
                    status_label,
                    external_score,
                    mastery_score,
                    evidence_source,
                    evidence_source,
                    target_prof,
                    target_prof if target_prof is not None else -1,
                    target_prof,
                    1 if memorize else 0,
                    stamp,
                    stamp,
                    existing["id"],
                ),
            )
            updated += 1
            touched_ids.append(int(existing["id"]))
        else:
            conn.execute(
                """
                INSERT INTO vocab_items (
                    term, reading, meaning, pos, source_scope, source_type,
                    first_seen_at, first_memorized_at, proficiency, difficulty, notes,
                    status_label, external_score, mastery_score, evidence_source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    term,
                    reading,
                    meaning,
                    pos,
                    scope,
                    source,
                    stamp,
                    stamp if memorize else None,
                    target_prof,
                    difficulty,
                    notes,
                    status_label,
                    external_score,
                    mastery_score,
                    evidence_source,
                    stamp,
                    stamp,
                ),
            )
            inserted += 1
            touched_ids.append(int(conn.execute("SELECT last_insert_rowid()").fetchone()[0]))
    conn.commit()
    return ImportResult(inserted=inserted, updated=updated, touched_ids=touched_ids)


def import_grammar_entries(
    conn: sqlite3.Connection,
    entries: Iterable[dict[str, Any]],
    imported_at: datetime | None = None,
    source_scope: str | None = None,
    source_type: str | None = None,
    study: bool = True,
) -> ImportResult:
    imported_at = imported_at or now_local()
    stamp = ts(imported_at)
    inserted = 0
    updated = 0
    touched_ids: list[int] = []
    for entry in entries:
        pattern = (entry.get("pattern") or "").strip()
        if not pattern:
            continue
        meaning_cn = (entry.get("meaning_cn") or "").strip()
        core_usage = (entry.get("core_usage") or "").strip()
        example = (entry.get("example") or "").strip()
        confusable_with = (entry.get("confusable_with") or "").strip()
        scope = (source_scope or entry.get("source_scope") or "user").strip() or "user"
        source = (source_type or entry.get("source_type") or "chat").strip() or "chat"
        difficulty = int(entry.get("difficulty") or 2)
        notes = (entry.get("notes") or "").strip()
        status_label = (entry.get("status_label") or "").strip()
        evidence_source = (entry.get("evidence_source") or "").strip()
        raw_score = entry.get("external_score")
        external_score = int(raw_score) if raw_score not in (None, "", "null") else None
        mastery_score = external_score
        if mastery_score is None:
            mastery_score = status_to_score(status_label)
        target_prof = score_to_proficiency(mastery_score)
        if target_prof is None:
            target_prof = status_to_proficiency(status_label)
        existing = conn.execute(
            "SELECT id, first_studied_at FROM grammar_items WHERE pattern = ? AND source_scope = ?",
            (pattern, scope),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE grammar_items
                SET meaning_cn = COALESCE(NULLIF(?, ''), meaning_cn),
                    core_usage = COALESCE(NULLIF(?, ''), core_usage),
                    example = COALESCE(NULLIF(?, ''), example),
                    confusable_with = COALESCE(NULLIF(?, ''), confusable_with),
                    source_type = ?,
                    difficulty = ?,
                    notes = CASE WHEN ? <> '' THEN ? ELSE notes END,
                    status_label = CASE WHEN ? <> '' THEN ? ELSE status_label END,
                    external_score = COALESCE(?, external_score),
                    mastery_score = COALESCE(?, mastery_score),
                    evidence_source = CASE WHEN ? <> '' THEN ? ELSE evidence_source END,
                    proficiency = CASE
                        WHEN ? IS NOT NULL AND (proficiency IS NULL OR ? > proficiency) THEN ?
                        ELSE proficiency
                    END,
                    first_studied_at = CASE
                        WHEN ? = 1 AND (first_studied_at IS NULL OR first_studied_at = '') THEN ?
                        ELSE first_studied_at
                    END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    meaning_cn,
                    core_usage,
                    example,
                    confusable_with,
                    source,
                    difficulty,
                    notes,
                    notes,
                    status_label,
                    status_label,
                    external_score,
                    mastery_score,
                    evidence_source,
                    evidence_source,
                    target_prof,
                    target_prof if target_prof is not None else -1,
                    target_prof,
                    1 if study else 0,
                    stamp,
                    stamp,
                    existing["id"],
                ),
            )
            updated += 1
            touched_ids.append(int(existing["id"]))
        else:
            conn.execute(
                """
                INSERT INTO grammar_items (
                    pattern, meaning_cn, core_usage, example, source_scope, source_type,
                    first_seen_at, first_studied_at, proficiency, difficulty, confusable_with,
                    notes, status_label, external_score, mastery_score, evidence_source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pattern,
                    meaning_cn,
                    core_usage,
                    example,
                    scope,
                    source,
                    stamp,
                    stamp if study else None,
                    target_prof,
                    difficulty,
                    confusable_with,
                    notes,
                    status_label,
                    external_score,
                    mastery_score,
                    evidence_source,
                    stamp,
                    stamp,
                ),
            )
            inserted += 1
            touched_ids.append(int(conn.execute("SELECT last_insert_rowid()").fetchone()[0]))
    conn.commit()
    return ImportResult(inserted=inserted, updated=updated, touched_ids=touched_ids)


def normalize_answer(text: str) -> str:
    return "".join(ch for ch in text.strip().upper() if ch.isalnum())


def display_record_kind(record_kind: str | None) -> str:
    return "测试" if (record_kind or "actual").strip().lower() == "test" else "正式"


def schedule_days(proficiency: int | None, is_correct: bool) -> int:
    correct_ladder = [1, 2, 4, 7, 14, 28]
    wrong_ladder = [0, 1, 1, 2, 3, 5]
    prof = max(0, min(5, proficiency or 0))
    if not is_correct:
        return wrong_ladder[prof]
    return correct_ladder[prof]


def due_clause(column: str = "next_due_at") -> str:
    return f"{column} IS NOT NULL AND {column} <> '' AND {column} <= ?"


def fetch_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params).fetchall())


def parse_knowledge_tags(raw_value: str | None) -> list[dict[str, Any]]:
    if not raw_value:
        return []
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def fetch_recent_actual_questions(conn: sqlite3.Connection, limit: int = 12) -> list[sqlite3.Row]:
    return fetch_rows(
        conn,
        """
        SELECT q.id, q.section_name, q.question_type, q.knowledge_tags, q.created_at
        FROM questions q
        JOIN sessions s ON s.id = q.session_id
        WHERE COALESCE(s.record_kind, 'actual') = 'actual'
        ORDER BY q.id DESC
        LIMIT ?
        """,
        (limit,),
    )


def recent_question_constraints(conn: sqlite3.Connection, knowledge_window: int = 3) -> dict[str, Any]:
    rows = fetch_recent_actual_questions(conn, limit=max(knowledge_window, 12))
    recent_vocab_ids: set[int] = set()
    recent_grammar_ids: set[int] = set()
    recent_terms: list[str] = []
    recent_patterns: list[str] = []
    for row in rows[:knowledge_window]:
        for tag in parse_knowledge_tags(row["knowledge_tags"]):
            if tag.get("kind") == "vocab" and tag.get("id") is not None:
                recent_vocab_ids.add(int(tag["id"]))
                if tag.get("term"):
                    recent_terms.append(str(tag["term"]))
            if tag.get("kind") == "grammar" and tag.get("id") is not None:
                recent_grammar_ids.add(int(tag["id"]))
                if tag.get("pattern"):
                    recent_patterns.append(str(tag["pattern"]))
    type_streak = 0
    streak_type = ""
    if rows:
        streak_type = rows[0]["question_type"]
        for row in rows:
            if row["question_type"] != streak_type:
                break
            type_streak += 1
    blocked_question_types = [streak_type] if streak_type and type_streak >= 4 else []
    return {
        "recent_vocab_ids": recent_vocab_ids,
        "recent_grammar_ids": recent_grammar_ids,
        "recent_terms": recent_terms,
        "recent_patterns": recent_patterns,
        "recent_question_types": [row["question_type"] for row in rows[:5]],
        "blocked_question_types": blocked_question_types,
        "current_question_type_streak": {
            "question_type": streak_type,
            "count": type_streak,
        },
    }


def interleave_row_groups(groups: list[list[sqlite3.Row]]) -> list[sqlite3.Row]:
    queues = [list(group) for group in groups if group]
    result: list[sqlite3.Row] = []
    while any(queues):
        advanced = False
        for queue in queues:
            if not queue:
                continue
            result.append(queue.pop(0))
            advanced = True
        if not advanced:
            break
    return result


def interleave_question_groups(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    queues = [list(group) for group in groups if group]
    result: list[dict[str, Any]] = []
    while any(queues):
        advanced = False
        for queue in queues:
            if not queue:
                continue
            result.append(queue.pop(0))
            advanced = True
        if not advanced:
            break
    return result


def prioritize_with_recent_holdout(
    rows: list[sqlite3.Row],
    blocked_ids: set[int],
) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    fresh: list[sqlite3.Row] = []
    holdout: list[sqlite3.Row] = []
    for row in rows:
        if row["id"] in blocked_ids:
            holdout.append(row)
        else:
            fresh.append(row)
    return fresh, holdout


def day_end_stamp(session_day: str) -> str:
    return f"{session_day} 23:59:59"


def load_day_intake_vocab_refs(session_day: str) -> list[tuple[str, str]]:
    path = ROOT / "data" / "intake" / f"moji_vocab_{session_day}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    refs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in payload if isinstance(payload, list) else []:
        if not isinstance(entry, dict):
            continue
        term = (entry.get("term") or "").strip()
        reading = (entry.get("reading") or "").strip()
        if not term:
            continue
        key = (term, reading)
        if key in seen:
            continue
        seen.add(key)
        refs.append(key)
    return refs


def fetch_day_intake_vocab_rows(conn: sqlite3.Connection, session_day: str) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    seen_ids: set[int] = set()
    for term, reading in load_day_intake_vocab_refs(session_day):
        if reading:
            row = conn.execute(
                """
                SELECT *
                FROM vocab_items
                WHERE source_scope = 'user' AND term = ? AND reading = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (term, reading),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT *
                FROM vocab_items
                WHERE source_scope = 'user' AND term = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (term,),
            ).fetchone()
        if not row or int(row["id"]) in seen_ids:
            continue
        seen_ids.add(int(row["id"]))
        rows.append(row)
    return rows


def merge_vocab_row_groups(*groups: list[sqlite3.Row], limit: int | None = None) -> list[sqlite3.Row]:
    merged: list[sqlite3.Row] = []
    seen_ids: set[int] = set()
    for group in groups:
        for row in group:
            row_id = int(row["id"])
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            merged.append(row)
            if limit and len(merged) >= limit:
                return merged
    return merged


def fetch_day_new_vocab_rows(conn: sqlite3.Connection, session_day: str, limit: int | None = None) -> list[sqlite3.Row]:
    day_prefix = f"{session_day}%"
    limit_sql = f" LIMIT {int(limit)}" if limit else ""
    intake_rows = fetch_day_intake_vocab_rows(conn, session_day)
    preferred = fetch_rows(
        conn,
        """
        SELECT * FROM vocab_items
        WHERE source_scope = 'user'
          AND source_type = 'chat-image'
          AND first_memorized_at LIKE ?
        ORDER BY difficulty ASC, updated_at DESC
        """
        + limit_sql,
        (day_prefix,),
    )
    if preferred:
        return merge_vocab_row_groups(intake_rows, preferred, limit=limit)
    batch_rows = fetch_rows(
        conn,
        """
        SELECT * FROM vocab_items
        WHERE source_scope = 'user'
          AND COALESCE(source_type, '') <> 'moji_screenshot'
          AND first_memorized_at LIKE ?
        ORDER BY difficulty ASC, updated_at DESC
        """
        + limit_sql,
        (day_prefix,),
    )
    if batch_rows:
        return merge_vocab_row_groups(intake_rows, batch_rows, limit=limit)
    fallback = fetch_rows(
        conn,
        """
        SELECT * FROM vocab_items
        WHERE source_scope = 'user' AND (first_memorized_at LIKE ? OR first_seen_at LIKE ?)
        ORDER BY difficulty ASC, updated_at DESC
        """
        + limit_sql,
        (day_prefix, day_prefix),
    )
    return merge_vocab_row_groups(intake_rows, fallback, limit=limit)


def fetch_day_new_grammar_rows(conn: sqlite3.Connection, session_day: str, limit: int | None = None) -> list[sqlite3.Row]:
    day_prefix = f"{session_day}%"
    limit_sql = f" LIMIT {int(limit)}" if limit else ""
    preferred = fetch_rows(
        conn,
        """
        SELECT * FROM grammar_items
        WHERE source_scope = 'user'
          AND COALESCE(source_type, '') <> 'exercise-derived'
          AND first_studied_at LIKE ?
        ORDER BY difficulty ASC, updated_at DESC
        """
        + limit_sql,
        (day_prefix,),
    )
    if preferred:
        return preferred
    fallback = fetch_rows(
        conn,
        """
        SELECT * FROM grammar_items
        WHERE source_scope = 'user' AND (first_studied_at LIKE ? OR first_seen_at LIKE ?)
        ORDER BY difficulty ASC, updated_at DESC
        """
        + limit_sql,
        (day_prefix, day_prefix),
    )
    return fallback


def get_study_pool(
    conn: sqlite3.Connection,
    session_day: str,
    reference_stamp: str | None = None,
) -> dict[str, list[sqlite3.Row]]:
    day_prefix = f"{session_day}%"
    now_stamp = reference_stamp or ts()
    user_vocab_new = fetch_day_new_vocab_rows(conn, session_day)
    user_vocab_due = fetch_rows(
        conn,
        f"""
        SELECT * FROM vocab_items
        WHERE source_scope = 'user' AND {due_clause()}
        ORDER BY {mastery_order_sql()} ASC, COALESCE(correct_rate, 0) ASC, updated_at ASC
        """,
        (now_stamp,),
    )
    user_vocab_review = fetch_rows(
        conn,
        f"""
        SELECT * FROM vocab_items
        WHERE source_scope = 'user'
          AND NOT (first_memorized_at LIKE ? OR first_seen_at LIKE ?)
          AND (
                status_label = '复习中'
                OR (COALESCE(mastery_score, COALESCE(proficiency, 0) * 20, 0) BETWEEN 40 AND 79)
              )
        ORDER BY {mastery_order_sql()} ASC, updated_at ASC
        LIMIT 80
        """,
        (day_prefix, day_prefix),
    )
    user_vocab_mastered = fetch_rows(
        conn,
        f"""
        SELECT * FROM vocab_items
        WHERE source_scope = 'user'
          AND (
                status_label = '已掌握'
                OR COALESCE(mastery_score, COALESCE(proficiency, 0) * 20, 0) >= 80
              )
        ORDER BY {mastery_order_sql()} DESC, updated_at DESC
        LIMIT 80
        """,
    )
    official_vocab_support = fetch_rows(
        conn,
        f"""
        SELECT * FROM vocab_items
        WHERE source_scope <> 'user'
        ORDER BY {source_priority_sql()}, {mastery_order_sql()} ASC, difficulty ASC, updated_at DESC
        LIMIT 120
        """,
    )
    user_grammar_new = fetch_day_new_grammar_rows(conn, session_day)
    user_grammar_due = fetch_rows(
        conn,
        f"""
        SELECT * FROM grammar_items
        WHERE source_scope = 'user' AND {due_clause()}
        ORDER BY {mastery_order_sql()} ASC, COALESCE(correct_rate, 0) ASC, updated_at ASC
        LIMIT 20
        """,
        (now_stamp,),
    )
    user_grammar_review = fetch_rows(
        conn,
        f"""
        SELECT * FROM grammar_items
        WHERE source_scope = 'user'
          AND NOT (first_studied_at LIKE ? OR first_seen_at LIKE ?)
          AND (
                status_label = '复习中'
                OR (COALESCE(mastery_score, COALESCE(proficiency, 0) * 20, 0) BETWEEN 40 AND 79)
              )
        ORDER BY {mastery_order_sql()} ASC, updated_at ASC
        LIMIT 30
        """,
        (day_prefix, day_prefix),
    )
    user_grammar_mastered = fetch_rows(
        conn,
        f"""
        SELECT * FROM grammar_items
        WHERE source_scope = 'user'
          AND (
                status_label = '已掌握'
                OR COALESCE(mastery_score, COALESCE(proficiency, 0) * 20, 0) >= 80
              )
        ORDER BY {mastery_order_sql()} DESC, updated_at DESC
        LIMIT 30
        """,
    )
    official_grammar_support = fetch_rows(
        conn,
        f"""
        SELECT * FROM grammar_items
        WHERE source_scope <> 'user'
        ORDER BY CASE WHEN example <> '' THEN 0 ELSE 1 END,
                 {source_priority_sql()},
                 {mastery_order_sql()} ASC,
                 difficulty ASC,
                 updated_at DESC
        LIMIT 120
        """,
    )
    pool = {
        "new_vocab": user_vocab_new,
        "due_vocab": user_vocab_due,
        "new_grammar": user_grammar_new,
        "due_grammar": user_grammar_due,
        "user_new_vocab": user_vocab_new,
        "user_due_vocab": user_vocab_due,
        "user_review_vocab": user_vocab_review,
        "user_mastered_vocab": user_vocab_mastered,
        "official_support_vocab": official_vocab_support,
        "user_new_grammar": user_grammar_new,
        "user_due_grammar": user_grammar_due,
        "user_review_grammar": user_grammar_review,
        "user_mastered_grammar": user_grammar_mastered,
        "official_support_grammar": official_grammar_support,
        "mistakes": fetch_rows(
            conn,
            """
            SELECT m.*, q.knowledge_tags
            FROM mistakes m
            JOIN questions q ON q.id = m.question_id
            WHERE m.status = 'open' AND COALESCE(m.record_kind, 'actual') = 'actual'
            ORDER BY m.created_at DESC
            LIMIT 20
            """,
        ),
        "support_vocab": dedupe_rows(user_vocab_review + user_vocab_mastered + official_vocab_support),
        "support_grammar": dedupe_rows(user_grammar_review + user_grammar_mastered + official_grammar_support),
    }
    return pool


def dedupe_rows(rows: Iterable[sqlite3.Row], key: str = "id") -> list[sqlite3.Row]:
    seen: set[Any] = set()
    result: list[sqlite3.Row] = []
    for row in rows:
        marker = row[key]
        if marker in seen:
            continue
        seen.add(marker)
        result.append(row)
    return result


def daily_coverage_requirements(pool: dict[str, list[sqlite3.Row]]) -> dict[str, Any]:
    new_vocab_rows = dedupe_rows(pool["user_new_vocab"])
    new_vocab_ids = {int(row["id"]) for row in new_vocab_rows}
    due_vocab_rows = [row for row in dedupe_rows(pool["user_due_vocab"]) if int(row["id"]) not in new_vocab_ids]
    review_vocab_rows = [
        row
        for row in dedupe_rows(pool["user_due_vocab"] + pool["user_review_vocab"] + pool["user_mastered_vocab"])
        if int(row["id"]) not in new_vocab_ids
    ]
    grammar_rows = [
        row
        for row in dedupe_rows(
            pool["user_new_grammar"]
            + pool["user_due_grammar"]
            + pool["user_review_grammar"]
            + pool["user_mastered_grammar"]
            + pool["official_support_grammar"]
        )
        if usable_grammar_item(row)
    ]
    today_new_grammar_rows = [row for row in dedupe_rows(pool["user_new_grammar"]) if usable_grammar_item(row)]
    due_grammar_rows = [row for row in dedupe_rows(pool["user_due_grammar"]) if usable_grammar_item(row)]
    new_vocab_target = len(new_vocab_rows)
    due_vocab_count = len(due_vocab_rows)
    if due_vocab_count <= 0:
        review_vocab_target = 0
    else:
        review_vocab_target = min(due_vocab_count, max(50, (due_vocab_count + 1) // 2))
    grammar_target = min(len(grammar_rows), 10)
    return {
        "new_vocab_rows": new_vocab_rows,
        "review_vocab_rows": review_vocab_rows,
        "grammar_rows": grammar_rows,
        "today_new_vocab_ids": [int(row["id"]) for row in new_vocab_rows],
        "today_new_grammar_ids": [int(row["id"]) for row in today_new_grammar_rows],
        "due_vocab_ids": [int(row["id"]) for row in due_vocab_rows],
        "due_grammar_ids": [int(row["id"]) for row in due_grammar_rows],
        "new_vocab_target": new_vocab_target,
        "review_vocab_target": review_vocab_target,
        "grammar_target": grammar_target,
        "required_new_vocab_ids": [int(row["id"]) for row in new_vocab_rows],
        "required_review_vocab_ids": [int(row["id"]) for row in review_vocab_rows[:review_vocab_target]],
        "required_grammar_ids": [int(row["id"]) for row in grammar_rows[:grammar_target]],
        "counting_rule": "只要知识点出现在正式 questions.knowledge_tags 中，就算当天已覆盖。",
    }


def collect_knowledge_ids_from_question_rows(
    rows: Iterable[sqlite3.Row],
) -> tuple[set[int], set[int]]:
    vocab_ids: set[int] = set()
    grammar_ids: set[int] = set()
    for row in rows:
        for tag in parse_knowledge_tags(row["knowledge_tags"]):
            if tag.get("kind") == "vocab" and tag.get("id") is not None:
                vocab_ids.add(int(tag["id"]))
            if tag.get("kind") == "grammar" and tag.get("id") is not None:
                grammar_ids.add(int(tag["id"]))
    return vocab_ids, grammar_ids


def collect_knowledge_ids_from_authored_questions(
    questions: Iterable[dict[str, Any]],
) -> tuple[set[int], set[int]]:
    vocab_ids: set[int] = set()
    grammar_ids: set[int] = set()
    for question in questions:
        for tag in question.get("knowledge_tags", []):
            if tag.get("kind") == "vocab" and tag.get("id") is not None:
                vocab_ids.add(int(tag["id"]))
            if tag.get("kind") == "grammar" and tag.get("id") is not None:
                grammar_ids.add(int(tag["id"]))
    return vocab_ids, grammar_ids


def coverage_requirements_snapshot(requirements: dict[str, Any]) -> dict[str, Any]:
    return {
        "counting_rule": requirements["counting_rule"],
        "required_new_vocab_ids": list(requirements.get("required_new_vocab_ids", [])),
        "required_review_vocab_ids": list(requirements.get("required_review_vocab_ids", [])),
        "required_grammar_ids": list(requirements.get("required_grammar_ids", [])),
        "today_new_vocab_ids": list(requirements.get("today_new_vocab_ids", [])),
        "today_new_grammar_ids": list(requirements.get("today_new_grammar_ids", [])),
        "due_vocab_ids": list(requirements.get("due_vocab_ids", [])),
        "due_grammar_ids": list(requirements.get("due_grammar_ids", [])),
    }


def coverage_requirements_from_summary(summary: dict[str, Any]) -> dict[str, Any] | None:
    raw = summary.get("coverage_requirements")
    if not isinstance(raw, dict):
        return None
    counting_rule = str(raw.get("counting_rule") or "").strip()
    required_new_vocab_ids = [int(value) for value in raw.get("required_new_vocab_ids", [])]
    required_review_vocab_ids = [int(value) for value in raw.get("required_review_vocab_ids", [])]
    required_grammar_ids = [int(value) for value in raw.get("required_grammar_ids", [])]
    today_new_vocab_ids = [int(value) for value in raw.get("today_new_vocab_ids", [])]
    today_new_grammar_ids = [int(value) for value in raw.get("today_new_grammar_ids", [])]
    due_vocab_ids = [int(value) for value in raw.get("due_vocab_ids", [])]
    due_grammar_ids = [int(value) for value in raw.get("due_grammar_ids", [])]
    if not counting_rule:
        return None
    return {
        "counting_rule": counting_rule,
        "required_new_vocab_ids": required_new_vocab_ids,
        "required_review_vocab_ids": required_review_vocab_ids,
        "required_grammar_ids": required_grammar_ids,
        "today_new_vocab_ids": today_new_vocab_ids,
        "today_new_grammar_ids": today_new_grammar_ids,
        "due_vocab_ids": due_vocab_ids,
        "due_grammar_ids": due_grammar_ids,
        "new_vocab_target": len(required_new_vocab_ids),
        "review_vocab_target": len(required_review_vocab_ids),
        "grammar_target": len(required_grammar_ids),
    }


def compute_coverage_panel(
    summary: dict[str, Any],
    requirements: dict[str, Any],
    authored_vocab_ids: set[int],
    authored_grammar_ids: set[int],
) -> dict[str, dict[str, int]]:
    required_new_vocab_ids = set(requirements.get("required_new_vocab_ids", []))
    required_review_vocab_ids = set(requirements.get("required_review_vocab_ids", []))
    required_grammar_ids = set(requirements.get("required_grammar_ids", []))
    today_new_vocab_ids = set(requirements.get("today_new_vocab_ids", []))
    today_new_grammar_ids = set(requirements.get("today_new_grammar_ids", []))
    due_grammar_ids = set(requirements.get("due_grammar_ids", []))

    review_vocab_total = len(required_review_vocab_ids)
    review_grammar_total = int(summary.get("due_grammar") or len(due_grammar_ids))
    grammar_target_total = len(required_grammar_ids)
    review_vocab_covered = len(required_review_vocab_ids & authored_vocab_ids)
    review_grammar_covered = len(due_grammar_ids & authored_grammar_ids)
    grammar_target_covered = len(required_grammar_ids & authored_grammar_ids)

    return {
        "new_vocab": {
            "covered": len(required_new_vocab_ids & authored_vocab_ids),
            "total": int(summary.get("new_vocab") or len(required_new_vocab_ids)),
        },
        "review_vocab": {
            "covered": review_vocab_covered,
            "total": review_vocab_total,
        },
        "new_grammar": {
            "covered": len(today_new_grammar_ids & authored_grammar_ids),
            "total": int(summary.get("new_grammar") or len(today_new_grammar_ids)),
        },
        "review_grammar": {
            "covered": review_grammar_covered,
            "total": review_grammar_total,
        },
        "grammar_target": {
            "covered": grammar_target_covered,
            "total": grammar_target_total,
        },
    }


def enrich_authored_summary(
    conn: sqlite3.Connection,
    session_day: str,
    questions: list[dict[str, Any]],
    summary: dict[str, Any],
    reference_stamp: str | None = None,
) -> dict[str, Any]:
    enriched = dict(summary)
    requirements = daily_coverage_requirements(get_study_pool(conn, session_day, reference_stamp=reference_stamp))
    authored_vocab_ids, authored_grammar_ids = collect_knowledge_ids_from_authored_questions(questions)
    enriched["coverage_requirements"] = coverage_requirements_snapshot(requirements)
    enriched["coverage_panel"] = compute_coverage_panel(enriched, requirements, authored_vocab_ids, authored_grammar_ids)
    return enriched


def refresh_session_source_summary(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        raise ValueError(f"Session {session_id} not found.")
    question_rows = fetch_rows(
        conn,
        """
        SELECT section_name, question_type, difficulty, prompt, answer, explanation, knowledge_tags, is_new_knowledge, source_scope
        FROM questions
        WHERE session_id = ? AND COALESCE(record_kind, 'actual') = COALESCE(?, 'actual')
        ORDER BY ordinal ASC
        """,
        (session_id, session["record_kind"]),
    )
    questions = [
        {
            "section_name": row["section_name"],
            "question_type": row["question_type"],
            "difficulty": int(row["difficulty"] or 2),
            "prompt": row["prompt"],
            "answer": row["answer"],
            "explanation": row["explanation"],
            "knowledge_tags": parse_knowledge_tags(row["knowledge_tags"]),
            "is_new_knowledge": int(row["is_new_knowledge"] or 0),
            "source_scope": row["source_scope"] or "mixed",
        }
        for row in question_rows
    ]
    summary = enrich_authored_summary(
        conn,
        session["session_date"],
        questions,
        authored_session_summary(
            session["session_date"],
            int(session["target_minutes"] or 35),
            questions,
            safe_session_summary(session),
        ),
        reference_stamp=str(session["created_at"] or "") or None,
    )
    conn.execute(
        "UPDATE sessions SET source_summary = ?, question_count = ?, updated_at = ? WHERE id = ?",
        (json.dumps(summary, ensure_ascii=False), len(questions), ts(), session_id),
    )
    conn.commit()
    return summary


def estimate_target_count(pool: dict[str, list[sqlite3.Row]], target_minutes: int, max_questions: int) -> int:
    base_by_time = max(12, int(round(target_minutes * 0.95)))
    coverage_pressure = int(
        round(
            len(pool["new_vocab"]) * 0.35
            + len(pool["due_vocab"]) * 0.45
            + len(pool["user_review_vocab"]) * 0.12
            + len(pool["new_grammar"]) * 1.10
            + len(pool["due_grammar"]) * 1.25
            + len(pool["user_review_grammar"]) * 0.35
            + len(pool["mistakes"]) * 1.60
        )
    )
    coverage_target = max(0, int(round(coverage_pressure / 2.6)))
    dynamic = base_by_time + coverage_target
    requirements = daily_coverage_requirements(pool)
    minimum_coverage_floor = int(
        round(
            requirements["new_vocab_target"] * 0.55
            + requirements["review_vocab_target"] * 0.45
            + requirements["grammar_target"] * 0.80
        )
    )
    hard_floor = 24 if target_minutes >= 20 else 12
    dynamic_floor = max(dynamic, minimum_coverage_floor)
    soft_cap = min(max_questions, max(hard_floor, int(round(target_minutes * 1.6)) + coverage_target, minimum_coverage_floor))
    return max(8, min(soft_cap, dynamic_floor))


def shuffle_options(correct: str, distractors: list[str], rng: random.Random) -> tuple[list[str], str]:
    options = [correct] + distractors[:3]
    rng.shuffle(options)
    answer_letter = "ABCD"[options.index(correct)]
    return options, answer_letter


def shuffle_authored_prompt_options(prompt: str, answer: str) -> tuple[str, str]:
    normalized_answer = normalize_answer(answer)
    if normalized_answer not in {"A", "B", "C", "D"}:
        return prompt, answer
    lines = prompt.splitlines()
    option_rows: list[tuple[int, str, str]] = []
    for index, raw_line in enumerate(lines):
        match = re.match(r"^([ABCD])\.\s*(.+?)\s*$", raw_line.strip())
        if match:
            option_rows.append((index, match.group(1), match.group(2)))
    if len(option_rows) != 4:
        return prompt, answer
    labels = [label for _, label, _ in option_rows]
    if labels != ["A", "B", "C", "D"]:
        return prompt, answer
    option_texts = [text for _, _, text in option_rows]
    correct_index = "ABCD".index(normalized_answer)
    correct_text = option_texts[correct_index]
    stem = "\n".join(line for idx, line in enumerate(lines) if idx not in {row[0] for row in option_rows})
    seed_source = "\n".join([stem, correct_text, *sorted(option_texts)])
    seed_value = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:16], 16)
    order = list(range(4))
    random.Random(seed_value).shuffle(order)
    shuffled = [option_texts[index] for index in order]
    for output_index, (line_index, _, _) in enumerate(option_rows):
        lines[line_index] = f"{'ABCD'[output_index]}. {shuffled[output_index]}"
    new_answer = "ABCD"[order.index(correct_index)]
    return "\n".join(lines), new_answer


def choose_distinct_values(
    rows: list[sqlite3.Row],
    current_value: str,
    field: str,
    limit: int,
) -> list[str]:
    values: list[str] = []
    seen = {current_value}
    for row in rows:
        candidate = (row[field] or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        values.append(candidate)
        if len(values) >= limit:
            break
    return values


def choose_reading_distractors(item: sqlite3.Row, all_vocab: list[sqlite3.Row], limit: int) -> list[str]:
    correct = (item["reading"] or "").strip()
    if not correct:
        return []
    target_len = len(correct)
    target_tail = correct[-1]
    target_pos = (item["pos"] or "").strip()
    scored: list[tuple[int, str]] = []
    seen = {correct}
    for row in all_vocab:
        candidate = (row["reading"] or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        score = 0
        if len(candidate) == target_len:
            score += 4
        elif abs(len(candidate) - target_len) == 1:
            score += 2
        if candidate[-1] == target_tail:
            score += 3
        row_pos = (row["pos"] or "").strip()
        if target_pos and row_pos and target_pos.split("·")[0] == row_pos.split("·")[0]:
            score += 2
        scored.append((score, candidate))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [candidate for _, candidate in scored[:limit]]


BACKGROUND_ACTORS = ("田中さん", "佐藤さん", "近所の人", "家族", "店の人", "利用者", "担当者", "友達")
BACKGROUND_PLACES = ("駅前", "広場", "店の前", "家の近く", "公園", "案内板の前", "通り", "受付の前")
BACKGROUND_TIMES = ("朝", "昼", "夕方", "夜")
BACKGROUND_SUBJECTS = ("案内", "予定", "入口", "荷物", "店の前", "掲示", "会場")
BACKGROUND_OBJECTS = ("予定", "紙", "荷物", "客", "花", "会場", "品物")
BACKGROUND_TOPICS = ("案内の内容", "その日の予定", "受付の流れ", "会場の使い方", "周りの様子")
BACKGROUND_ACTIONS = ("早めに動く", "先に確認する", "様子を見る", "静かに待つ", "予定を変える")


def is_verb_like(item: sqlite3.Row) -> bool:
    pos = (item["pos"] or "").strip()
    return "自动" in pos or "他动" in pos or "自他动" in pos or "動" in pos


def is_modifier_like(item: sqlite3.Row) -> bool:
    pos = (item["pos"] or "").strip()
    return "副" in pos or ("形" in pos and "动" not in pos and "動" not in pos)


def row_scene_text(item: sqlite3.Row) -> str:
    return " ".join(
        part.strip()
        for part in (
            item["term"] or "",
            item["reading"] or "",
            item["meaning"] or "",
            item["notes"] or "",
        )
        if part and part.strip()
    )


def background_seed_token(rows: list[sqlite3.Row], focus_item: sqlite3.Row | None = None) -> str:
    parts: list[str] = []
    if focus_item is not None:
        parts.append(row_scene_text(focus_item))
    for row in rows[:8]:
        parts.append(row_scene_text(row))
    return "|".join(part for part in parts if part) or "background"


def pick_seeded_value(options: tuple[str, ...], seed_token: str, salt: str) -> str:
    digest = hashlib.sha1(f"{salt}:{seed_token}".encode("utf-8")).hexdigest()
    return options[int(digest[:8], 16) % len(options)]


def build_background_scenario(
    rows: list[sqlite3.Row],
    rng: random.Random,
    focus_item: sqlite3.Row | None = None,
) -> dict[str, Any]:
    weighted_rows = ([focus_item] if focus_item is not None else []) + rows
    source_rows = [row for row in weighted_rows if row is not None] or rows
    nouns = [row for row in source_rows if is_noun_like(row)]
    verbs = [row for row in source_rows if is_verb_like(row)]
    modifiers = [row for row in source_rows if is_modifier_like(row)]
    seed_token = background_seed_token(source_rows, focus_item=focus_item)
    support_terms: list[str] = []
    seen_terms: set[str] = set()
    for row in source_rows:
        term = (row["term"] or "").strip()
        if not term or term in seen_terms:
            continue
        seen_terms.add(term)
        support_terms.append(term)
        if len(support_terms) >= 4:
            break
    for fallback in (
        pick_seeded_value(BACKGROUND_TOPICS, seed_token, "topic"),
        pick_seeded_value(BACKGROUND_OBJECTS, seed_token, "object"),
    ):
        if len(support_terms) >= 3:
            break
        if fallback not in seen_terms:
            seen_terms.add(fallback)
            support_terms.append(fallback)
    subject = nouns[0]["term"] if nouns else pick_seeded_value(BACKGROUND_SUBJECTS, seed_token, "subject")
    object_term = nouns[1]["term"] if len(nouns) > 1 else (nouns[0]["term"] if nouns else pick_seeded_value(BACKGROUND_OBJECTS, seed_token, "object"))
    topic = nouns[0]["term"] if nouns else pick_seeded_value(BACKGROUND_TOPICS, seed_token, "topic")
    adverb_action = modifiers[0]["term"] if modifiers and "副" in (modifiers[0]["pos"] or "") else pick_seeded_value(BACKGROUND_ACTIONS, seed_token, "action")
    support_verbs: list[str] = []
    seen_verbs: set[str] = set()
    for row in verbs:
        term = (row["term"] or "").strip()
        if not term or term in seen_verbs:
            continue
        seen_verbs.add(term)
        support_verbs.append(term)
        if len(support_verbs) >= 3:
            break
    candidate_id = hashlib.sha1(seed_token.encode("utf-8")).hexdigest()[:8]
    return {
        "candidate_id": candidate_id,
        "actor": pick_seeded_value(BACKGROUND_ACTORS, seed_token, "actor"),
        "place": pick_seeded_value(BACKGROUND_PLACES, seed_token, "place"),
        "time": pick_seeded_value(BACKGROUND_TIMES, seed_token, "time"),
        "subject": subject,
        "object": object_term,
        "topic": topic,
        "support_terms": support_terms,
        "support_verbs": support_verbs,
        "adverb_action": adverb_action,
        "summary": f"从 {', '.join(support_terms[:3])} 抽取背景锚点，组合为非学习题材的自然语境。",
    }


def serialize_background_candidate(background: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": background["candidate_id"],
        "actor": background["actor"],
        "place": background["place"],
        "time": background["time"],
        "subject": background["subject"],
        "object": background["object"],
        "topic": background["topic"],
        "support_terms": background["support_terms"],
        "support_verbs": background["support_verbs"],
        "summary": background["summary"],
    }


def build_background_candidates(
    rows: list[sqlite3.Row],
    rng: random.Random,
    max_items: int = 6,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()
    ordered_rows = rows[: max(max_items * 3, 12)]
    for row in ordered_rows:
        background = build_background_scenario(ordered_rows, rng, focus_item=row)
        if background["candidate_id"] in seen_candidate_ids:
            continue
        seen_candidate_ids.add(background["candidate_id"])
        candidates.append(serialize_background_candidate(background))
        if len(candidates) >= max_items:
            break
    if not candidates:
        candidates.append(serialize_background_candidate(build_background_scenario(rows, rng)))
    return candidates


def vocab_meaning_option_rows(item: sqlite3.Row, all_vocab: list[sqlite3.Row]) -> list[sqlite3.Row]:
    pos = (item["pos"] or "").strip()
    if not pos:
        return all_vocab
    primary = pos.split("・")[0].split("·")[0]
    filtered = [
        row
        for row in all_vocab
        if row["id"] != item["id"] and primary and primary in ((row["pos"] or "").strip())
    ]
    return filtered or [row for row in all_vocab if row["id"] != item["id"]]


def vocab_context_sentence(item: sqlite3.Row, all_vocab: list[sqlite3.Row], rng: random.Random) -> str:
    term = item["term"]
    pos = (item["pos"] or "").strip()
    background = build_background_scenario(all_vocab, rng, focus_item=item)
    item_text = row_scene_text(item)
    custom_sentences = {
        "美味しい": "この店の料理は［美味しい］と評判だ。",
        "時": "忙しい［時］こそ、落ち着いて確認したほうがいい。",
        "まあ": "急な変更はあったが、今日は［まあ］大丈夫だろう。",
        "煙": "台所の窓から白い［煙］が見えた。",
        "指導": "新しい店員への［指導］は、店長が担当している。",
        "嗤う": "人の失敗を［嗤う］のは、よくないことだ。",
        "要約": "会議の内容を三行で［要約］してください。",
        "現す": "彼は顔に不安な気持ちを［現す］ことが多い。",
        "会社": "兄は駅前の［会社］で働いている。",
        "テープ": "この箱は［テープ］でしっかり閉じてある。",
        "年": "大学を卒業してから、もう三［年］が過ぎた。",
        "酸っぱい": "このみかんは少し［酸っぱい］。",
        "難しい": "この説明は少し［難しい］が、読み直せば分かる。",
        "美容院": "妹は駅前の［美容院］で髪を切った。",
        "仲間": "同じ目標を持つ［仲間］がいると心強い。",
        "田舎": "祖父母は［田舎］で静かに暮らしている。",
        "本当": "その話は［本当］ですか。",
        "得る": "努力を続ければ、大きな結果を［得る］こともある。",
        "随分": "今日は昨日より［随分］暖かい。",
        "間違う": "地図を急いで見ると、道を［間違う］ことがある。",
        "着く": "電車が遅れたが、会場には時間どおりに［着く］ことができた。",
        "泣く": "転んだ子どもが急に［泣く］出した。",
        "煩い": "隣の工事の音が朝から［煩い］。",
        "上": "棚の［上］に古い箱が置いてある。",
        "能力": "彼女は外国語を学ぶ［能力］が高い。",
        "看板": "店の前に大きな［看板］が出ていた。",
        "名所旧跡": "京都には有名な［名所旧跡］が多い。",
        "思い": "家族への［思い］を手紙に書いた。",
        "時間": "出発まであと少し［時間］がある。",
        "教科書": "授業の前に［教科書］を机の上に出した。",
        "表情": "彼の［表情］を見て、少し安心した。",
        "生む": "新しい工夫が大きな利益を［生む］こともある。",
        "この間": "［この間］会った店員を、駅前でまた見かけた。",
        "向こう": "川の［向こう］に小さな駅が見える。",
        "～以内": "資料は三日［～以内］に提出してください。",
    }
    if term in custom_sentences:
        return custom_sentences[term]
    if "接尾" in pos or "～" in term or "〜" in term:
        return f"{background['actor']}は、{background['time']}に{background['place']}で見た案内に、［{term}］という表現が使われているのに気づいた。"
    if "副" in pos:
        return f"{background['actor']}は、{background['time']}の予定について話し合い、「［{term}］大丈夫だろう」と言った。"
    if "名" in pos:
        return f"{background['actor']}は、{background['time']}に{background['place']}で［{term}］についての案内を読んでいた。"
    if "他动" in pos:
        object_term = background["object"]
        if any(token in item_text for token in ("招", "邀请", "招待")):
            object_term = "客"
        elif any(token in item_text for token in ("飼", "饲养")):
            object_term = "犬"
        elif any(token in item_text for token in ("嗅", "闻")):
            object_term = "花"
        elif any(token in item_text for token in ("変", "更换", "改变")):
            object_term = "予定"
        return f"{background['actor']}は、{background['time']}に{background['place']}で{object_term}を［{term}］ことにした。"
    if "自动" in pos or "自他动" in pos or "動" in pos:
        if any(token in item_text for token in ("行", "去", "向")):
            return f"{background['actor']}は、{background['time']}に{background['place']}から会場へ［{term}］ことにした。"
        subject = background["subject"]
        if any(token in item_text for token in ("閉", "关")):
            subject = "店の入口"
        elif any(token in item_text for token in ("折", "折断")):
            subject = "枝"
        elif any(token in item_text for token in ("でき上", "完成")):
            subject = "料理"
        elif any(token in item_text for token in ("優", "优秀", "出色")):
            return f"{background['place']}では、［{term}］人が集まることもある。"
        return f"{background['time']}になると、{background['place']}では{subject}が［{term}］ことがある。"
    if "形" in pos and "动" not in pos and "動" not in pos:
        return f"{background['place']}で買った{background['object']}は［{term}］ので、皆に好評だった。"
    return f"{background['actor']}は、{background['time']}に{background['place']}で［{term}］のことを気にしていた。"


def is_noun_like(item: sqlite3.Row) -> bool:
    pos = (item["pos"] or "").strip()
    if not pos:
        return True
    return "名" in pos or "サ変" in pos


def clean_grammar_example(example: str) -> str:
    value = (example or "").replace("│", " ").replace("｜", " ").strip()
    if "||" in value:
        value = value.split("||", 1)[0].strip()
    if len(value) > 80:
        value = value[:80].rstrip()
    return value


def looks_school_themed(text: str) -> bool:
    return any(token in (text or "") for token in ("先生", "授業", "勉強", "復習", "試験", "学生", "単語", "文章"))


def usable_grammar_item(item: sqlite3.Row) -> bool:
    pattern = (item["pattern"] or "").strip()
    if not pattern:
        return False
    if any(token in pattern for token in ("附录", "功能", "例句", "語法表")):
        return False
    if "。" in pattern or "||" in pattern:
        return False
    if len(pattern) > 24:
        return False
    if "/" in pattern and "〜" not in pattern and "～" not in pattern:
        return False
    return True


def allocate_session_section_counts(total_questions: int) -> dict[str, int]:
    floors = {"文字と語彙": 6, "文法": 6, "読解": 6, "和文中訳": 2}
    minimum_total = sum(floors.values())
    if total_questions <= minimum_total:
        counts = {"文字と語彙": 0, "文法": 0, "読解": 0, "和文中訳": 0}
        remaining = total_questions
        for section in ("文字と語彙", "文法", "読解", "和文中訳"):
            take = min(floors[section], remaining)
            counts[section] = take
            remaining -= take
        return counts

    max_reading = max(floors["読解"], total_questions - (floors["文字と語彙"] + floors["文法"] + floors["和文中訳"]))
    reading_blocks = max(2, int(round((total_questions * 0.30) / 3.0)))
    reading_blocks = min(max_reading // 3, reading_blocks)
    counts = {
        "読解": max(floors["読解"], reading_blocks * 3),
        "文字と語彙": floors["文字と語彙"],
        "文法": floors["文法"],
        "和文中訳": floors["和文中訳"],
    }

    remaining = total_questions - sum(counts.values())
    weights = [("文字と語彙", 0.5), ("文法", 0.3), ("和文中訳", 0.2)]
    while remaining > 0:
        progressed = False
        for section, _ in weights:
            if remaining <= 0:
                break
            counts[section] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            break
    return counts

def scripted_question_generation_disabled() -> NoReturn:
    raise RuntimeError(
        "脚本生题已停用。当前项目只允许：select_session_content -> "
        "extract_background_candidates -> agent/AI编写整套题 -> persist_authored_session。"
    )


def vocab_choice_question(item: sqlite3.Row, all_vocab: list[sqlite3.Row], rng: random.Random) -> dict[str, Any]:
    scripted_question_generation_disabled()


def grammar_choice_question(item: sqlite3.Row, all_grammar: list[sqlite3.Row], rng: random.Random) -> dict[str, Any]:
    scripted_question_generation_disabled()


def reading_question(vocab_item: sqlite3.Row, grammar_item: sqlite3.Row, rng: random.Random) -> dict[str, Any]:
    scripted_question_generation_disabled()


def listening_text_question(vocab_item: sqlite3.Row, grammar_item: sqlite3.Row, rng: random.Random) -> dict[str, Any]:
    scripted_question_generation_disabled()


def translation_choice_question(grammar_item: sqlite3.Row, rng: random.Random) -> dict[str, Any]:
    scripted_question_generation_disabled()


def reading_block_questions(
    vocab_items: list[sqlite3.Row],
    grammar_item: sqlite3.Row | None,
    all_vocab: list[sqlite3.Row],
    rng: random.Random,
) -> list[dict[str, Any]]:
    scripted_question_generation_disabled()


def build_questions(
    conn: sqlite3.Connection,
    session_day: str,
    target_minutes: int,
    max_questions: int,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    scripted_question_generation_disabled()


def serialize_vocab_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "term": row["term"],
        "reading": row["reading"],
        "meaning": row["meaning"],
        "pos": row["pos"],
        "source_scope": row["source_scope"],
        "status_label": row["status_label"],
        "mastery_score": row["mastery_score"],
        "next_due_at": row["next_due_at"],
    }


def serialize_grammar_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "pattern": row["pattern"],
        "meaning_cn": row["meaning_cn"],
        "core_usage": row["core_usage"],
        "example": clean_grammar_example(row["example"] or ""),
        "source_scope": row["source_scope"],
        "status_label": row["status_label"],
        "mastery_score": row["mastery_score"],
        "next_due_at": row["next_due_at"],
    }


def build_session_selection(
    conn: sqlite3.Connection,
    session_day: str,
    target_minutes: int,
    max_questions: int,
) -> dict[str, Any]:
    pool = get_study_pool(conn, session_day)
    requirements = daily_coverage_requirements(pool)
    recent_constraints = recent_question_constraints(conn)
    target_count = estimate_target_count(pool, target_minutes, max_questions)
    section_counts = allocate_session_section_counts(target_count)
    seed_value = int(hashlib.sha1(f"{session_day}-selection".encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed_value)
    vocab_round_robin = interleave_row_groups(
        [
            dedupe_rows(pool["user_due_vocab"]),
            dedupe_rows(pool["user_new_vocab"]),
            dedupe_rows(pool["user_review_vocab"]),
            dedupe_rows(pool["user_mastered_vocab"]),
        ]
    )
    grammar_round_robin = interleave_row_groups(
        [
            dedupe_rows(pool["user_due_grammar"]),
            dedupe_rows(pool["user_new_grammar"]),
            dedupe_rows(pool["user_review_grammar"]),
            dedupe_rows(pool["user_mastered_grammar"]),
        ]
    )
    vocab_primary, vocab_recent_holdout = prioritize_with_recent_holdout(
        dedupe_rows(vocab_round_robin),
        recent_constraints["recent_vocab_ids"],
    )
    grammar_primary, grammar_recent_holdout = prioritize_with_recent_holdout(
        dedupe_rows(grammar_round_robin),
        recent_constraints["recent_grammar_ids"],
    )
    grammar_official = dedupe_rows(pool["official_support_grammar"])
    grammar_official_fresh, grammar_official_holdout = prioritize_with_recent_holdout(
        grammar_official,
        recent_constraints["recent_grammar_ids"],
    )
    grammar_support = [row for row in dedupe_rows(grammar_primary + grammar_official_fresh + grammar_official_holdout) if usable_grammar_item(row)]
    grammar_official_usable = [row for row in grammar_official_fresh if usable_grammar_item(row)]
    grammar_recommended = [row for row in dedupe_rows(grammar_primary + grammar_official_usable) if usable_grammar_item(row)]
    noun_vocab_primary = [row for row in vocab_primary if is_noun_like(row)]
    scenario_pool = dedupe_rows(vocab_primary + pool["official_support_vocab"])
    reading_bundles: list[dict[str, Any]] = []
    grammar_index = 0
    if grammar_support:
        for offset in range(0, min(len(noun_vocab_primary), 9), 3):
            bundle = noun_vocab_primary[offset : offset + 3]
            if len(bundle) < 3:
                break
            grammar_item = grammar_support[grammar_index % len(grammar_support)]
            grammar_index += 1
            reading_bundles.append(
                {
                    "vocab": [serialize_vocab_item(row) for row in bundle],
                    "grammar": serialize_grammar_item(grammar_item),
                    "background": serialize_background_candidate(build_background_scenario(bundle, rng, focus_item=bundle[0])),
                }
            )
    return {
        "session_day": session_day,
        "target_minutes": target_minutes,
        "target_questions": target_count,
        "question_budget": {
            "max_questions": max_questions,
            "sizing_rule": "覆盖优先；当新学、到期复习、错题回流压力较大时，题量可主动上调，但单日不超过100题。",
            "minimum_targets": {
                "new_vocab": requirements["new_vocab_target"],
                "review_vocab": requirements["review_vocab_target"],
                "grammar": requirements["grammar_target"],
                "counting_rule": requirements["counting_rule"],
            },
            "coverage_snapshot": {
                "today_new_vocab": len(pool["new_vocab"]),
                "due_vocab": len(pool["due_vocab"]),
                "active_review_vocab": len(pool["user_review_vocab"]),
                "today_new_grammar": len(pool["new_grammar"]),
                "due_grammar": len(pool["due_grammar"]),
                "active_review_grammar": len(pool["user_review_grammar"]),
                "mistakes": len(pool["mistakes"]),
            },
        },
        "recommended_section_counts": section_counts,
        "selection_policy": {
            "core": "当天新学 + 到期复习 + 复习中/已掌握用户内容优先，官方内容仅作语法和题型兜底",
            "question_author": "ai_skill",
            "selector": "script",
            "rotation": "低熟练优先，但在当天新学、到期复习、复习中、已掌握之间轮转取材，避免只盯着同一小撮内容。",
            "coverage_rule": "当复习压力高时，优先增加题量和综合题密度，而不是机械维持20或24题。",
            "recent_repeat_rule": "近3题已正式出过的词汇和语法默认进入 holdout，本轮不优先再出；只有当材料不足时才回退使用。",
            "unused_return_rule": "AI 最终未采用的候选内容不会写入 questions，因此不会记入重复历史，下一轮仍可继续参与抽取。",
        },
        "authoring_constraints": {
            "avoid_recent_vocab_ids": sorted(recent_constraints["recent_vocab_ids"]),
            "avoid_recent_grammar_ids": sorted(recent_constraints["recent_grammar_ids"]),
            "avoid_recent_terms": recent_constraints["recent_terms"],
            "avoid_recent_patterns": recent_constraints["recent_patterns"],
            "recent_question_types": recent_constraints["recent_question_types"],
            "blocked_question_types": recent_constraints["blocked_question_types"],
            "current_question_type_streak": recent_constraints["current_question_type_streak"],
            "question_type_rule": "同一 question_type 不应连续出现 5 次；若 blocked_question_types 非空，本轮优先换题型。",
            "required_new_vocab_ids": requirements["required_new_vocab_ids"],
            "required_review_vocab_ids": requirements["required_review_vocab_ids"],
            "required_grammar_ids": requirements["required_grammar_ids"],
            "coverage_hard_rule": "当天新词必须全部覆盖；语法至少覆盖10个；旧词复习至少覆盖当天到期词的50%，且当天到期达到50个时不少于50个；若当天到期不足50个则尽量全覆盖。只要知识点出现在正式题目的 knowledge_tags 中，就算已覆盖；简单复习词在题面自然出现且有正确 knowledge_tags 也算覆盖。",
        },
        "vocab": {
            "today_new": [serialize_vocab_item(row) for row in pool["user_new_vocab"][: max(20, requirements["new_vocab_target"])]],
            "due_review": [serialize_vocab_item(row) for row in pool["user_due_vocab"][: min(len(pool["user_due_vocab"]), max(60, requirements["review_vocab_target"] + 10))]],
            "active_review": [serialize_vocab_item(row) for row in pool["user_review_vocab"][:40]],
            "mastered_background": [serialize_vocab_item(row) for row in pool["user_mastered_vocab"][:20]],
            "official_support": [serialize_vocab_item(row) for row in pool["official_support_vocab"][:20]],
            "recommended": [serialize_vocab_item(row) for row in vocab_primary[: max(24, requirements["new_vocab_target"] + requirements["review_vocab_target"])]],
            "recent_holdout": [serialize_vocab_item(row) for row in vocab_recent_holdout[:12]],
        },
        "grammar": {
            "today_new": [serialize_grammar_item(row) for row in pool["user_new_grammar"][:10]],
            "due_review": [serialize_grammar_item(row) for row in pool["user_due_grammar"][:10]],
            "active_review": [serialize_grammar_item(row) for row in pool["user_review_grammar"][:10]],
            "mastered_background": [serialize_grammar_item(row) for row in pool["user_mastered_grammar"][:10]],
            "official_support": [serialize_grammar_item(row) for row in grammar_official_usable[:15]],
            "recommended": [serialize_grammar_item(row) for row in grammar_recommended[: max(16, requirements["grammar_target"])]],
            "recent_holdout": [serialize_grammar_item(row) for row in dedupe_rows(grammar_recent_holdout + grammar_official_holdout)[:8]],
        },
        "background_candidates": build_background_candidates(scenario_pool, rng, max_items=6),
        "reading_bundles": reading_bundles,
    }


def allocate_mock_section_counts(total_questions: int) -> dict[str, int]:
    blueprint_path = ROOT / "data" / "kb" / "cjt4" / "mock_blueprints.json"
    blueprint = {
        "听力（文字版）": 0.15,
        "文字与词语": 0.15,
        "语法": 0.20,
        "阅读": 0.30,
        "翻译与写作": 0.20,
    }
    if blueprint_path.exists():
        try:
            rows = json.loads(blueprint_path.read_text(encoding="utf-8"))
            if rows and isinstance(rows[0].get("sections"), dict):
                blueprint = rows[0]["sections"]
        except (json.JSONDecodeError, OSError):
            pass
    counts: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    allocated = 0
    for section, ratio in blueprint.items():
        exact = total_questions * ratio
        count = max(1, int(exact))
        counts[section] = count
        allocated += count
        remainders.append((exact - int(exact), section))
    while allocated < total_questions:
        remainders.sort(reverse=True)
        for _, section in remainders:
            if allocated >= total_questions:
                break
            counts[section] += 1
            allocated += 1
    while allocated > total_questions:
        removable = [section for section, count in counts.items() if count > 1]
        if not removable:
            break
        section = max(removable, key=lambda item: counts[item])
        counts[section] -= 1
        allocated -= 1
    return counts


def build_mock_paper(
    conn: sqlite3.Connection,
    paper_day: str,
    target_minutes: int,
    max_questions: int,
    title: str | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, int]]:
    scripted_question_generation_disabled()


def persist_session(
    conn: sqlite3.Connection,
    session_id: str,
    session_day: str,
    target_minutes: int,
    questions: list[dict[str, Any]],
    summary: dict[str, Any],
    record_kind: str = "actual",
    ) -> None:
    stamp = ts()
    conn.execute(
        """
        INSERT INTO sessions (
            id, session_date, status, target_minutes, question_count, source_summary,
            record_kind, started_at, created_at, updated_at
        )
        VALUES (?, ?, 'generated', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            session_day,
            target_minutes,
            len(questions),
            json.dumps(summary, ensure_ascii=False),
            record_kind,
            stamp,
            stamp,
            stamp,
        ),
    )
    for idx, question in enumerate(questions, start=1):
        conn.execute(
            """
            INSERT INTO questions (
                session_id, ordinal, section_name, question_type, difficulty, prompt, answer,
                explanation, knowledge_tags, is_new_knowledge, source_scope, record_kind, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                idx,
                question["section_name"],
                question["question_type"],
                question["difficulty"],
                question["prompt"],
                question["answer"],
                question["explanation"],
                json.dumps(question["knowledge_tags"], ensure_ascii=False),
                question["is_new_knowledge"],
                question["source_scope"],
                record_kind,
                stamp,
                stamp,
            ),
        )
    conn.commit()


def supersede_older_pending_sessions(
    conn: sqlite3.Connection,
    session_day: str,
    keep_session_id: str,
    record_kind: str = "actual",
) -> list[str]:
    rows = fetch_rows(
        conn,
        """
        SELECT s.id
        FROM sessions s
        JOIN (
            SELECT session_id, SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count
            FROM questions
            GROUP BY session_id
        ) q ON q.session_id = s.id
        WHERE s.session_date = ?
          AND COALESCE(s.record_kind, 'actual') = ?
          AND s.id <> ?
          AND COALESCE(s.status, 'generated') NOT IN ('completed', 'superseded')
          AND q.pending_count > 0
        ORDER BY s.created_at ASC, s.id ASC
        """,
        (session_day, record_kind, keep_session_id),
    )
    if not rows:
        return []
    stamp = ts()
    ids = [row["id"] for row in rows]
    for session_id in ids:
        conn.execute(
            "UPDATE sessions SET status = 'superseded', updated_at = ? WHERE id = ?",
            (stamp, session_id),
        )
    conn.commit()
    return ids


def authored_session_summary(
    session_day: str,
    target_minutes: int,
    questions: list[dict[str, Any]],
    raw_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = dict(raw_summary or {})
    defaults = {
        "session_day": session_day,
        "target_minutes": target_minutes,
        "question_target": len(questions),
        "question_actual": len(questions),
        "new_vocab": 0,
        "due_vocab": 0,
        "new_grammar": 0,
        "due_grammar": 0,
        "mistakes": 0,
        "user_vocab_primary": 0,
        "user_grammar_primary": 0,
        "official_vocab_support": 0,
        "official_grammar_support": 0,
        "author_mode": "ai_authored",
    }
    for key, value in defaults.items():
        summary.setdefault(key, value)
    return summary


def validate_authored_question(question: dict[str, Any]) -> dict[str, Any]:
    normalized_prompt, normalized_answer = shuffle_authored_prompt_options(
        question["prompt"],
        str(question["answer"]).strip(),
    )
    normalized = {
        "section_name": question["section_name"],
        "question_type": question["question_type"],
        "difficulty": int(question.get("difficulty", 2)),
        "prompt": normalized_prompt,
        "answer": normalized_answer,
        "explanation": question["explanation"],
        "knowledge_tags": question.get("knowledge_tags", []),
        "is_new_knowledge": int(question.get("is_new_knowledge", 0)),
        "source_scope": question.get("source_scope", "mixed"),
    }
    if not normalized["answer"]:
        raise ValueError("Authored question answer cannot be empty.")
    if not isinstance(normalized["knowledge_tags"], list):
        raise ValueError("Authored question knowledge_tags must be a list.")
    return normalized


def diary_path_for_day(session_day: str) -> Path:
    return DIARY_DIR / f"{session_day}.md"


def safe_session_summary(session: sqlite3.Row) -> dict[str, Any]:
    raw = (session["source_summary"] or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def question_id_span(questions: list[sqlite3.Row]) -> str:
    ids = [int(question["id"]) for question in questions]
    if not ids:
        return "无"
    if min(ids) == max(ids):
        return str(ids[0])
    return f"{min(ids)}~{max(ids)}"


def compact_section_counts(questions: list[sqlite3.Row]) -> str:
    counts: dict[str, int] = {}
    for question in questions:
        label = str(question["section_name"] or "未分类")
        counts[label] = counts.get(label, 0) + 1
    return "、".join(f"{label} {count}" for label, count in counts.items()) or "无"


def compact_status_counts(questions: list[sqlite3.Row]) -> str:
    order = ["pending", "correct", "wrong", "invalid"]
    counts: dict[str, int] = {}
    for question in questions:
        label = str(question["status"] or "pending")
        counts[label] = counts.get(label, 0) + 1
    parts = [f"{label} {counts[label]}" for label in order if counts.get(label)]
    parts.extend(f"{label} {count}" for label, count in counts.items() if label not in order)
    return "、".join(parts) or "无"


def compact_knowledge_labels(question: sqlite3.Row) -> str:
    labels: list[str] = []
    for tag in parse_knowledge_tags(question["knowledge_tags"]):
        label = str(tag.get("term") or tag.get("pattern") or tag.get("id") or "").strip()
        if label and label not in labels:
            labels.append(label)
    return "、".join(labels) or "无"


def session_diary_lines(
    session: sqlite3.Row,
    session_questions: list[sqlite3.Row],
    used_questions: list[sqlite3.Row],
    attempts_by_question: dict[int, list[sqlite3.Row]],
) -> list[str]:
    summary = safe_session_summary(session)
    display_start = summary.get("display_start_ordinal")
    display_total = summary.get("display_total_questions")
    lines = [
        f"## 会话 {session['id']}",
        "",
        f"- 记录类型：{display_record_kind(session['record_kind'])}",
        f"- 生成时间：{session['created_at']}",
        f"- 会话状态：{session['status']}",
        f"- 目标时长：{session['target_minutes']} 分钟",
        f"- 题目数量：{session['question_count']}",
        f"- 实际使用题数：{len(used_questions)}",
        f"- 题目事实来源：{DB_PATH}",
        f"- 题目ID范围：{question_id_span(used_questions)}",
        f"- 题型分布：{compact_section_counts(used_questions)}",
        f"- 状态分布：{compact_status_counts(used_questions)}",
        f"- 新词：{summary.get('new_vocab', 0)}，到期词汇：{summary.get('due_vocab', 0)}，新语法：{summary.get('new_grammar', 0)}，到期语法：{summary.get('due_grammar', 0)}，错题回流：{summary.get('mistakes', 0)}",
        "",
        "### 实际使用题目",
        "",
    ]
    if display_start and display_total:
        end_ordinal = int(display_start) + max(len(session_questions) - 1, 0)
        lines.append(f"- 展示题号范围：第 {display_start} 题 ~ 第 {end_ordinal} 题 / 共 {display_total} 题")
    if not used_questions:
        lines.extend(
            [
                "- 本会话暂无实际使用题目；未展示或未作答的生成题目不写入习题日记正文。",
                "",
            ]
        )
        return lines
    lines.extend(
        [
            "- 日记正文只保留实际使用过的题目；未展示、未作答或被后续会话污染的残留题目不在这里展开。",
            "",
        ]
    )
    for question in used_questions:
        attempts = attempts_by_question.get(int(question["id"]), [])
        lines.extend(
            [
                f"#### 第 {question['ordinal']} 题｜question_id={question['id']}｜{question['section_name']}｜难度 {question['difficulty']}",
                "",
                question["prompt"],
                "",
                f"- 正确答案：{question['answer']}",
                f"- 解析：{question['explanation']}",
                f"- 知识点：{compact_knowledge_labels(question)}",
                f"- 新知识：{'是' if question['is_new_knowledge'] else '否'}",
                f"- 最终状态：{question['status']}",
                f"- 作答次数：{len(attempts)}",
                "",
            ]
        )
        for idx, attempt in enumerate(attempts, start=1):
            lines.extend(
                [
                    f"##### 作答 {idx}｜{attempt['answered_at']}",
                    "",
                    attempt["feedback_summary"],
                    "",
                ]
            )
    return lines


def build_day_diary(conn: sqlite3.Connection, session_day: str, record_kind: str = "actual") -> str:
    sessions = fetch_rows(
        conn,
        """
        SELECT *
        FROM sessions
        WHERE session_date = ? AND COALESCE(record_kind, 'actual') = ?
        ORDER BY created_at ASC, id ASC
        """,
        (session_day, record_kind),
    )
    lines = [f"# {session_day} 习题日记", ""]
    if not sessions:
        lines.extend(["- 暂无正式会话记录。", ""])
        return "\n".join(lines).strip() + "\n"

    rendered_sessions = 0
    skipped_sessions: list[str] = []
    for session in sessions:
        session_questions = fetch_rows(
            conn,
            "SELECT * FROM questions WHERE session_id = ? ORDER BY ordinal ASC, id ASC",
            (session["id"],),
        )
        attempt_rows = fetch_rows(
            conn,
            """
            SELECT a.*, q.id AS question_id, q.ordinal, q.section_name, q.status AS question_status
            FROM attempts a
            JOIN questions q ON q.id = a.question_id
            WHERE q.session_id = ?
            ORDER BY a.answered_at ASC, a.id ASC
            """,
            (session["id"],),
        )
        attempts_by_question: dict[int, list[sqlite3.Row]] = {}
        for attempt in attempt_rows:
            attempts_by_question.setdefault(int(attempt["question_id"]), []).append(attempt)
        used_question_ids = [int(attempt["question_id"]) for attempt in attempt_rows]
        used_questions = [question for question in session_questions if int(question["id"]) in used_question_ids]
        if not used_questions:
            skipped_sessions.append(str(session["id"]))
            continue
        lines.extend(session_diary_lines(session, session_questions, used_questions, attempts_by_question))
        rendered_sessions += 1
        if rendered_sessions < len(sessions) - len(skipped_sessions):
            lines.append("")
    if skipped_sessions:
        lines.insert(2, f"- 已跳过 {len(skipped_sessions)} 个未实际使用题目的会话：{'、'.join(skipped_sessions)}。")
        lines.insert(3, "")
    return "\n".join(lines).strip() + "\n"


def write_session_diary(conn: sqlite3.Connection, session_id: str) -> Path:
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    day_path = diary_path_for_day(session["session_date"])
    day_path.write_text(build_day_diary(conn, session["session_date"], record_kind="actual"), encoding="utf-8")
    return day_path


def rebuild_day_diary(conn: sqlite3.Connection, session_day: str, record_kind: str = "actual") -> Path:
    path = diary_path_for_day(session_day)
    path.write_text(build_day_diary(conn, session_day, record_kind=record_kind), encoding="utf-8")
    return path


def daily_summary_path_for_day(session_day: str) -> Path:
    return SUMMARY_DIR / f"{session_day}-当日总结.md"


def persist_mock_paper(
    conn: sqlite3.Connection,
    paper_id: str,
    paper_day: str,
    title: str,
    target_minutes: int,
    questions: list[dict[str, Any]],
    summary: dict[str, Any],
    section_counts: dict[str, int],
) -> None:
    stamp = ts()
    conn.execute(
        """
        INSERT INTO mock_papers (id, title, paper_date, level, target_minutes, question_count, blueprint_json, source_summary, status, created_at, updated_at)
        VALUES (?, ?, ?, 'exam', ?, ?, ?, ?, 'generated', ?, ?)
        """,
        (
            paper_id,
            title,
            paper_day,
            target_minutes,
            len(questions),
            json.dumps(section_counts, ensure_ascii=False),
            json.dumps(summary, ensure_ascii=False),
            stamp,
            stamp,
        ),
    )
    for idx, question in enumerate(questions, start=1):
        conn.execute(
            """
            INSERT INTO mock_paper_questions (
                paper_id, ordinal, section_name, question_type, difficulty, prompt, answer,
                explanation, knowledge_tags, is_new_knowledge, source_scope, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                idx,
                question["section_name"],
                question["question_type"],
                question["difficulty"],
                question["prompt"],
                question["answer"],
                question["explanation"],
                json.dumps(question["knowledge_tags"], ensure_ascii=False),
                question["is_new_knowledge"],
                question["source_scope"],
                record_kind,
                stamp,
                stamp,
            ),
        )
    conn.commit()


def append_diary_attempt(conn: sqlite3.Connection, question_id: int, feedback: str) -> Path:
    question = conn.execute(
        """
        SELECT q.*, s.session_date, s.record_kind
        FROM questions q
        JOIN sessions s ON s.id = q.session_id
        WHERE q.id = ?
        """,
        (question_id,),
    ).fetchone()
    path = diary_path_for_day(question["session_date"])
    record_kind = (question["record_kind"] or "actual").strip().lower()
    if record_kind == "actual":
        path.write_text(build_day_diary(conn, question["session_date"], record_kind="actual"), encoding="utf-8")
    return path


def session_completed(conn: sqlite3.Connection, session_id: str) -> bool:
    pending = conn.execute(
        "SELECT COUNT(*) FROM questions WHERE session_id = ? AND status = 'pending'",
        (session_id,),
    ).fetchone()[0]
    return pending == 0


def refresh_session_status(conn: sqlite3.Connection, session_id: str) -> str:
    session = conn.execute("SELECT status, created_at, started_at FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        raise ValueError(f"Session {session_id} not found.")
    current_status = (session["status"] or "generated").strip().lower()
    if current_status == "superseded":
        return "superseded"
    counts = conn.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count
        FROM questions
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    total = int(counts["total_count"] or 0)
    pending = int(counts["pending_count"] or 0)
    if total == 0 or pending == total:
        new_status = "generated"
    elif pending == 0:
        new_status = "completed"
    else:
        new_status = "in_progress"
    stamp = ts()
    completed_at = stamp if new_status == "completed" else None
    conn.execute(
        """
        UPDATE sessions
        SET status = ?,
            started_at = COALESCE(started_at, created_at, ?),
            completed_at = CASE
                WHEN ? = 'completed' THEN COALESCE(completed_at, ?)
                ELSE completed_at
            END,
            updated_at = ?
        WHERE id = ?
        """,
        (new_status, stamp, new_status, completed_at, stamp, session_id),
    )
    return new_status


def next_pending_question_row(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, ordinal, section_name, question_type, difficulty, prompt, status
        FROM questions
        WHERE session_id = ? AND status = 'pending'
        ORDER BY ordinal ASC, id ASC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()


def session_status_payload(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        raise ValueError(f"Session {session_id} not found.")
    refresh_session_status(conn, session_id)
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    counts = conn.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
            SUM(CASE WHEN status = 'correct' THEN 1 ELSE 0 END) AS correct_count,
            SUM(CASE WHEN status = 'wrong' THEN 1 ELSE 0 END) AS wrong_count
        FROM questions
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    total = int(counts["total_count"] or 0)
    pending = int(counts["pending_count"] or 0)
    correct = int(counts["correct_count"] or 0)
    wrong = int(counts["wrong_count"] or 0)
    summary = json.loads(session["source_summary"] or "{}")
    next_question = next_pending_question_row(conn, session_id)
    return {
        "session_id": session_id,
        "session_date": session["session_date"],
        "record_kind": session["record_kind"],
        "status": session["status"],
        "started_at": session["started_at"],
        "completed_at": session["completed_at"],
        "post_review_synced_at": session["post_review_synced_at"],
        "target_minutes": session["target_minutes"],
        "question_count": total,
        "answered_count": correct + wrong,
        "pending_count": pending,
        "correct_count": correct,
        "wrong_count": wrong,
        "summary": summary,
        "next_question": dict(next_question) if next_question else None,
    }


def find_active_session(
    conn: sqlite3.Connection,
    session_day: str,
    record_kind: str = "actual",
    include_completed: bool = False,
) -> sqlite3.Row | None:
    rows = fetch_rows(
        conn,
        """
        SELECT
            s.*,
            SUM(CASE WHEN q.status = 'pending' THEN 1 ELSE 0 END) AS pending_count
        FROM sessions s
        LEFT JOIN questions q ON q.session_id = s.id
        WHERE s.session_date = ?
          AND COALESCE(s.record_kind, 'actual') = ?
          AND COALESCE(s.status, 'generated') <> 'superseded'
        GROUP BY s.id
        ORDER BY
            CASE WHEN SUM(CASE WHEN q.status = 'pending' THEN 1 ELSE 0 END) > 0 THEN 0 ELSE 1 END,
            s.created_at DESC,
            s.id DESC
        """,
        (session_day, record_kind),
    )
    if include_completed:
        return rows[0] if rows else None
    for row in rows:
        if int(row["pending_count"] or 0) > 0:
            return row
    return None


def build_daily_summary(conn: sqlite3.Connection, session_day: str) -> str:
    session_rows = fetch_rows(
        conn,
        """
        SELECT id, status, question_count, completed_at
        FROM sessions
        WHERE session_date = ? AND COALESCE(record_kind, 'actual') = 'actual'
        ORDER BY created_at ASC, id ASC
        """,
        (session_day,),
    )
    attempts = fetch_rows(
        conn,
        """
        SELECT q.section_name, q.knowledge_tags, a.is_correct
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        JOIN sessions s ON s.id = q.session_id
        WHERE s.session_date = ? AND COALESCE(s.record_kind, 'actual') = 'actual'
        ORDER BY a.id ASC
        """,
        (session_day,),
    )
    total = len(attempts)
    correct = sum(int(row["is_correct"]) for row in attempts)
    accuracy = round(correct * 100.0 / total, 2) if total else 0.0
    wrong_sections: dict[str, int] = {}
    weak_tags: dict[str, int] = {}
    for row in attempts:
        if row["is_correct"]:
            continue
        wrong_sections[row["section_name"]] = wrong_sections.get(row["section_name"], 0) + 1
        for tag in json.loads(row["knowledge_tags"]):
            label = tag.get("term") or tag.get("pattern") or str(tag.get("id"))
            weak_tags[label] = weak_tags.get(label, 0) + 1
    top_sections = "、".join(
        f"{name} {count} 题" for name, count in sorted(wrong_sections.items(), key=lambda item: item[1], reverse=True)[:3]
    ) or "整体还算稳，没有明显翻车区。"
    top_tags = "、".join(
        f"{name}({count})" for name, count in sorted(weak_tags.items(), key=lambda item: item[1], reverse=True)[:5]
    ) or "暂无集中薄弱词法。"
    completed_sessions = [row for row in session_rows if str(row["status"] or "") == "completed"]
    active_sessions = [row for row in session_rows if str(row["status"] or "") not in {"completed", "superseded"}]
    session_summary = "、".join(f"{row['id']}({row['status']})" for row in session_rows) or "无正式会话。"
    return "\n".join(
        [
            "## 当日总结",
            "",
            f"- 日期：{session_day}",
            f"- 完成时间：{ts()}",
            f"- 正式会话数：{len(session_rows)}",
            f"- 已完成会话：{len(completed_sessions)}",
            f"- 仍未收口会话：{len(active_sessions)}",
            f"- 当日作答题量：{total}",
            f"- 正确题数：{correct}",
            f"- 正确率：{accuracy}%",
            f"- 易错题型：{top_sections}",
            f"- 重点回看：{top_tags}",
            f"- 会话状态：{session_summary}",
            "- 建议：先把错题和重复出错的词法过一遍，明天别让同一个坑继续收门票。",
        ]
    )


def append_daily_summary_if_complete(conn: sqlite3.Connection, session_id: str) -> Path | None:
    if not session_completed(conn, session_id):
        return None
    reconcile_completed_session_learning(conn, session_id)
    session = conn.execute("SELECT session_date FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        return None
    session_day = session["session_date"]
    rebuild_day_diary(conn, session_day, record_kind="actual")
    active = find_active_session(conn, session_day, record_kind="actual", include_completed=False)
    if active:
        return None
    summary_path = daily_summary_path_for_day(session_day)
    summary_path.write_text(build_daily_summary(conn, session_day), encoding="utf-8")
    return summary_path


def session_knowledge_attempts(conn: sqlite3.Connection, session_id: str) -> dict[tuple[str, int], dict[str, Any]]:
    rows = fetch_rows(
        conn,
        """
        SELECT q.knowledge_tags, a.is_correct
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE q.session_id = ?
        ORDER BY a.id ASC
        """,
        (session_id,),
    )
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        for tag in parse_knowledge_tags(row["knowledge_tags"]):
            if tag.get("id") is None or tag.get("kind") not in {"vocab", "grammar"}:
                continue
            key = (str(tag["kind"]), int(tag["id"]))
            entry = result.setdefault(
                key,
                {
                    "kind": key[0],
                    "id": key[1],
                    "label": tag.get("term") or tag.get("pattern") or str(tag["id"]),
                    "seen": 0,
                    "correct": 0,
                    "wrong": 0,
                },
            )
            entry["seen"] += 1
            if int(row["is_correct"] or 0):
                entry["correct"] += 1
            else:
                entry["wrong"] += 1
    return result


def calibration_delta(seen: int, correct: int, wrong: int) -> int:
    if seen < 2:
        return 0
    accuracy = correct / seen
    delta = int(round((accuracy - 0.6) * seen * 4))
    if wrong >= 2:
        delta -= 1
    return max(-8, min(4, delta))


def reconcile_completed_session_learning(
    conn: sqlite3.Connection,
    session_id: str,
    force: bool = False,
) -> dict[str, Any]:
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        raise ValueError(f"Session {session_id} not found.")
    if not session_completed(conn, session_id):
        return {"session_id": session_id, "applied": False, "reason": "session_not_completed"}
    completed_at = parse_ts(session["completed_at"]) or parse_ts(session["updated_at"]) or now_local()
    synced_at = parse_ts(session["post_review_synced_at"])
    if not force and synced_at and synced_at >= completed_at:
        return {"session_id": session_id, "applied": False, "reason": "already_synced"}

    aggregates = session_knowledge_attempts(conn, session_id)
    stamp = ts()
    updated_items: list[dict[str, Any]] = []
    for payload in aggregates.values():
        delta = calibration_delta(payload["seen"], payload["correct"], payload["wrong"])
        if delta == 0 and payload["wrong"] == 0:
            continue
        table = "vocab_items" if payload["kind"] == "vocab" else "grammar_items"
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (payload["id"],)).fetchone()
        if not row:
            continue
        current_score = row["mastery_score"]
        if current_score is None and row["external_score"] is not None:
            current_score = row["external_score"]
        if current_score is None and row["proficiency"] is not None:
            current_score = int(row["proficiency"]) * 20
        if current_score is None:
            current_score = 50
        new_score = max(0, min(100, int(current_score) + delta))
        new_prof = score_to_proficiency(new_score) or 0
        existing_due = parse_ts(row["next_due_at"])
        if payload["wrong"] > 0:
            hours = 12 if payload["wrong"] >= 2 or payload["correct"] == 0 else 18
            candidate_due = completed_at + timedelta(hours=hours)
            if existing_due is None or existing_due > candidate_due:
                next_due = candidate_due
            else:
                next_due = existing_due
        elif payload["seen"] >= 2 and payload["correct"] == payload["seen"]:
            candidate_due = completed_at + timedelta(days=max(schedule_days(new_prof, True), min(21, payload["seen"] * 3)))
            if existing_due is None or existing_due < candidate_due:
                next_due = candidate_due
            else:
                next_due = existing_due
        else:
            next_due = existing_due or (completed_at + timedelta(days=schedule_days(new_prof, payload["wrong"] == 0)))
        conn.execute(
            f"""
            UPDATE {table}
            SET proficiency = ?,
                mastery_score = ?,
                next_due_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (new_prof, new_score, ts(next_due), stamp, payload["id"]),
        )
        updated_items.append(
            {
                "kind": payload["kind"],
                "id": payload["id"],
                "label": payload["label"],
                "seen": payload["seen"],
                "correct": payload["correct"],
                "wrong": payload["wrong"],
                "delta": delta,
                "mastery_score": new_score,
                "next_due_at": ts(next_due),
            }
        )
    conn.execute(
        "UPDATE sessions SET post_review_synced_at = ?, updated_at = ? WHERE id = ?",
        (stamp, stamp, session_id),
    )
    conn.commit()
    return {
        "session_id": session_id,
        "applied": True,
        "updated_count": len(updated_items),
        "items": updated_items,
    }


def refresh_day_session_statuses(
    conn: sqlite3.Connection,
    session_day: str,
    record_kind: str = "actual",
) -> dict[str, Any]:
    rows = fetch_rows(
        conn,
        """
        SELECT id, created_at
        FROM sessions
        WHERE session_date = ? AND COALESCE(record_kind, 'actual') = ?
        ORDER BY created_at ASC, id ASC
        """,
        (session_day, record_kind),
    )
    refreshed: list[str] = []
    for row in rows:
        refresh_session_status(conn, row["id"])
        refreshed.append(row["id"])
    keep = fetch_rows(
        conn,
        """
        SELECT id
        FROM sessions
        WHERE session_date = ?
          AND COALESCE(record_kind, 'actual') = ?
          AND COALESCE(status, 'generated') <> 'superseded'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (session_day, record_kind),
    )
    superseded = supersede_older_pending_sessions(conn, session_day, keep[0]["id"], record_kind) if keep else []
    return {
        "session_day": session_day,
        "record_kind": record_kind,
        "refreshed_session_ids": refreshed,
        "superseded_session_ids": superseded,
    }


def audit_study_day(
    conn: sqlite3.Connection,
    session_day: str,
    record_kind: str = "actual",
) -> dict[str, Any]:
    session_rows = fetch_rows(
        conn,
        """
        SELECT
            s.*,
            SUM(CASE WHEN q.status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
            SUM(CASE WHEN q.status = 'correct' THEN 1 ELSE 0 END) AS correct_count,
            SUM(CASE WHEN q.status = 'wrong' THEN 1 ELSE 0 END) AS wrong_count,
            SUM(CASE WHEN q.status = 'invalid' THEN 1 ELSE 0 END) AS invalid_count
        FROM sessions s
        LEFT JOIN questions q ON q.session_id = s.id
        WHERE s.session_date = ? AND COALESCE(s.record_kind, 'actual') = ?
        GROUP BY s.id
        ORDER BY s.created_at ASC, s.id ASC
        """,
        (session_day, record_kind),
    )
    duplicate_attempt_rows = fetch_rows(
        conn,
        """
        SELECT q.session_id, q.id AS question_id, q.ordinal, COUNT(*) AS attempt_count
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        JOIN sessions s ON s.id = q.session_id
        WHERE s.session_date = ? AND COALESCE(s.record_kind, 'actual') = ?
        GROUP BY q.id
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC, q.id ASC
        """,
        (session_day, record_kind),
    )
    stale_pending: list[str] = []
    status_issues: list[dict[str, Any]] = []
    latest_created = max((row["created_at"] for row in session_rows), default="")
    for row in session_rows:
        pending = int(row["pending_count"] or 0)
        answered = int(row["correct_count"] or 0) + int(row["wrong_count"] or 0)
        status = (row["status"] or "generated").strip().lower()
        if status == "completed" and pending > 0:
            status_issues.append({"session_id": row["id"], "issue": "completed_with_pending"})
        if status == "generated" and answered > 0:
            status_issues.append({"session_id": row["id"], "issue": "generated_with_answers"})
        if status not in {"completed", "superseded"} and pending > 0 and row["created_at"] < latest_created:
            stale_pending.append(row["id"])

    active_session_ids = [row["id"] for row in session_rows if (row["status"] or "generated") != "superseded"]
    authored_vocab_ids: set[int] = set()
    authored_grammar_ids: set[int] = set()
    if active_session_ids:
        authored_rows = fetch_rows(
            conn,
            f"""
            SELECT knowledge_tags
            FROM questions
            WHERE session_id IN ({",".join("?" for _ in active_session_ids)})
              AND status <> 'invalid'
            """,
            tuple(active_session_ids),
        )
        authored_vocab_ids, authored_grammar_ids = collect_knowledge_ids_from_question_rows(authored_rows)

    used_rows = fetch_rows(
        conn,
        """
        SELECT DISTINCT q.id, q.knowledge_tags
        FROM questions q
        JOIN sessions s ON s.id = q.session_id
        JOIN attempts a ON a.question_id = q.id
        WHERE s.session_date = ?
          AND COALESCE(s.record_kind, 'actual') = ?
          AND q.status <> 'invalid'
        ORDER BY q.id ASC
        """,
        (session_day, record_kind),
    )
    used_vocab_ids, used_grammar_ids = collect_knowledge_ids_from_question_rows(used_rows)

    requirements: dict[str, Any] | None = None
    for row in reversed(session_rows):
        requirements = coverage_requirements_from_summary(safe_session_summary(row))
        if requirements:
            break
    if requirements is None:
        audit_stamp = day_end_stamp(session_day)
        requirements = daily_coverage_requirements(get_study_pool(conn, session_day, reference_stamp=audit_stamp))
    required_new_vocab_ids = set(requirements["required_new_vocab_ids"])
    required_review_vocab_ids = set(requirements["required_review_vocab_ids"])
    required_grammar_ids = set(requirements["required_grammar_ids"])
    today_new_vocab_ids = set(requirements.get("today_new_vocab_ids", [])) or {int(row["id"]) for row in fetch_day_new_vocab_rows(conn, session_day)}
    today_new_grammar_ids = set(requirements.get("today_new_grammar_ids", []))
    due_vocab_ids = set(requirements.get("due_vocab_ids", []))
    due_grammar_ids = set(requirements.get("due_grammar_ids", []))
    return {
        "session_day": session_day,
        "record_kind": record_kind,
        "session_count": len(session_rows),
        "sessions": [
            {
                "id": row["id"],
                "status": row["status"],
                "question_count": row["question_count"],
                "pending_count": int(row["pending_count"] or 0),
                "correct_count": int(row["correct_count"] or 0),
                "wrong_count": int(row["wrong_count"] or 0),
                "invalid_count": int(row["invalid_count"] or 0),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in session_rows
        ],
        "issues": {
            "stale_pending_session_ids": stale_pending,
            "status_issues": status_issues,
            "duplicate_attempts": [dict(row) for row in duplicate_attempt_rows],
            "invalid_question_count": sum(int(row["invalid_count"] or 0) for row in session_rows),
        },
        "coverage": {
            "counting_rule": requirements["counting_rule"],
            "authored_vocab_count": len(authored_vocab_ids),
            "authored_grammar_count": len(authored_grammar_ids),
            "used_vocab_count": len(used_vocab_ids),
            "used_grammar_count": len(used_grammar_ids),
            "today_new_vocab_total": len(required_new_vocab_ids),
            "today_new_vocab_covered": len(required_new_vocab_ids & authored_vocab_ids),
            "used_today_new_vocab_covered": len(required_new_vocab_ids & used_vocab_ids),
            "review_vocab_target": len(required_review_vocab_ids),
            "review_vocab_covered": len(required_review_vocab_ids & authored_vocab_ids),
            "used_review_vocab_covered": len(required_review_vocab_ids & used_vocab_ids),
            "today_new_grammar_total": len(today_new_grammar_ids),
            "today_new_grammar_covered": len(today_new_grammar_ids & authored_grammar_ids),
            "used_today_new_grammar_covered": len(today_new_grammar_ids & used_grammar_ids),
            "grammar_target": len(required_grammar_ids),
            "grammar_covered": len(required_grammar_ids & authored_grammar_ids),
            "used_grammar_target_covered": len(required_grammar_ids & used_grammar_ids),
            "due_vocab_total": len(due_vocab_ids),
            "due_vocab_covered": len(due_vocab_ids & authored_vocab_ids),
            "used_due_vocab_covered": len(due_vocab_ids & used_vocab_ids),
            "due_grammar_total": len(due_grammar_ids),
            "due_grammar_covered": len(due_grammar_ids & authored_grammar_ids),
            "used_due_grammar_covered": len(due_grammar_ids & used_grammar_ids),
        },
    }


def update_item_progress(conn: sqlite3.Connection, tag: dict[str, Any], is_correct: bool, learned_from_exercise: bool) -> None:
    table = "vocab_items" if tag["kind"] == "vocab" else "grammar_items"
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (tag["id"],)).fetchone()
    if not row:
        return
    current_score = row["mastery_score"]
    if current_score is None and row["external_score"] is not None:
        current_score = row["external_score"]
    if current_score is None and row["proficiency"] is not None:
        current_score = int(row["proficiency"]) * 20
    new_score = adjust_mastery_score(current_score, is_correct)
    new_prof = score_to_proficiency(new_score) or 0
    now_dt = now_local()
    interval = schedule_days(new_prof, is_correct)
    next_due = now_dt + timedelta(days=interval)
    times_seen = int(row["times_seen"] or 0) + 1
    correct_times = int(row["correct_times"] or 0) + (1 if is_correct else 0)
    incorrect_times = int(row["incorrect_times"] or 0) + (0 if is_correct else 1)
    correct_rate = round(correct_times * 100.0 / times_seen, 2)
    first_field = "first_memorized_at" if tag["kind"] == "vocab" else "first_studied_at"
    conn.execute(
        f"""
        UPDATE {table}
        SET proficiency = ?,
            mastery_score = ?,
            last_review_at = ?,
            times_seen = ?,
            correct_times = ?,
            incorrect_times = ?,
            correct_rate = ?,
            next_due_at = ?,
            learned_from_exercise = CASE WHEN ? = 1 THEN 1 ELSE learned_from_exercise END,
            {first_field} = CASE
                WHEN ({first_field} IS NULL OR {first_field} = '') AND ? = 1 THEN ?
                ELSE {first_field}
            END,
            updated_at = ?
        WHERE id = ?
        """,
        (
            new_prof,
            new_score,
            ts(now_dt),
            times_seen,
            correct_times,
            incorrect_times,
            correct_rate,
            ts(next_due),
            1 if learned_from_exercise else 0,
            1 if learned_from_exercise else 0,
            ts(now_dt),
            ts(now_dt),
            tag["id"],
        ),
    )


def grade_question(
    conn: sqlite3.Connection,
    question_id: int,
    user_answer: str,
    response_seconds: int | None = None,
) -> dict[str, Any]:
    question = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if not question:
        raise ValueError(f"Question {question_id} not found.")
    if (question["status"] or "pending") in {"correct", "wrong", "invalid"}:
        raise ValueError(f"Question {question_id} has already been finalized with status {question['status']}.")
    record_kind = (question["record_kind"] or "actual").strip().lower()
    normalized_user = normalize_answer(user_answer)
    normalized_correct = normalize_answer(question["answer"])
    is_correct = normalized_user == normalized_correct
    score = 1.0 if is_correct else SequenceMatcher(None, normalized_user, normalized_correct).ratio()
    feedback_summary = (
        f"判定：{'正确' if is_correct else '错误'}。"
        f" 你的答案：{user_answer.strip() or '（空）'}；正确答案：{question['answer']}。"
        f" {question['explanation']}"
    )
    stamp = ts()
    conn.execute(
        """
        INSERT INTO attempts (question_id, answered_at, user_answer, normalized_answer, is_correct, score, feedback_summary, response_seconds, record_kind)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_id,
            stamp,
            user_answer,
            normalized_user,
            1 if is_correct else 0,
            score,
            feedback_summary,
            response_seconds,
            record_kind,
        ),
    )
    attempt_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        "UPDATE questions SET status = ?, updated_at = ? WHERE id = ?",
        ("correct" if is_correct else "wrong", stamp, question_id),
    )
    tags = json.loads(question["knowledge_tags"])
    if record_kind == "actual":
        for tag in tags:
            update_item_progress(conn, tag, is_correct, bool(question["is_new_knowledge"]))
    if not is_correct:
        conn.execute(
            """
            INSERT INTO mistakes (question_id, attempt_id, created_at, session_id, user_answer, correct_answer, reason, review_suggestion, record_kind)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_id,
                attempt_id,
                stamp,
                question["session_id"],
                user_answer,
                question["answer"],
                question["explanation"],
                "建议 24 小时内回看该知识点，并在下一轮组卷中再次出现。",
                record_kind,
            ),
        )
    refresh_session_status(conn, question["session_id"])
    conn.commit()
    append_wrong_notebook_if_needed(conn, question_id, attempt_id, is_correct)
    append_diary_attempt(conn, question_id, feedback_summary)
    append_daily_summary_if_complete(conn, question["session_id"])
    return {
        "question_id": question_id,
        "attempt_id": attempt_id,
        "is_correct": is_correct,
        "feedback_summary": feedback_summary,
    }


def append_wrong_notebook_if_needed(conn: sqlite3.Connection, question_id: int, attempt_id: int, is_correct: bool) -> None:
    if is_correct:
        return
    row = conn.execute(
        """
        SELECT q.ordinal, q.section_name, q.prompt, q.answer, a.user_answer, m.reason, s.id AS session_id, s.session_date, s.record_kind
        FROM questions q
        JOIN attempts a ON a.id = ?
        JOIN mistakes m ON m.attempt_id = a.id
        JOIN sessions s ON s.id = q.session_id
        WHERE q.id = ?
        """,
        (attempt_id, question_id),
    ).fetchone()
    title = f"## {row['session_date']}｜会话 {row['session_id']}｜第 {row['ordinal']} 题"
    if (row["record_kind"] or "actual") == "test":
        title = f"## {row['session_date']}｜测试｜会话 {row['session_id']}｜第 {row['ordinal']} 题"
    with WRONG_NOTEBOOK.open("a", encoding="utf-8") as handle:
        handle.write("\n")
        handle.write(f"{title}\n\n")
        handle.write(f"- 题型：{row['section_name']}\n")
        handle.write(f"- 你的答案：{row['user_answer']}\n")
        handle.write(f"- 正确答案：{row['answer']}\n")
        handle.write(f"- 错因：{row['reason']}\n")
        handle.write("- 复习建议：24 小时内复习，下一次组卷优先回流。\n")


def index_materials(conn: sqlite3.Connection, inbox: Path | None = None) -> list[dict[str, Any]]:
    inbox = inbox or ROOT / "data" / "kb" / "material-inbox"
    results: list[dict[str, Any]] = []
    for path in sorted(inbox.rglob("*")):
        if path.is_dir() or path.name.lower() == "readme.md":
            continue
        payload = path.read_bytes()
        sha1 = hashlib.sha1(payload).hexdigest()
        kind = path.suffix.lower().lstrip(".") or "unknown"
        existing = conn.execute("SELECT id FROM material_sources WHERE path = ?", (str(path),)).fetchone()
        if existing:
            conn.execute(
                "UPDATE material_sources SET sha1 = ?, imported_at = ?, notes = ? WHERE id = ?",
                (sha1, ts(), "重新扫描", existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO material_sources (path, kind, source_scope, sha1, import_status, imported_at, notes)
                VALUES (?, ?, 'external', ?, 'indexed', ?, ?)
                """,
                (str(path), kind, sha1, ts(), "等待后续清洗导入"),
            )
        results.append({"path": str(path), "kind": kind, "sha1": sha1})
    conn.commit()
    return results


def append_progress_snapshot(
    title: str,
    completed: list[str],
    files: list[str],
    errors: list[str],
    next_steps: list[str],
    start: str | None = None,
    end: str | None = None,
) -> Path:
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    start_minute = start or minute()
    end_minute = end or minute()
    completed_lines = [f"- {item}" for item in completed] if completed else ["- 本阶段暂无完成项。"]
    file_lines = [f"- {item}" for item in files] if files else ["- 本阶段未新增文件。"]
    error_lines = [f"- {item}" for item in errors] if errors else ["- 无。"]
    lines = [
        "",
        f"## {start_minute} ~ {end_minute}",
        "",
        "### 本阶段完成内容",
        *completed_lines,
        "",
        "### 新增/修改/生成的文件清单与用途说明",
        *file_lines,
        "",
        "### 错误汇报",
        *error_lines,
    ]
    if title:
        lines.insert(2, f"> 阶段标题：{title}")
    if next_steps:
        lines.extend(["", "### 下一步", *(f"- {item}" for item in next_steps)])
    with PROGRESS_LOG.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return PROGRESS_LOG


def publish_skill(source: Path = SKILL_SRC, target: Path = SKILL_PUBLISH_TARGET) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"Skill source not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return target


def format_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def emit_json(data: Any) -> None:
    payload = format_json(data) + "\n"
    sys.stdout.buffer.write(payload.encode("utf-8"))
    note_tool_output(data)


def dispatch_subcommand(command_name: str) -> None:
    def _runner() -> None:
        parser = build_parser()
        args = parser.parse_args([command_name, *sys.argv[1:]])
        args.func(args)

    run_tool_main(command_name, _runner, [command_name, *sys.argv[1:]])


def cli_import_vocab(args: argparse.Namespace) -> None:
    conn = connect_db()
    entries = load_entries(args.text, args.file, "vocab")
    result = import_vocab_entries(
        conn,
        entries,
        source_scope=args.source_scope,
        source_type=args.source_type,
        memorize=not args.no_memorize,
    )
    emit_json({"inserted": result.inserted, "updated": result.updated, "touched_ids": result.touched_ids})


def cli_import_grammar(args: argparse.Namespace) -> None:
    conn = connect_db()
    entries = load_entries(args.text, args.file, "grammar")
    result = import_grammar_entries(
        conn,
        entries,
        source_scope=args.source_scope,
        source_type=args.source_type,
        study=not args.no_study,
    )
    emit_json({"inserted": result.inserted, "updated": result.updated, "touched_ids": result.touched_ids})


def cli_import_moji_snapshot(args: argparse.Namespace) -> None:
    conn = connect_db()
    entries = load_entries(None, args.file, "vocab")
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        payload = dict(entry)
        if args.status_label and not payload.get("status_label"):
            payload["status_label"] = args.status_label
        if not payload.get("evidence_source"):
            payload["evidence_source"] = str(DEFAULT_MOJI_BUNDLE)
        payload.setdefault("notes", "来自 MOJi 截图导入")
        normalized.append(payload)
    result = import_vocab_entries(
        conn,
        normalized,
        source_scope=args.source_scope,
        source_type="moji_screenshot",
        memorize=not args.no_memorize,
    )
    emit_json({"inserted": result.inserted, "updated": result.updated, "touched_ids": result.touched_ids})


def cli_import_materials(_: argparse.Namespace) -> None:
    conn = connect_db()
    indexed = index_materials(conn)
    emit_json({"indexed": indexed, "count": len(indexed)})


def cli_select_session_content(args: argparse.Namespace) -> None:
    conn = connect_db()
    session_day = args.session_date or now_local().strftime("%Y-%m-%d")
    selection = build_session_selection(conn, session_day, args.target_minutes, args.max_questions)
    emit_json(selection)


def cli_extract_background_candidates(args: argparse.Namespace) -> None:
    conn = connect_db()
    session_day = args.session_date or now_local().strftime("%Y-%m-%d")
    selection = build_session_selection(conn, session_day, args.target_minutes, args.max_questions)
    emit_json(
        {
            "session_day": session_day,
            "target_minutes": args.target_minutes,
            "background_candidates": selection.get("background_candidates", []),
            "authoring_constraints": selection.get("authoring_constraints", {}),
            "reading_bundle_backgrounds": [
                {
                    "vocab": [row["term"] for row in bundle.get("vocab", [])],
                    "grammar": (bundle.get("grammar") or {}).get("pattern"),
                    "background": bundle.get("background"),
                }
                for bundle in selection.get("reading_bundles", [])
            ],
        }
    )


def cli_persist_authored_session(args: argparse.Namespace) -> None:
    conn = connect_db()
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    questions = [validate_authored_question(row) for row in payload.get("questions", [])]
    if not questions:
        raise ValueError("No authored questions found in input payload.")
    session_day = args.session_date or payload.get("session_day") or now_local().strftime("%Y-%m-%d")
    target_minutes = args.target_minutes or int(payload.get("target_minutes") or 35)
    session_id = payload.get("session_id") or uuid.uuid4().hex[:12]
    summary = enrich_authored_summary(
        conn,
        session_day,
        questions,
        authored_session_summary(session_day, target_minutes, questions, payload.get("summary")),
        reference_stamp=ts(),
    )
    persist_session(conn, session_id, session_day, target_minutes, questions, summary, record_kind=args.record_kind)
    superseded_ids: list[str] = []
    if args.record_kind == "actual":
        superseded_ids = supersede_older_pending_sessions(conn, session_day, session_id, args.record_kind)
    diary_path = write_session_diary(conn, session_id)
    question_rows = fetch_rows(
        conn,
        "SELECT id, ordinal, prompt FROM questions WHERE session_id = ? ORDER BY ordinal ASC",
        (session_id,),
    )
    emit_json(
        {
            "session_id": session_id,
            "diary_path": str(diary_path),
            "question_count": len(question_rows),
            "superseded_session_ids": superseded_ids,
            "questions": [dict(row) for row in question_rows],
        }
    )


def cli_generate_session(args: argparse.Namespace) -> None:
    raise SystemExit(
        "generate_session 已停用。当前项目严格要求具体题目由 AI 编写，"
        "禁止脚本直接生成题面。请改用：select_session_content -> "
        "extract_background_candidates -> persist_authored_session。"
    )


def cli_generate_mock_paper(args: argparse.Namespace) -> None:
    raise SystemExit(
        "练习卷/模拟卷导出功能已停用。当前项目只允许把生成题目写入 data/study.db 与 doc/习题日记/，如需正式训练请走整套会话生成流程。"
    )


def cli_grade_answer(args: argparse.Namespace) -> None:
    conn = connect_db()
    result = grade_question(conn, args.question_id, args.user_answer, args.response_seconds)
    emit_json(result)


def cli_session_status(args: argparse.Namespace) -> None:
    conn = connect_db()
    if args.session_id:
        session_id = args.session_id
    else:
        session_day = args.session_date or now_local().strftime("%Y-%m-%d")
        active = find_active_session(
            conn,
            session_day,
            record_kind=args.record_kind,
            include_completed=args.include_completed,
        )
        if not active:
            emit_json(
                {
                    "session_id": None,
                    "session_date": session_day,
                    "record_kind": args.record_kind,
                    "status": "missing",
                    "target_minutes": 0,
                    "question_count": 0,
                    "answered_count": 0,
                    "pending_count": 0,
                    "correct_count": 0,
                    "wrong_count": 0,
                    "summary": {},
                    "next_question": None,
                }
            )
            return
        session_id = active["id"]
    emit_json(session_status_payload(conn, session_id))


def cli_reconcile_session(args: argparse.Namespace) -> None:
    conn = connect_db()
    if args.session_id:
        targets = [args.session_id]
    else:
        session_day = args.session_date or now_local().strftime("%Y-%m-%d")
        rows = fetch_rows(
            conn,
            """
            SELECT id
            FROM sessions
            WHERE session_date = ?
              AND COALESCE(record_kind, 'actual') = ?
              AND status = 'completed'
            ORDER BY created_at ASC, id ASC
            """,
            (session_day, args.record_kind),
        )
        targets = [row["id"] for row in rows]
    results = [reconcile_completed_session_learning(conn, session_id, force=args.force) for session_id in targets]
    emit_json({"results": results})


def cli_audit_study_day(args: argparse.Namespace) -> None:
    conn = connect_db()
    session_day = args.session_date or now_local().strftime("%Y-%m-%d")
    repair = refresh_day_session_statuses(conn, session_day, args.record_kind) if args.apply_status_fixes else None
    emit_json(
        {
            "repair": repair,
            "audit": audit_study_day(conn, session_day, args.record_kind),
        }
    )


def cli_rebuild_day_diary(args: argparse.Namespace) -> None:
    conn = connect_db()
    session_day = args.session_date or now_local().strftime("%Y-%m-%d")
    path = rebuild_day_diary(conn, session_day, record_kind=args.record_kind)
    sessions = fetch_rows(
        conn,
        """
        SELECT id, status, question_count
        FROM sessions
        WHERE session_date = ? AND COALESCE(record_kind, 'actual') = ?
        ORDER BY created_at ASC, id ASC
        """,
        (session_day, args.record_kind),
    )
    emit_json(
        {
            "path": str(path),
            "session_date": session_day,
            "record_kind": args.record_kind,
            "session_count": len(sessions),
            "sessions": [dict(row) for row in sessions],
        }
    )


def cli_sync_progress(args: argparse.Namespace) -> None:
    path = append_progress_snapshot(
        title=args.title,
        completed=args.completed or [],
        files=args.files or [],
        errors=args.errors or [],
        next_steps=args.next_steps or [],
        start=args.start,
        end=args.end,
    )
    emit_json({"progress_log": str(path)})


def cli_publish_skill(_: argparse.Namespace) -> None:
    path = publish_skill()
    emit_json({"published_to": str(path)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Language drill study assistant utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    vocab_parser = subparsers.add_parser("import_vocab", help="Import vocabulary records.")
    vocab_parser.add_argument("--text", default=None)
    vocab_parser.add_argument("--file", default=None)
    vocab_parser.add_argument("--source-scope", default="user")
    vocab_parser.add_argument("--source-type", default="chat")
    vocab_parser.add_argument("--no-memorize", action="store_true")
    vocab_parser.set_defaults(func=cli_import_vocab)

    moji_parser = subparsers.add_parser("import_moji_snapshot", help="Import learned vocabulary from MOJi screenshot data.")
    moji_parser.add_argument("--file", required=True)
    moji_parser.add_argument("--source-scope", default="user")
    moji_parser.add_argument("--status-label", default="")
    moji_parser.add_argument("--no-memorize", action="store_true")
    moji_parser.set_defaults(func=cli_import_moji_snapshot)

    grammar_parser = subparsers.add_parser("import_grammar", help="Import grammar records.")
    grammar_parser.add_argument("--text", default=None)
    grammar_parser.add_argument("--file", default=None)
    grammar_parser.add_argument("--source-scope", default="user")
    grammar_parser.add_argument("--source-type", default="chat")
    grammar_parser.add_argument("--no-study", action="store_true")
    grammar_parser.set_defaults(func=cli_import_grammar)

    material_parser = subparsers.add_parser("import_materials", help="Index files from material inbox.")
    material_parser.set_defaults(func=cli_import_materials)

    select_parser = subparsers.add_parser("select_session_content", help="Select today's study materials without generating question text.")
    select_parser.add_argument("--session-date", default=None)
    select_parser.add_argument("--target-minutes", type=int, default=35)
    select_parser.add_argument("--max-questions", type=int, default=100)
    select_parser.set_defaults(func=cli_select_session_content)

    background_parser = subparsers.add_parser("extract_background_candidates", help="Extract reusable non-study background candidates from today's selected vocab pool.")
    background_parser.add_argument("--session-date", default=None)
    background_parser.add_argument("--target-minutes", type=int, default=35)
    background_parser.add_argument("--max-questions", type=int, default=100)
    background_parser.set_defaults(func=cli_extract_background_candidates)

    authored_parser = subparsers.add_parser("persist_authored_session", help="Persist AI-authored questions as a session.")
    authored_parser.add_argument("--input-json", required=True)
    authored_parser.add_argument("--session-date", default=None)
    authored_parser.add_argument("--target-minutes", type=int, default=None)
    authored_parser.add_argument("--record-kind", choices=["actual", "test"], default="actual")
    authored_parser.set_defaults(func=cli_persist_authored_session)

    session_parser = subparsers.add_parser(
        "generate_session",
        help="Deprecated and disabled. Use AI-authored sessions persisted via persist_authored_session.",
    )
    session_parser.add_argument("--session-date", default=None)
    session_parser.add_argument("--target-minutes", type=int, default=35)
    session_parser.add_argument("--max-questions", type=int, default=100)
    session_parser.add_argument("--record-kind", choices=["actual", "test"], default="actual")
    session_parser.set_defaults(func=cli_generate_session)

    mock_parser = subparsers.add_parser("generate_mock_paper", help="Deprecated. Mock-paper export has been removed.")
    mock_parser.add_argument("--paper-date", default=None)
    mock_parser.add_argument("--title", default=None)
    mock_parser.add_argument("--target-minutes", type=int, default=120)
    mock_parser.add_argument("--max-questions", type=int, default=60)
    mock_parser.set_defaults(export_kind="mock")
    mock_parser.set_defaults(func=cli_generate_mock_paper)

    practice_parser = subparsers.add_parser("generate_practice_paper", help="Deprecated. Practice-paper export has been removed.")
    practice_parser.add_argument("--paper-date", default=None)
    practice_parser.add_argument("--title", default=None)
    practice_parser.add_argument("--target-minutes", type=int, default=120)
    practice_parser.add_argument("--max-questions", type=int, default=60)
    practice_parser.set_defaults(export_kind="practice")
    practice_parser.set_defaults(func=cli_generate_mock_paper)

    grade_parser = subparsers.add_parser("grade_answer", help="Grade one question answer.")
    grade_parser.add_argument("--question-id", type=int, required=True)
    grade_parser.add_argument("--user-answer", required=True)
    grade_parser.add_argument("--response-seconds", type=int, default=None)
    grade_parser.set_defaults(func=cli_grade_answer)

    session_status_parser = subparsers.add_parser("session_status", help="Return active session progress and next pending question.")
    session_status_parser.add_argument("--session-id", default=None)
    session_status_parser.add_argument("--session-date", default=None)
    session_status_parser.add_argument("--record-kind", choices=["actual", "test"], default="actual")
    session_status_parser.add_argument("--include-completed", action="store_true")
    session_status_parser.set_defaults(func=cli_session_status)

    reconcile_parser = subparsers.add_parser("reconcile_session", help="Reconcile completed-session learning results into long-term mastery.")
    reconcile_parser.add_argument("--session-id", default=None)
    reconcile_parser.add_argument("--session-date", default=None)
    reconcile_parser.add_argument("--record-kind", choices=["actual", "test"], default="actual")
    reconcile_parser.add_argument("--force", action="store_true")
    reconcile_parser.set_defaults(func=cli_reconcile_session)

    audit_parser = subparsers.add_parser("audit_study_day", help="Audit one study day for session/data problems and coverage.")
    audit_parser.add_argument("--session-date", default=None)
    audit_parser.add_argument("--record-kind", choices=["actual", "test"], default="actual")
    audit_parser.add_argument("--apply-status-fixes", action="store_true")
    audit_parser.set_defaults(func=cli_audit_study_day)

    rebuild_diary_parser = subparsers.add_parser("rebuild_day_diary", help="Rebuild one day's diary from database-backed used-question records.")
    rebuild_diary_parser.add_argument("--session-date", default=None)
    rebuild_diary_parser.add_argument("--record-kind", choices=["actual", "test"], default="actual")
    rebuild_diary_parser.set_defaults(func=cli_rebuild_day_diary)

    progress_parser = subparsers.add_parser("sync_progress_snapshot", help="Append a progress snapshot.")
    progress_parser.add_argument("--title", default="")
    progress_parser.add_argument("--start", default=None)
    progress_parser.add_argument("--end", default=None)
    progress_parser.add_argument("--completed", action="append")
    progress_parser.add_argument("--files", action="append")
    progress_parser.add_argument("--errors", action="append")
    progress_parser.add_argument("--next-steps", action="append")
    progress_parser.set_defaults(func=cli_sync_progress)

    publish_parser = subparsers.add_parser("publish_skill", help="Sync project-local skill to D:\\2Folder\\skills.")
    publish_parser.set_defaults(func=cli_publish_skill)
    return parser


def main() -> None:
    def _runner() -> None:
        parser = build_parser()
        args = parser.parse_args()
        args.func(args)

    run_tool_main("study_core", _runner, sys.argv[1:])


if __name__ == "__main__":
    main()
