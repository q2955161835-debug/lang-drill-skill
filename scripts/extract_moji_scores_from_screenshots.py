from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from study_core import DEFAULT_MOJI_BUNDLE, ROOT, connect_db, import_vocab_entries
from tool_logging import run_tool_main


SCREENSHOT_DIR = DEFAULT_MOJI_BUNDLE
TARGET_JSON = ROOT / "data" / "intake" / "moji_vocab_scores.json"
TARGET_CSV = ROOT / "data" / "intake" / "moji_vocab_scores.csv"
OCR_CACHE = ROOT / "tmp" / "moji_score_ocr_cache.json"
SOURCE_FILE = ROOT / "data" / "intake" / "moji_vocab.json"
ITEM_X1 = 70
ITEM_X2 = 900
ITEM_Y_PAD_TOP = 170
ITEM_Y_PAD_BOTTOM = 20
RESIZE_SCALE = 2


@dataclass
class Observation:
    score: int
    image: str
    y: float
    raw_text: str
    matched_term: str
    matched_reading: str
    similarity: float


def load_source_entries() -> list[dict]:
    return json.loads(SOURCE_FILE.read_text(encoding="utf-8"))


def visible_images() -> list[Path]:
    return sorted(path for path in SCREENSHOT_DIR.glob("IMG_*.PNG") if "(1)" not in path.name)


