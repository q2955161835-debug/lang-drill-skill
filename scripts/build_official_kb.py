from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import fitz

from study_core import connect_db, import_grammar_entries, import_vocab_entries, index_materials, ts
from tool_logging import run_tool_main


ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_DIR = ROOT / "data" / "kb" / "material-inbox" / "official"
EXTRACTED_DIR = OFFICIAL_DIR / "extracted"
CJT4_PDF = OFFICIAL_DIR / "cjt4_syllabus_2023.pdf"
GAOKAO_PDF = EXTRACTED_DIR / "highschool_japanese_curriculum_2020.pdf"
GAOKAO_HTML = OFFICIAL_DIR / "gaokao_japanese_adaptive_2024.html"
CJT4_DIR = ROOT / "data" / "kb" / "cjt4"
GAOKAO_DIR = ROOT / "data" / "kb" / "gaokao-japanese"


RE_CJK = re.compile(r"[\u4e00-\u9fff]")
RE_KANA = re.compile(r"[\u3040-\u30ff]")
RE_PURE_NUM = re.compile(r"^\d+$")
RE_CJT4_VOCAB = re.compile(r"^(?P<star>[＊*])?\s*(?P<reading>[^\s【】]+?)(?:【(?P<surface>[^】]+)】)?$")


def clean_text(value: str) -> str:
    value = value.replace("\u3000", " ").replace("\xa0", " ")
    value = value.replace("\u2002", " ").replace("\u2003", " ").replace("\u2009", " ")
    value = value.replace("\x07", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def contains_cjk(value: str) -> bool:
    return bool(RE_CJK.search(value))


def extract_pdf_text(path: Path, start_page: int, end_page: int) -> str:
    doc = fitz.open(path)
    chunks = [doc[idx].get_text() for idx in range(start_page - 1, end_page)]
    return "\n".join(chunks)


def clean_lines(text: str) -> list[str]:
    lines = [clean_text(line) for line in text.splitlines()]
    return [line for line in lines if line]


def parse_cjt4_vocab() -> list[dict[str, Any]]:
    text = extract_pdf_text(CJT4_PDF, 14, 126)
    lines = clean_lines(text)
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    skip_exact = {
        "全国大学日语四、六级考试大纲",
        "词汇表",
        "あ",
        "い",
        "う",
        "え",
        "お",
        "か",
        "き",
        "く",
        "け",
        "こ",
        "さ",
        "し",
        "す",
        "せ",
        "そ",
        "た",
        "ち",
        "つ",
        "て",
        "と",
        "な",
        "に",
        "ぬ",
        "ね",
        "の",
        "は",
        "ひ",
        "ふ",
        "へ",
        "ほ",
        "ま",
        "み",
        "む",
        "め",
        "も",
        "や",
        "ゆ",
        "よ",
        "ら",
        "り",
        "る",
        "れ",
        "ろ",
        "わ",
    }
    for line in lines:
        if line in skip_exact or RE_PURE_NUM.match(line) or contains_cjk(line) and "【" not in line:
            continue
        if line.startswith("1.") or line.startswith("2.") or line.startswith("3.") or line.startswith("4."):
            continue
        match = RE_CJT4_VOCAB.match(line)
        if not match:
            continue
        reading = clean_text(match.group("reading"))
        surface_raw = clean_text(match.group("surface") or "")
        surface = surface_raw.split("・")[0].split("／")[0].split("/")[0] if surface_raw else reading
        core_required = bool(match.group("star"))
        key = (surface, reading)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "term": surface,
                "reading": reading,
                "meaning": "",
                "pos": "",
                "source_scope": "cjt4",
                "source_type": "official_syllabus_2023",
                "difficulty": 2 if core_required else 4,
                "notes": "官方大学日语大纲词汇表；* 为四/六级1-4级重点词汇" if core_required else "官方大学日语大纲词汇表；发展目标词汇",
            }
        )
    return entries


