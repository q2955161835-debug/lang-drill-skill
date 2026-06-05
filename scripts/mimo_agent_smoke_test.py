from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def is_plausible_api_key(value: str) -> bool:
    text = value.strip()
    if len(text) < 20 or re.search(r"\s", text):
        return False
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return False
    return bool(re.search(r"[A-Za-z]", text) and re.search(r"\d|[_-]", text))


def read_api_key(path: Path) -> str:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    labelled: list[str] = []
    unlabelled: list[str] = []
    for line in lines:
        if re.match(r"https?://", line) or "官网" in line or "http://" in line or "https://" in line:
            continue
        labelled_match = re.match(r"^(?P<key>[^:=：]+)\s*[:=：]\s*(?P<value>.+)$", line)
        if labelled_match:
            key = labelled_match.group("key")
            value = labelled_match.group("value")
            if ("key" in key.lower() or "token" in key.lower() or "密钥" in key) and is_plausible_api_key(value):
                labelled.append(value.strip())
            continue
        if is_plausible_api_key(line):
            unlabelled.append(line)
    candidates = labelled or unlabelled
    if not candidates:
        raise SystemExit("未在 API key 文件中找到可用密钥。")
    return candidates[-1]


def chat_completion(base_url: str, api_key: str, model: str, prompt: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是 LangDrill 的测试 agent，只返回紧凑 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_completion_tokens": 2048,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Mimo API 请求失败：HTTP {exc.code}，响应长度 {len(body)}。") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a minimal MiMo agent smoke test without storing secrets.")
    parser.add_argument("--api-key-file", default=None, help="Local file containing a Mimo API key. The key is never printed.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    load_env_file(Path(".env"))
    api_key = os.environ.get("MIMO_API_KEY", "")
    if args.api_key_file:
        api_key = read_api_key(Path(args.api_key_file))
    if not api_key:
        raise SystemExit("缺少 MIMO_API_KEY，或通过 --api-key-file 指定本地密钥文件。")

    base_url = args.base_url or os.environ.get("MIMO_BASE_URL", DEFAULT_BASE_URL)
    model = args.model or os.environ.get("MIMO_MODEL", DEFAULT_MODEL)
    prompt = (
        "检查这个测试目标是否明确：运行 scripts/restore_default_settings.py 后，"
        "应把 data/background/student_profile.md 写回包含“目标语言：待确认”、"
        "“考试目标：待确认”、“每日题量：待确认”的默认模板；"
        "应把旧 student_profile.md 备份到 D:\\0文件夹\\备份\\lang-drill-settings-YYYYMMDD_HHMM\\；"
        "不得删除或清空 data/study.db。只返回 JSON，字段为 ok 和 note。"
    )
    result = chat_completion(base_url=base_url, api_key=api_key, model=model, prompt=prompt)
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(json.dumps({"model": model, "content_length": len(content), "content": content}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
