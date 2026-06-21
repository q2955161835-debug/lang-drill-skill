from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable

import fitz
from bs4 import BeautifulSoup

from study_core import connect_db, import_grammar_entries, import_vocab_entries, index_materials, ts
from tool_logging import run_tool_main


ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_DIR = ROOT / "data" / "kb" / "material-inbox" / "official"
HIGH_ENGLISH_PDF = OFFICIAL_DIR / "highschool_english_curriculum_2020.pdf"
CET_PDF = OFFICIAL_DIR / "cet_syllabus_2016.pdf"
GAOKAO_ADAPTIVE_HTML = OFFICIAL_DIR / "gaokao_english_adaptive_2024.html"

GAOKAO_DIR = ROOT / "data" / "kb" / "gaokao-english"
CET4_DIR = ROOT / "data" / "kb" / "cet4"
CET6_DIR = ROOT / "data" / "kb" / "cet6"
ENGLISH_DIR = ROOT / "data" / "kb" / "english"

HIGH_ENGLISH_SOURCE_URL = "https://www.pep.com.cn/xw/zt/rjwy/gzkb2020/202205/P020220517522153664167.pdf"
CET_SOURCE_URL = "https://cet.neea.edu.cn/res/Home/1704/55b02330ac17274664f06d9d3db8249d.pdf"
GAOKAO_ADAPTIVE_URL = "https://www.neea.edu.cn/html1/report/2401/499-1.htm"
CET_HOME_URL = "https://cet.neea.edu.cn/"
NEEA_HOME_URL = "https://www.neea.edu.cn/"

RE_ASCII_LETTER = re.compile(r"[A-Za-z]")
RE_CJK = re.compile(r"[\u4e00-\u9fff]")
RE_PURE_NUM = re.compile(r"^[0-9０-９]+$")
RE_HIGH_VOCAB = re.compile(r"^[A-Za-z][A-Za-z0-9 ./'’()\\-]+\*{0,2}$")
RE_CET_VOCAB = re.compile(r"^★?[A-Za-z][A-Za-z0-9 ./()'’\\-Ｇ]+$")


def clean_text(value: str) -> str:
    value = value.replace("\u3000", " ").replace("\xa0", " ")
    value = value.replace("Ｇ", "-").replace("􀆳", "'").replace("’", "'")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def extract_pdf_lines(path: Path, start_page: int, end_page: int) -> list[str]:
    doc = fitz.open(path)
    lines: list[str] = []
    for page in range(start_page, end_page + 1):
        lines.extend(clean_text(line) for line in doc[page - 1].get_text().splitlines())
    return [line for line in lines if line]


def highschool_difficulty(star_count: int) -> int:
    if star_count >= 2:
        return 3
    if star_count == 1:
        return 2
    return 1


def parse_highschool_english_vocab() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    started = False
    for line in extract_pdf_lines(HIGH_ENGLISH_PDF, 129, 184):
        if not started:
            if line == "A":
                started = True
            continue
        if started and "主要国家名称" in line:
            break
        if should_skip_highschool_vocab_line(line):
            continue
        star_count = len(line) - len(line.rstrip("*"))
        term = clean_text(line.rstrip("*"))
        key = (term.lower(), "gaokao-english")
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "term": term,
                "reading": "",
                "meaning": "",
                "pos": "",
                "source_scope": "gaokao-english",
                "source_type": "official_curriculum_2020",
                "difficulty": highschool_difficulty(star_count),
                "notes": "普通高中英语课程标准（2017年版2020年修订）附录2词汇表；*为必修新增，**为选择性必修新增。",
            }
        )
    return dedupe_vocab(entries)


def should_skip_highschool_vocab_line(line: str) -> bool:
    if not line or RE_PURE_NUM.match(line):
        return True
    if RE_CJK.search(line):
        return True
    if line in {"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"}:
        return True
    if len(line) > 70:
        return True
    return not RE_HIGH_VOCAB.match(line)