def parse_cjt4_grammar() -> list[dict[str, Any]]:
    text = extract_pdf_text(CJT4_PDF, 127, 141)
    lines = clean_lines(text)
    start_idx = next(idx for idx, line in enumerate(lines) if line == "1")
    entries: list[dict[str, Any]] = []
    idx = start_idx

    def looks_like_pattern_line(value: str) -> bool:
        if not value or RE_PURE_NUM.match(value):
            return False
        if value in {"序", "号", "目", "标", "项目", "语法意义"}:
            return False
        if "～" in value or RE_KANA.search(value):
            return True
        if value.startswith("/"):
            return True
        if value in {"が", "から", "で", "と", "に", "の", "は", "へ", "も", "や", "より", "を"}:
            return True
        return False

    while idx < len(lines):
        line = lines[idx]
        if not RE_PURE_NUM.match(line):
            idx += 1
            continue
        ordinal = int(line)
        idx += 1
        core_required = False
        if idx < len(lines) and lines[idx] in {"*", "＊"}:
            core_required = True
            idx += 1
        pattern_lines: list[str] = []
        while idx < len(lines) and looks_like_pattern_line(lines[idx]):
            pattern_lines.append(lines[idx])
            idx += 1
        meaning_lines: list[str] = []
        while idx < len(lines) and not RE_PURE_NUM.match(lines[idx]):
            meaning_lines.append(lines[idx])
            idx += 1
        pattern = " ".join(pattern_lines).replace(" /", "/").replace("/ ", "/")
        meaning = "".join(meaning_lines)
        if not pattern:
            continue
        entries.append(
            {
                "pattern": pattern,
                "meaning_cn": meaning,
                "core_usage": meaning,
                "example": "",
                "source_scope": "cjt4",
                "source_type": "official_syllabus_2023",
                "difficulty": 2 if core_required else 4,
                "confusable_with": "",
                "notes": f"官方大学日语大纲语法项目表，第{ordinal}项",
            }
        )
    return entries


def parse_gaokao_vocab() -> list[dict[str, Any]]:
    text = extract_pdf_text(GAOKAO_PDF, 96, 114)
    lines = clean_lines(text)
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    idx = 0
    while idx < len(lines) - 1:
        line = lines[idx]
        if line.startswith("附录4 词汇表") or line.startswith("本表包含") or line.startswith("表中的") or RE_PURE_NUM.match(line):
            idx += 1
            continue
        level_line = lines[idx + 1]
        if level_line not in {"4", "5"}:
            idx += 1
            continue
        raw = line
        if "（" in raw and "）" in raw:
            reading, surface_raw = raw.split("（", 1)
            surface = surface_raw.rstrip("）").split("・")[0]
        else:
            reading = raw
            surface = raw
        reading = clean_text(reading)
        surface = clean_text(surface)
        key = (surface, reading)
        if key in seen:
            idx += 2
            continue
        seen.add(key)
        level = int(level_line)
        entries.append(
            {
                "term": surface,
                "reading": reading,
                "meaning": "",
                "pos": "",
                "source_scope": "gaokao",
                "source_type": "official_curriculum_2020",
                "difficulty": 2 if level == 4 else 3,
                "notes": f"官方普通高中日语课程标准词汇表，级别 {level}",
            }
        )
        idx += 2
    return entries


def is_pattern_line(line: str) -> bool:
    if not line or line in {"结构", "功能意义", "例句", "续表"}:
        return False
    if RE_PURE_NUM.match(line):
        return False
    if line.startswith("附录") or line.startswith("普通高中日语课程标准") or line.startswith("本表") or line.startswith("注："):
        return False
    return not contains_cjk(line) and not line.startswith("●")


