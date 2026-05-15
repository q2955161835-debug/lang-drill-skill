from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from study_core import ROOT, connect_db, index_materials, ts
from tool_logging import run_tool_main


SOURCE_DIR = ROOT / "data" / "kb" / "material-inbox" / "historical-papers" / "cjt4" / "ifoor"
TARGET_JSON = ROOT / "data" / "kb" / "cjt4" / "historical_download_manifest_2011_2025.json"
TARGET_MD = ROOT / "doc" / "真题" / "历史真题本地索引.md"
YEAR_PATTERN = re.compile(r"(20\d{2}|201\d)")
TARGET_LINK_PATTERN = re.compile(r"targetLink1\s*=\s*'([^']+)'")


def page_text(node: BeautifulSoup | None) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def extract_direct_link(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    match = TARGET_LINK_PATTERN.search(text)
    link = match.group(1) if match else ""
    code_match = re.search(r"(?:pwd|提取码)=([0-9A-Za-z]{4})", link)
    return link, (code_match.group(1) if code_match else "")


def parse_year_page(path: Path) -> dict:
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    title = page_text(soup.select_one("h1"))
    update_time = page_text(soup.select_one(".info span"))
    preview = [page_text(node) for node in soup.select(".article p")]
    download_pages: list[dict] = []
    for down_path in sorted(path.parent.glob(f"{path.stem}-*.html")):
        channel = down_path.stem.split("-", 1)[1]
        if channel == "download":
            continue
        direct_link, extraction_code = extract_direct_link(down_path)
        download_pages.append(
            {
                "channel": channel,
                "local_path": str(down_path),
                "share_link": direct_link,
                "extraction_code": extraction_code,
            }
        )
    return {
        "year": path.stem,
        "title": title,
        "page_update": update_time,
        "local_path": str(path),
        "preview_text": preview,
        "downloads": download_pages,
    }


def collect_records() -> list[dict]:
    records: list[dict] = []
    for path in sorted(SOURCE_DIR.glob("20*.html")):
        if "-" in path.stem:
            continue
        records.append(parse_year_page(path))
    return records


def write_outputs(records: list[dict]) -> None:
    TARGET_JSON.parent.mkdir(parents=True, exist_ok=True)
    TARGET_MD.parent.mkdir(parents=True, exist_ok=True)
    TARGET_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 历史真题本地索引",
        "",
        f"- 生成时间：{ts()}",
        f"- 覆盖年份：{records[0]['year']} ~ {records[-1]['year']}" if records else "- 覆盖年份：无",
        "- 说明：当前为本地 HTML 快照和网盘分享链接归档，不代表所有年份真题正文文件已直接保存在仓库内。",
        "",
    ]
    for record in records:
        channels = "、".join(
            f"{item['channel']}({item['extraction_code'] or '免码'})"
            for item in record["downloads"]
            if item["share_link"]
        ) or "无"
        lines.extend(
            [
                f"## {record['year']}",
                "",
                f"- 标题：{record['title']}",
                f"- 页面更新时间：{record['page_update']}",
                f"- 本地快照：{record['local_path']}",
                f"- 可用分享渠道：{channels}",
                f"- 页面预览：{record['preview_text'][0] if record['preview_text'] else '无'}",
                "",
            ]
        )
    TARGET_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def upsert_db(records: list[dict]) -> None:
    conn = connect_db()
    stamp = ts()
    for record in records:
        share_summary = "；".join(
            f"{item['channel']}={item['share_link']}" + (f" 提取码 {item['extraction_code']}" if item["extraction_code"] else "")
            for item in record["downloads"]
            if item["share_link"]
        )
        notes = f"页面更新时间：{record['page_update']}；本地清单：{TARGET_JSON}"
        if share_summary:
            notes += f"；分享链接：{share_summary}"
        row = conn.execute(
            """
            SELECT id FROM paper_index
            WHERE exam_name = ? AND year = ? AND level = ? AND section = ?
            """,
            ("大学日语四级历史真题页面快照", record["year"], "cjt4", "local_html_snapshot"),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE paper_index SET source_status = ?, source_path = ?, notes = ?, updated_at = ? WHERE id = ?",
                ("local_manifest_ready", record["local_path"], notes, stamp, row["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO paper_index (exam_name, year, level, section, source_status, source_path, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "大学日语四级历史真题页面快照",
                    record["year"],
                    "cjt4",
                    "local_html_snapshot",
                    "local_manifest_ready",
                    record["local_path"],
                    notes,
                    stamp,
                    stamp,
                ),
            )
    conn.commit()
    index_materials(conn, SOURCE_DIR.parent.parent)


def main() -> None:
    records = collect_records()
    write_outputs(records)
    upsert_db(records)
    print(
        json.dumps(
            {
                "records": len(records),
                "json": str(TARGET_JSON),
                "markdown": str(TARGET_MD),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run_tool_main("build_cjt4_historical_manifest", main)