def parse_cet_vocab() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cet4: list[dict[str, Any]] = []
    cet6: list[dict[str, Any]] = []
    for line in extract_pdf_lines(CET_PDF, 21, 149):
        if should_skip_cet_vocab_line(line):
            continue
        is_cet6 = line.startswith("★")
        term = clean_text(line.lstrip("★"))
        row = {
            "term": term,
            "reading": "",
            "meaning": "",
            "pos": "",
            "source_scope": "cet6" if is_cet6 else "cet4",
            "source_type": "official_syllabus_2016",
            "difficulty": 3 if is_cet6 else 2,
            "notes": "全国大学英语四、六级考试大纲（2016年修订版）词表；★标为六级词。" if is_cet6 else "全国大学英语四、六级考试大纲（2016年修订版）词表；未加★为四级词。",
        }
        (cet6 if is_cet6 else cet4).append(row)
    return dedupe_vocab(cet4), dedupe_vocab(cet6)


def should_skip_cet_vocab_line(line: str) -> bool:
    if not line or RE_PURE_NUM.match(line):
        return True
    if RE_CJK.search(line):
        return True
    if len(line) > 70:
        return True
    return not RE_CET_VOCAB.match(line)


def dedupe_vocab(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (
            (row.get("term") or "").strip().lower(),
            (row.get("reading") or "").strip().lower(),
            (row.get("source_scope") or "").strip(),
        )
        if not key[0] or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def build_grammar_entries() -> dict[str, list[dict[str, Any]]]:
    gaokao = [
        ("名词：可数名词、不可数名词、专有名词、名词所有格", "词类与名词系统"),
        ("动词：基本形式、及物/不及物、系动词、助动词、情态动词", "词类与动词系统"),
        ("形容词与副词：基本形式、比较级、最高级", "词类与修饰关系"),
        ("代词、数词、介词、连词、冠词", "基础词类与句法连接"),
        ("句子种类：陈述句、疑问句、祈使句、感叹句", "句式识别与表达"),
        ("时态、语态、主谓一致", "谓语结构"),
        ("非谓语动词：动词不定式、动词-ing形式、过去分词", "非谓语结构"),
        ("从句：定语从句、状语从句、名词性从句", "复合句"),
        ("直接引语与间接引语、省略、倒装、强调", "特殊句式"),
    ]
    cet_common = [
        ("听力理解：主旨、细节、隐含意义、观点态度、听力策略", "听力理解能力"),
        ("阅读理解：主旨、细节、推论、作者态度、词义猜测、篇章关系", "阅读理解能力"),
        ("写作：中心思想、信息表达、篇章组织、语法词汇准确性、衔接手段", "书面表达能力"),
        ("翻译：汉语信息转换、段落信息完整表达、译文结构和连贯", "翻译能力"),
        ("口头表达：准确性和范围、话语长短和连贯性、灵活性和适切性", "口语能力"),
    ]
    return {
        "gaokao-english": [
            grammar_row(pattern, meaning, "gaokao-english", "official_curriculum_2020", "普通高中英语课程标准（2017年版2020年修订）附录3语法项目一览。")
            for pattern, meaning in gaokao
        ],
        "cet4": [
            grammar_row(pattern, meaning, "cet4", "official_syllabus_2016", "全国大学英语四、六级考试大纲（2016年修订版）四级考试技能要求。")
            for pattern, meaning in cet_common
        ],
        "cet6": [
            grammar_row(pattern, meaning, "cet6", "official_syllabus_2016", "全国大学英语四、六级考试大纲（2016年修订版）六级考试技能要求。")
            for pattern, meaning in cet_common
        ],
    }


def grammar_row(pattern: str, meaning: str, scope: str, source_type: str, notes: str) -> dict[str, Any]:
    return {
        "pattern": pattern,
        "meaning_cn": meaning,
        "core_usage": meaning,
        "example": "",
        "source_scope": scope,
        "source_type": source_type,
        "difficulty": 2,
        "confusable_with": "",
        "notes": notes,
    }


def build_exam_blueprints() -> list[dict[str, Any]]:
    return [
        {
            "exam_id": "gaokao-english",
            "language": "English",
            "year": 2024,
            "source": GAOKAO_ADAPTIVE_URL,
            "sections": [
                {"name": "Listening", "question_types": ["multiple_choice"], "default_ratio": 0.20, "notes": "听力理解，按高考英语常见听力任务生成。"},
                {"name": "Reading", "question_types": ["multiple_choice", "matching"], "default_ratio": 0.33, "notes": "阅读理解和七选五/匹配类任务。"},
                {"name": "Language Use", "question_types": ["cloze", "grammar_fill_blank"], "default_ratio": 0.20, "notes": "完形填空、语法填空和词汇语法运用。"},
                {"name": "Writing", "question_types": ["application_writing", "continuation_writing"], "default_ratio": 0.27, "notes": "应用文写作和读后续写。"},
            ],
        },
        {
            "exam_id": "cet4",
            "language": "English",
            "year": 2016,
            "source": CET_SOURCE_URL,
            "sections": [
                {"name": "Writing", "question_types": ["essay"], "default_ratio": 0.15, "notes": "四级写作不少于120词。"},
                {"name": "Listening", "question_types": ["news_report", "conversation", "passage"], "default_ratio": 0.35, "notes": "四级听力语速约120-140词/分钟。"},
                {"name": "Reading", "question_types": ["word_bank_cloze", "long_reading_matching", "careful_reading"], "default_ratio": 0.35, "notes": "四级阅读含选词填空、长篇匹配和仔细阅读。"},
                {"name": "Translation", "question_types": ["cn_to_en_paragraph"], "default_ratio": 0.15, "notes": "四级汉译英段落约140-160个汉字。"},
            ],
        },
        {
            "exam_id": "cet6",
            "language": "English",
            "year": 2016,
            "source": CET_SOURCE_URL,
            "sections": [
                {"name": "Writing", "question_types": ["essay"], "default_ratio": 0.15, "notes": "六级写作不少于150词。"},
                {"name": "Listening", "question_types": ["long_conversation", "passage", "lecture"], "default_ratio": 0.35, "notes": "六级听力语速约140-160词/分钟。"},
                {"name": "Reading", "question_types": ["word_bank_cloze", "long_reading_matching", "careful_reading"], "default_ratio": 0.35, "notes": "六级阅读含选词填空、长篇匹配和仔细阅读。"},
                {"name": "Translation", "question_types": ["cn_to_en_paragraph"], "default_ratio": 0.15, "notes": "六级汉译英段落约180-200个汉字。"},
            ],
        },
    ]


def gaokao_adaptive_image_urls() -> list[str]:
    if not GAOKAO_ADAPTIVE_HTML.exists():
        return []
    soup = BeautifulSoup(GAOKAO_ADAPTIVE_HTML.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    urls: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if "/res/Home/2401/" in src:
            urls.append(f"https://www.neea.edu.cn{src}" if src.startswith("/") else src)
    return urls


def build_recent_paper_index() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    gaokao_images = gaokao_adaptive_image_urls()
    for year in ("2023", "2024", "2025"):
        source_status = "official_public" if year == "2024" else "indexed_pending_fulltext"
        source_path = GAOKAO_ADAPTIVE_URL if year == "2024" else NEEA_HOME_URL
        notes = "近三年高考英语试卷索引；不收录完整试题全文。"
        if year == "2024":
            notes += " 中国教育考试网公开2024年高考综合改革适应性测试英语科新课标试卷页面；页面图片资源：" + " | ".join(gaokao_images)
        else:
            notes += " 官方公开全文入口未稳定定位，保留年度试卷槽位，后续可由本地官方/可靠资料导入补全。"
        entries.append(paper_entry("高考英语近三年试卷索引", year, "gaokao-english", "national_paper", source_status, source_path, notes))

    for level, exam_name in (("cet4", "大学英语四级近三年试卷索引"), ("cet6", "大学英语六级近三年试卷索引")):
        for year in ("2023", "2024", "2025"):
            notes = "近三年大学英语四、六级试卷索引；不收录完整试题全文。中国教育考试网官方项目页用于确认考试系列和大纲，历次真题全文如需使用应由用户提供可授权本地资料。"
            entries.append(paper_entry(exam_name, year, level, "june_december_sessions", "indexed_pending_fulltext", CET_HOME_URL, notes))

    entries.extend(
        [
            paper_entry("全国大学英语四级考试（笔试）官方样卷", "2016", "cet4", "official_sample_written", "official_public", CET_SOURCE_URL, "来源于全国大学英语四、六级考试大纲（2016年修订版）样卷；不收录完整试题全文。"),
            paper_entry("全国大学英语六级考试（笔试）官方样卷", "2016", "cet6", "official_sample_written", "official_public", CET_SOURCE_URL, "来源于全国大学英语四、六级考试大纲（2016年修订版）样卷；不收录完整试题全文。"),
        ]
    )
    return entries


def paper_entry(exam_name: str, year: str, level: str, section: str, source_status: str, source_path: str, notes: str) -> dict[str, Any]:
    return {
        "exam_name": exam_name,
        "year": year,
        "level": level,
        "section": section,
        "source_status": source_status,
        "source_path": source_path,
        "notes": notes,
    }


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
                (entry["exam_name"], entry["year"], entry["level"], entry["section"], entry["source_status"], entry["source_path"], entry["notes"], stamp, stamp),
            )
    conn.commit()


def write_readmes(counts: dict[str, int]) -> None:
    common_boundary = "近三年真题默认只保存索引和来源状态，不把版权状态不明的完整试题全文作为默认发布资产。"
    (ENGLISH_DIR / "README.md").write_text(
        "# English Knowledge Base\n\n"
        "This directory documents English exam assets now available in sibling top-level KB folders:\n\n"
        "- `data/kb/gaokao-english/`: Chinese Gaokao English curriculum vocabulary, grammar scope, blueprint, and recent-paper index.\n"
        "- `data/kb/cet4/`: CET-4 official 2016 syllabus vocabulary, skill scope, blueprint, and recent-paper index.\n"
        "- `data/kb/cet6/`: CET-6 official 2016 syllabus vocabulary, skill scope, blueprint, and recent-paper index.\n\n"
        "The core scripts seed top-level `data/kb/*/official_vocab_*.json` and `official_grammar_*.json` files into `data/study.db`.\n\n"
        f"{common_boundary}\n",
        encoding="utf-8",
    )
    for target_dir, title, source, vocab_count, grammar_count in (
        (GAOKAO_DIR, "高考英语", HIGH_ENGLISH_SOURCE_URL, counts["gaokao_vocab"], counts["gaokao_grammar"]),
        (CET4_DIR, "大学英语四级", CET_SOURCE_URL, counts["cet4_vocab"], counts["cet4_grammar"]),
        (CET6_DIR, "大学英语六级", CET_SOURCE_URL, counts["cet6_vocab"], counts["cet6_grammar"]),
    ):
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "README.md").write_text(
            f"# {title} KB\n\n"
            f"- 来源：{source}\n"
            f"- 词汇条目：{vocab_count}\n"
            f"- 语法/技能范围条目：{grammar_count}\n"
            f"- 题型蓝图：`exam_blueprint_*.json`\n"
            f"- 真题索引：`official_papers_index.json`\n"
            f"- 边界：{common_boundary}\n",
            encoding="utf-8",
        )