def parse_gaokao_grammar() -> list[dict[str, Any]]:
    text = extract_pdf_text(GAOKAO_PDF, 81, 95)
    lines = clean_lines(text)
    start_idx = next(idx for idx, line in enumerate(lines) if "附录3 语法表" in line)
    end_idx = next((idx for idx, line in enumerate(lines) if "附录4 词汇表" in line), len(lines))
    lines = lines[start_idx:end_idx]
    entries: list[dict[str, Any]] = []
    current_patterns: list[str] = []
    current_meaning: list[str] = []
    current_examples: list[str] = []
    stage = "seek"

    def finalize() -> None:
        if not current_patterns:
            return
        pattern = " / ".join(current_patterns)
        meaning = "".join(current_meaning)
        example = " || ".join(current_examples)
        entries.append(
            {
                "pattern": pattern,
                "meaning_cn": meaning,
                "core_usage": meaning,
                "example": example,
                "source_scope": "gaokao",
                "source_type": "official_curriculum_2020",
                "difficulty": 2,
                "confusable_with": "",
                "notes": "官方普通高中日语课程标准附录3语法表",
            }
        )
        current_patterns.clear()
        current_meaning.clear()
        current_examples.clear()

    for line in lines:
        if line in {"结构", "功能意义", "例句", "续表"} or RE_PURE_NUM.match(line):
            continue
        if line.startswith("附录3") or line.startswith("本表") or line.startswith("注：") or line.startswith("1. 词法表") or line.startswith("2. 句法表"):
            continue
        if stage == "seek":
            if is_pattern_line(line):
                current_patterns.append(line)
                stage = "pattern"
            continue
        if stage == "pattern":
            if is_pattern_line(line):
                current_patterns.append(line)
            elif line.startswith("●"):
                current_examples.append(line.lstrip("●").strip())
                stage = "example"
            else:
                current_meaning.append(line)
                stage = "meaning"
            continue
        if stage == "meaning":
            if line.startswith("●"):
                current_examples.append(line.lstrip("●").strip())
                stage = "example"
            elif is_pattern_line(line) and current_examples:
                finalize()
                current_patterns.append(line)
                stage = "pattern"
            else:
                current_meaning.append(line)
            continue
        if stage == "example":
            if line.startswith("●"):
                current_examples.append(line.lstrip("●").strip())
            elif is_pattern_line(line):
                finalize()
                current_patterns.append(line)
                stage = "pattern"
            else:
                if current_examples:
                    current_examples[-1] = f"{current_examples[-1]} {line}".strip()
                else:
                    current_meaning.append(line)
    finalize()
    return entries


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_paper_index() -> list[dict[str, Any]]:
    gaokao_page_urls = [
        f"https://www.neea.edu.cn{suffix}"
        for suffix in [
            "/res/Home/2401/24010519.jpg",
            "/res/Home/2401/24010520.jpg",
            "/res/Home/2401/24010521.jpg",
            "/res/Home/2401/24010522.jpg",
            "/res/Home/2401/24010523.jpg",
            "/res/Home/2401/24010524.jpg",
            "/res/Home/2401/24010525.jpg",
            "/res/Home/2401/24010526.jpg",
            "/res/Home/2401/24010527.jpg",
            "/res/Home/2401/24010528.jpg",
            "/res/Home/2401/24010529.png",
            "/res/Home/2401/24010530.png",
        ]
    ]
    return [
        {
            "exam_name": "大学日语四级考试官方样卷",
            "year": "2023",
            "level": "cjt4",
            "section": "full_sample",
            "source_status": "official_public",
            "source_path": str(CJT4_PDF),
            "notes": "来源于《全国大学日语四、六级考试大纲（2023年版）》；样卷页码 142-161。",
        },
        {
            "exam_name": "大学日语四级考试官方样卷听力文字稿",
            "year": "2023",
            "level": "cjt4",
            "section": "listening_transcript",
            "source_status": "official_public",
            "source_path": str(CJT4_PDF),
            "notes": "来源于《全国大学日语四、六级考试大纲（2023年版）》；听力文字稿页码 162-168。",
        },
        {
            "exam_name": "大学日语四级考试官方样卷标准答案",
            "year": "2023",
            "level": "cjt4",
            "section": "answer_key",
            "source_status": "official_public",
            "source_path": str(CJT4_PDF),
            "notes": "来源于《全国大学日语四、六级考试大纲（2023年版）》；标准答案页码 169-172。",
        },
        {
            "exam_name": "2024年高考综合改革适应性测试日语科新课标试卷",
            "year": "2024",
            "level": "gaokao",
            "section": "adaptive_test",
            "source_status": "official_public",
            "source_path": "https://www.neea.edu.cn/html1/report/2401/531-1.htm",
            "notes": "中国教育考试网官方页面；页面包含试卷图片资源：" + " | ".join(gaokao_page_urls),
        },
    ]


