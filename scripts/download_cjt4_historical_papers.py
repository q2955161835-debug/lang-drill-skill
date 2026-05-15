from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from study_core import ROOT, connect_db, index_materials, ts
from tool_logging import run_tool_main


TARGET_DIR = ROOT / "data" / "kb" / "material-inbox" / "historical-papers" / "cjt4" / "ifoor"
INDEX_PATH = ROOT / "data" / "kb" / "cjt4" / "historical_local_pages_2011_2025.json"
ARCHIVE_URL = "https://www.ifoor.com/riyu/cjt4/"
YEAR_PAGES = {
    "2011": "https://www.ifoor.com/riyu/cjt4/90601.html",
    "2012": "https://www.ifoor.com/riyu/cjt4/90602.html",
    "2013": "https://www.ifoor.com/riyu/cjt4/90603.html",
    "2014": "https://www.ifoor.com/riyu/cjt4/90604.html",
    "2015": "https://www.ifoor.com/riyu/cjt4/90605.html",
    "2016": "https://www.ifoor.com/riyu/cjt4/90606.html",
    "2017": "https://www.ifoor.com/riyu/cjt4/90607.html",
    "2018": "https://www.ifoor.com/riyu/cjt4/90608.html",
    "2019": "https://www.ifoor.com/riyu/cjt4/90609.html",
    "2020": "https://www.ifoor.com/riyu/cjt4/90610.html",
    "2021": "https://www.ifoor.com/riyu/cjt4/90611.html",
    "2022": "https://www.ifoor.com/riyu/cjt4/90612.html",
    "2023": "https://www.ifoor.com/riyu/cjt4/90613.html",
    "2024": "https://www.ifoor.com/riyu/cjt4/90614.html",
    "2025": "https://www.ifoor.com/riyu/cjt4/90615.html",
}
DIRECT_LINK_PATTERN = re.compile(r"targetLink1\s*=\s*'([^']+)'")


def fetch(url: str) -> str:
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return response.text


def save_pages() -> list[dict]:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    archive_path = TARGET_DIR / "archive.html"
    archive_path.write_text(fetch(ARCHIVE_URL), encoding="utf-8")
    records.append(
        {
            "year": "archive",
            "title": "大学日语四级真题年份总入口",
            "remote_url": ARCHIVE_URL,
            "local_path": str(archive_path),
        }
    )
    for year, url in YEAR_PAGES.items():
        html = fetch(url)
        path = TARGET_DIR / f"{year}.html"
        path.write_text(html, encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        download_records: list[dict] = []
        for link in soup.select("a.down-btn[href]"):
            href = link.get("href", "").strip()
            if not href:
                continue
            remote = href if href.startswith("http") else f"https://www.ifoor.com{href}"
            key = "download"
            if "btn-kuake" in (link.get("class") or []):
                key = "quark"
            elif "btn-baidu" in (link.get("class") or []):
                key = "baidu"
            elif "btn-xunlei" in (link.get("class") or []):
                key = "xunlei"
            elif "btn-uc" in (link.get("class") or []):
                key = "uc"
            down_html = fetch(remote)
            down_path = TARGET_DIR / f"{year}-{key}.html"
            down_path.write_text(down_html, encoding="utf-8")
            pan_match = re.search(r"https://(?:pan|drive)\.[^\"'<>\\s]+", down_html)
            direct_match = DIRECT_LINK_PATTERN.search(down_html)
            direct_link = direct_match.group(1) if direct_match else (pan_match.group(0) if pan_match else "")
            code_match = re.search(r"(?:pwd|提取码)=([0-9A-Za-z]{4})", direct_link)
            download_records.append(
                {
                    "channel": key,
                    "remote_url": remote,
                    "local_path": str(down_path),
                    "pan_link": direct_link,
                    "extraction_code": code_match.group(1) if code_match else "",
                }
            )
        records.append(
            {
                "year": year,
                "title": f"{year} 年大学日语四级真题页面快照",
                "remote_url": url,
                "local_path": str(path),
                "downloads": download_records,
            }
        )
    INDEX_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


def upsert_index(records: list[dict]) -> None:
    conn = connect_db()
    stamp = ts()
    for row in records:
        paper_year = row["year"]
        if paper_year == "archive":
            continue
        existing = conn.execute(
            """
            SELECT id FROM paper_index
            WHERE exam_name = ? AND year = ? AND level = ? AND section = ?
            """,
            ("大学日语四级历史真题页面快照", paper_year, "cjt4", "local_html_snapshot"),
        ).fetchone()
        download_hints = "；".join(
            f"{item['channel']}={item['pan_link'] or item['remote_url']}" + (f" 提取码 {item['extraction_code']}" if item.get("extraction_code") else "")
            for item in row.get("downloads", [])[:4]
        )
        notes = f"本地快照：{row['local_path']}；远程来源：{row['remote_url']}"
        if download_hints:
            notes += f"；下载线索：{download_hints}"
        if existing:
            conn.execute(
                "UPDATE paper_index SET source_status = ?, source_path = ?, notes = ?, updated_at = ? WHERE id = ?",
                ("local_html_snapshot", row["local_path"], notes, stamp, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO paper_index (exam_name, year, level, section, source_status, source_path, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "大学日语四级历史真题页面快照",
                    paper_year,
                    "cjt4",
                    "local_html_snapshot",
                    "local_html_snapshot",
                    row["local_path"],
                    notes,
                    stamp,
                    stamp,
                ),
            )
    conn.commit()
    index_materials(conn, TARGET_DIR.parent.parent)


def main() -> None:
    records = save_pages()
    upsert_index(records)
    print(
        json.dumps(
            {
                "saved": len(records),
                "index": str(INDEX_PATH),
                "target_dir": str(TARGET_DIR),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run_tool_main("download_cjt4_historical_papers", main)