def write_source_manifest() -> None:
    path = ROOT / "data" / "kb" / "sources_official.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# 官方资料来源清单\n"
    marker = "## 英语考试资料"
    english_section = (
        "\n## 英语考试资料\n"
        "- 高考英语课标：`data/kb/material-inbox/official/highschool_english_curriculum_2020.pdf`，来源："
        f"`{HIGH_ENGLISH_SOURCE_URL}`。\n"
        "- CET 四、六级大纲：`data/kb/material-inbox/official/cet_syllabus_2016.pdf`，来源："
        f"`{CET_SOURCE_URL}`。\n"
        "- 2024 高考英语适应性测试页面：`data/kb/material-inbox/official/gaokao_english_adaptive_2024.html`，来源："
        f"`{GAOKAO_ADAPTIVE_URL}`。\n"
        "- 近三年真题：仅写入 `paper_index` 和 `official_papers_index.json` 的索引/状态，不收录完整试题全文。\n"
    )
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + english_section
    else:
        existing = existing.rstrip() + "\n" + english_section
    path.write_text(existing.rstrip() + "\n", encoding="utf-8")


def write_assets(
    gaokao_vocab: list[dict[str, Any]],
    cet4_vocab: list[dict[str, Any]],
    cet6_vocab: list[dict[str, Any]],
    grammar: dict[str, list[dict[str, Any]]],
    blueprints: list[dict[str, Any]],
    paper_index: list[dict[str, Any]],
) -> None:
    by_dir = {
        "gaokao-english": GAOKAO_DIR,
        "cet4": CET4_DIR,
        "cet6": CET6_DIR,
    }
    vocab_by_scope = {"gaokao-english": gaokao_vocab, "cet4": cet4_vocab, "cet6": cet6_vocab}
    year_by_scope = {"gaokao-english": "2020", "cet4": "2016", "cet6": "2016"}
    for scope, target_dir in by_dir.items():
        year = year_by_scope[scope]
        write_json(target_dir / f"official_vocab_{year}.json", vocab_by_scope[scope])
        write_csv(target_dir / f"official_vocab_{year}.csv", vocab_by_scope[scope])
        write_json(target_dir / f"official_grammar_{year}.json", grammar[scope])
        write_csv(target_dir / f"official_grammar_{year}.csv", grammar[scope])
        blueprint = next(item for item in blueprints if item["exam_id"] == scope)
        write_json(target_dir / f"exam_blueprint_{blueprint['year']}.json", blueprint)
        write_json(target_dir / "official_papers_index.json", [entry for entry in paper_index if entry["level"] == scope])