def normalize_text(text: str) -> str:
    replacements = {
        "丨": "|",
        "｜": "|",
        "＜": "",
        "<": "",
        ">": "",
        "（": "",
        "）": "",
        "(": "",
        ")": "",
        "「": "",
        "」": "",
        "【": "",
        "】": "",
        "[": "",
        "]": "",
        "值": "値",
        "业": "業",
        "气": "気",
        "国": "国",
        "龙": "段",
        "翰": "幹",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[①②③④⑤⑥⑦⑧⑨⑩0-9]", "", text)
    text = text.replace("|", "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^一-龯ぁ-んァ-ンー々]+", "", text)
    return text


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    base = SequenceMatcher(None, a, b).ratio()
    if a in b or b in a:
        overlap = min(len(a), len(b)) / max(len(a), len(b))
        base = max(base, overlap)
    return base


def candidate_texts(ocr_rows: Iterable[list]) -> list[str]:
    candidates: list[str] = []
    for box, text, _conf in ocr_rows:
        top = min(point[1] for point in box)
        if top > 240:
            continue
        stripped = text.strip()
        if not stripped or "分" in stripped:
            continue
        if "[" in stripped or "名" in stripped and "］" in stripped:
            continue
        candidates.append(stripped)
    return candidates


def score_rows(image_path: Path, ocr_rows: Iterable[list]) -> list[tuple[float, int]]:
    matches: list[tuple[float, int]] = []
    for box, text, _conf in ocr_rows:
        match = re.search(r"(\d{2,3})\s*分", text)
        if not match:
            continue
        y = min(point[1] for point in box)
        matches.append((y, int(match.group(1))))
    matches.sort()
    return matches


def crop_candidates(image_path: Path, y: float, ocr: RapidOCR) -> list[str]:
    image = Image.open(image_path)
    y1 = max(0, int(y) - ITEM_Y_PAD_TOP)
    y2 = min(image.height, int(y) + ITEM_Y_PAD_BOTTOM)
    crop = image.crop((ITEM_X1, y1, ITEM_X2, y2))
    crop = crop.resize((crop.width * RESIZE_SCALE, crop.height * RESIZE_SCALE))
    result, _ = ocr(np.array(crop))
    return candidate_texts(result or [])


def build_cache(images: list[Path], ocr: RapidOCR) -> dict[str, dict]:
    OCR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    if OCR_CACHE.exists():
        cache = json.loads(OCR_CACHE.read_text(encoding="utf-8"))
    else:
        cache = {}
    for image_path in images:
        if image_path.name in cache:
            continue
        rows, _ = ocr(str(image_path))
        rows = rows or []
        score_hits = score_rows(image_path, rows)
        cache[image_path.name] = {
            "scores": [
                {
                    "y": y,
                    "score": score,
                    "candidates": crop_candidates(image_path, y, ocr),
                }
                for y, score in score_hits
            ]
        }
        OCR_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cache


def best_entry(raw: str, entries: list[dict]) -> tuple[float, dict] | None:
    raw_norm = normalize_text(raw)
    if not raw_norm:
        return None
    best: tuple[float, dict] | None = None
    for entry in entries:
        term_norm = normalize_text(entry["term"])
        reading_norm = normalize_text(entry["reading"])
        joined = term_norm + reading_norm
        score = max(similarity(raw_norm, term_norm), similarity(raw_norm, reading_norm), similarity(raw_norm, joined))
        if best is None or score > best[0]:
            best = (score, entry)
    return best


def extract_observations(entries: list[dict], cache: dict[str, dict]) -> list[Observation]:
    observations: list[Observation] = []
    for image_name, payload in cache.items():
        for item in payload["scores"]:
            y = float(item["y"])
            score = int(item["score"])
            for raw in item["candidates"]:
                hit = best_entry(raw, entries)
                if not hit:
                    continue
                similarity_score, entry = hit
                if similarity_score < 0.62:
                    continue
                observations.append(
                    Observation(
                        score=score,
                        image=image_name,
                        y=y,
                        raw_text=raw,
                        matched_term=entry["term"],
                        matched_reading=entry["reading"],
                        similarity=similarity_score,
                    )
                )
    return observations


def consolidate(entries: list[dict], observations: list[Observation]) -> tuple[list[dict], list[dict]]:
    buckets: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        buckets[(obs.matched_term, obs.matched_reading)].append(obs)

    resolved: list[dict] = []
    unresolved: list[dict] = []
    for entry in entries:
        key = (entry["term"], entry["reading"])
        group = buckets.get(key, [])
        if not group:
            unresolved.append(
                {
                    "term": entry["term"],
                    "reading": entry["reading"],
                    "status_label": entry["status_label"],
                    "reason": "ocr_no_match",
                }
            )
            continue
        counter = Counter(obs.score for obs in group)
        final_score, frequency = counter.most_common(1)[0]
        best_obs = max((obs for obs in group if obs.score == final_score), key=lambda obs: obs.similarity)
        resolved.append(
            {
                "term": entry["term"],
                "reading": entry["reading"],
                "status_label": entry["status_label"],
                "external_score": final_score,
                "mastery_score": final_score,
                "source_scope": "user",
                "source_type": "moji_screenshot",
                "evidence_source": str(SCREENSHOT_DIR),
                "notes": f"MOJi 截图 OCR 提取；最佳匹配 {best_obs.image}@y={int(best_obs.y)}，原始识别：{best_obs.raw_text}",
                "observed_count": len(group),
                "vote_count": frequency,
                "best_similarity": round(best_obs.similarity, 4),
            }
        )
    return resolved, unresolved


def write_outputs(resolved: list[dict], unresolved: list[dict]) -> None:
    TARGET_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {"resolved": resolved, "unresolved": unresolved}
    TARGET_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with TARGET_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "term",
                "reading",
                "status_label",
                "external_score",
                "mastery_score",
                "source_scope",
                "source_type",
                "evidence_source",
                "observed_count",
                "vote_count",
                "best_similarity",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(resolved)


def import_scores(resolved: list[dict]) -> dict[str, int]:
    conn = connect_db()
    result = import_vocab_entries(
        conn,
        resolved,
        source_scope="user",
        source_type="moji_screenshot",
        memorize=True,
    )
    return {"inserted": result.inserted, "updated": result.updated}


def main() -> None:
    entries = load_source_entries()
    images = visible_images()
    ocr = RapidOCR()
    cache = build_cache(images, ocr)
    observations = extract_observations(entries, cache)
    resolved, unresolved = consolidate(entries, observations)
    write_outputs(resolved, unresolved)
    import_result = import_scores(resolved)
    print(
        json.dumps(
            {
                "images": len(images),
                "observations": len(observations),
                "resolved": len(resolved),
                "unresolved": len(unresolved),
                "json": str(TARGET_JSON),
                "csv": str(TARGET_CSV),
                "ocr_cache": str(OCR_CACHE),
                **import_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run_tool_main("extract_moji_scores_from_screenshots", main)