def upsert_paper_index(entries: list[dict[str, Any]]) -> None:
    conn = connect_db()
    stamp = ts()
    for entry in entries:
        row = conn.execute(
            "SELECT id FROM paper_index WHERE exam_name = ? AND year = ? AND level = ? AND section = ?",
            (entry["exam_name"], entry["year"], entry["level"], entry["section"]),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE paper_index
                SET source_status = ?, source_path = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (entry["source_status"], entry["source_path"], entry["notes"], stamp, row["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO paper_index (exam_name, year, level, section, source_status, source_path, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["exam_name"],
                    entry["year"],
                    entry["level"],
                    entry["section"],
                    entry["source_status"],
                    entry["source_path"],
                    entry["notes"],
                    stamp,
                    stamp,
                ),
            )
    conn.commit()


def write_source_manifest() -> None:
    content = (
        "# 官方资料来源清单\n\n"
        "## 大学日语四、六级\n"
        "- 来源文件：`data/kb/material-inbox/official/cjt4_syllabus_2023.pdf`\n"
        "- 官方链接：`https://cet.neea.edu.cn/res/Home/2304/c9be2343532610fa7c6700e7b1074ae9.pdf`\n"
        "- 包含内容：词汇表、语法项目表、四级样卷、四级样卷听力文字稿、四级样卷标准答案、六级样卷相关内容。\n\n"
        "## 普通高中日语课程标准\n"
        "- 来源文件：`data/kb/material-inbox/official/extracted/highschool_japanese_curriculum_2020.pdf`\n"
        "- 官方链接：`http://www.moe.gov.cn/srcsite/A26/s8001/202006/W020200603315372317586.zip`\n"
        "- 包含内容：附录3语法表、附录4词汇表。\n\n"
        "## 高考日语公开样题页面\n"
        "- 来源文件：`data/kb/material-inbox/official/gaokao_japanese_adaptive_2024.html`\n"
        "- 官方链接：`https://www.neea.edu.cn/html1/report/2401/531-1.htm`\n"
        "- 包含内容：2024年高考综合改革适应性测试日语科新课标试卷页面与配图资源索引。\n"
    )
    (ROOT / "data" / "kb" / "sources_official.md").write_text(content, encoding="utf-8")


def main() -> None:
    cjt4_vocab = parse_cjt4_vocab()
    cjt4_grammar = parse_cjt4_grammar()
    gaokao_vocab = parse_gaokao_vocab()
    gaokao_grammar = parse_gaokao_grammar()
    paper_index = build_paper_index()

    write_json(CJT4_DIR / "official_vocab_2023.json", cjt4_vocab)
    write_csv(CJT4_DIR / "official_vocab_2023.csv", cjt4_vocab)
    write_json(CJT4_DIR / "official_grammar_2023.json", cjt4_grammar)
    write_csv(CJT4_DIR / "official_grammar_2023.csv", cjt4_grammar)
    write_json(CJT4_DIR / "official_papers_index.json", [entry for entry in paper_index if entry["level"] == "cjt4"])

    write_json(GAOKAO_DIR / "official_vocab_2020.json", gaokao_vocab)
    write_csv(GAOKAO_DIR / "official_vocab_2020.csv", gaokao_vocab)
    write_json(GAOKAO_DIR / "official_grammar_2020.json", gaokao_grammar)
    write_csv(GAOKAO_DIR / "official_grammar_2020.csv", gaokao_grammar)
    write_json(GAOKAO_DIR / "official_papers_index.json", [entry for entry in paper_index if entry["level"] == "gaokao"])

    write_source_manifest()

    conn = connect_db()
    import_vocab_entries(conn, cjt4_vocab, source_scope="cjt4", source_type="official_syllabus_2023", memorize=False)
    import_grammar_entries(conn, cjt4_grammar, source_scope="cjt4", source_type="official_syllabus_2023", study=False)
    import_vocab_entries(conn, gaokao_vocab, source_scope="gaokao", source_type="official_curriculum_2020", memorize=False)
    import_grammar_entries(conn, gaokao_grammar, source_scope="gaokao", source_type="official_curriculum_2020", study=False)
    upsert_paper_index(paper_index)
    index_materials(conn, OFFICIAL_DIR)

    print(
        json.dumps(
            {
                "cjt4_vocab": len(cjt4_vocab),
                "cjt4_grammar": len(cjt4_grammar),
                "gaokao_vocab": len(gaokao_vocab),
                "gaokao_grammar": len(gaokao_grammar),
                "paper_index": len(paper_index),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run_tool_main("build_official_kb", main)