def main() -> None:
    gaokao_vocab = parse_highschool_english_vocab()
    cet4_vocab, cet6_vocab = parse_cet_vocab()
    grammar = build_grammar_entries()
    blueprints = build_exam_blueprints()
    paper_index = build_recent_paper_index()

    write_assets(gaokao_vocab, cet4_vocab, cet6_vocab, grammar, blueprints, paper_index)
    write_readmes(
        {
            "gaokao_vocab": len(gaokao_vocab),
            "gaokao_grammar": len(grammar["gaokao-english"]),
            "cet4_vocab": len(cet4_vocab),
            "cet4_grammar": len(grammar["cet4"]),
            "cet6_vocab": len(cet6_vocab),
            "cet6_grammar": len(grammar["cet6"]),
        }
    )
    write_source_manifest()

    conn = connect_db()
    import_vocab_entries(conn, gaokao_vocab, source_scope="gaokao-english", source_type="official_curriculum_2020", memorize=False)
    import_vocab_entries(conn, cet4_vocab, source_scope="cet4", source_type="official_syllabus_2016", memorize=False)
    import_vocab_entries(conn, cet6_vocab, source_scope="cet6", source_type="official_syllabus_2016", memorize=False)
    import_grammar_entries(conn, grammar["gaokao-english"], source_scope="gaokao-english", source_type="official_curriculum_2020", study=False)
    import_grammar_entries(conn, grammar["cet4"], source_scope="cet4", source_type="official_syllabus_2016", study=False)
    import_grammar_entries(conn, grammar["cet6"], source_scope="cet6", source_type="official_syllabus_2016", study=False)
    upsert_paper_index(paper_index)
    index_materials(conn, OFFICIAL_DIR)

    print(
        json.dumps(
            {
                "gaokao_vocab": len(gaokao_vocab),
                "gaokao_grammar": len(grammar["gaokao-english"]),
                "cet4_vocab": len(cet4_vocab),
                "cet4_grammar": len(grammar["cet4"]),
                "cet6_vocab": len(cet6_vocab),
                "cet6_grammar": len(grammar["cet6"]),
                "paper_index": len(paper_index),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run_tool_main("build_english_official_kb", main)
