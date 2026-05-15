from __future__ import annotations

import json
import os
import re
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
RUN_INDEX_PATH = LOG_DIR / "tool_runs.jsonl"
HEALTH_PATH = LOG_DIR / "health_snapshot.json"
DETAIL_RETENTION_DAYS = 30
INDEX_RETENTION_DAYS = 60
OUTPUT_PREVIEW_LIMIT = 4000


class ToolRunLogger:
    def __init__(self, tool_name: str, argv: list[str]):
        self.tool_name = tool_name
        self.argv = list(argv)
        self.started_at = datetime.now().replace(microsecond=0)
        self.started_perf = perf_counter()
        self.run_id = f"{self.started_at.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{slugify(tool_name)}"
        self.day_dir = LOG_DIR / self.started_at.strftime("%Y-%m-%d")
        self.detail_path = self.day_dir / f"{self.run_id}.log"
        self.output_preview: list[str] = []

    def start(self) -> None:
        ensure_log_dirs()
        cleanup_old_logs()
        self.day_dir.mkdir(parents=True, exist_ok=True)
        header = [
            f"tool={self.tool_name}",
            f"started_at={self.started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"cwd={Path.cwd()}",
            f"argv={json.dumps(self.argv, ensure_ascii=False)}",
            f"python={sys.executable}",
            "",
        ]
        self.detail_path.write_text("\n".join(header), encoding="utf-8")

    def remember_output(self, payload: Any) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        if len(text) > OUTPUT_PREVIEW_LIMIT:
            text = text[:OUTPUT_PREVIEW_LIMIT] + " ...<truncated>"
        self.output_preview.append(text)
        self.output_preview = self.output_preview[-3:]
        with self.detail_path.open("a", encoding="utf-8") as fh:
            fh.write("[output]\n")
            fh.write(text)
            fh.write("\n\n")

    def finalize(
        self,
        *,
        status: str,
        exit_code: int,
        error: BaseException | None = None,
        traceback_text: str | None = None,
    ) -> None:
        ended_at = datetime.now().replace(microsecond=0)
        duration_ms = int((perf_counter() - self.started_perf) * 1000)
        record = {
            "run_id": self.run_id,
            "tool": self.tool_name,
            "status": status,
            "exit_code": exit_code,
            "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "ended_at": ended_at.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_ms": duration_ms,
            "cwd": str(Path.cwd()),
            "argv": self.argv,
            "detail_log": str(self.detail_path.relative_to(ROOT)),
            "output_preview": self.output_preview,
        }
        if error is not None:
            record["error_type"] = type(error).__name__
            record["error_message"] = str(error)

        with self.detail_path.open("a", encoding="utf-8") as fh:
            fh.write("[result]\n")
            fh.write(json.dumps(record, ensure_ascii=False, indent=2))
            fh.write("\n")
            if traceback_text:
                fh.write("\n[traceback]\n")
                fh.write(traceback_text)
                if not traceback_text.endswith("\n"):
                    fh.write("\n")

        with RUN_INDEX_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        refresh_health_snapshot()


CURRENT_LOGGER: ContextVar[ToolRunLogger | None] = ContextVar("current_tool_logger", default=None)


def slugify(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip())
    return text.strip("-") or "tool"


def ensure_log_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def parse_stamp(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def cleanup_old_logs() -> None:
    if not LOG_DIR.exists():
        return
    detail_cutoff = datetime.now() - timedelta(days=DETAIL_RETENTION_DAYS)
    for child in LOG_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            stamp = datetime.strptime(child.name, "%Y-%m-%d")
        except ValueError:
            continue
        if stamp < detail_cutoff:
            for nested in child.iterdir():
                nested.unlink(missing_ok=True)
            child.rmdir()
    if RUN_INDEX_PATH.exists():
        index_cutoff = datetime.now() - timedelta(days=INDEX_RETENTION_DAYS)
        kept_lines: list[str] = []
        for line in RUN_INDEX_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            started_at = parse_stamp(record.get("started_at"))
            if started_at and started_at >= index_cutoff:
                kept_lines.append(json.dumps(record, ensure_ascii=False))
        RUN_INDEX_PATH.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")


def refresh_health_snapshot() -> None:
    if not RUN_INDEX_PATH.exists():
        return
    records: list[dict[str, Any]] = []
    for line in RUN_INDEX_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    recent_cutoff = datetime.now() - timedelta(days=7)
    recent = [row for row in records if (parse_stamp(row.get("started_at")) or datetime.min) >= recent_cutoff]
    failures = [row for row in recent if row.get("status") != "success"]
    by_tool: dict[str, dict[str, int]] = {}
    for row in recent:
        tool = str(row.get("tool") or "unknown")
        bucket = by_tool.setdefault(tool, {"runs": 0, "failures": 0})
        bucket["runs"] += 1
        if row.get("status") != "success":
            bucket["failures"] += 1
    payload = {
        "updated_at": datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
        "retention_days": {"detail_logs": DETAIL_RETENTION_DAYS, "run_index": INDEX_RETENTION_DAYS},
        "recent_7d": {
            "total_runs": len(recent),
            "success_runs": sum(1 for row in recent if row.get("status") == "success"),
            "failed_runs": len(failures),
            "last_failure": failures[-1] if failures else None,
            "tools": by_tool,
        },
    }
    HEALTH_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def note_tool_output(payload: Any) -> None:
    logger = CURRENT_LOGGER.get()
    if logger is not None:
        logger.remember_output(payload)


def run_tool_main(tool_name: str, main_fn: Callable[[], Any], argv: list[str] | None = None) -> Any:
    logger = ToolRunLogger(tool_name, argv if argv is not None else sys.argv[1:])
    logger.start()
    token = CURRENT_LOGGER.set(logger)
    try:
        result = main_fn()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        status = "success" if code == 0 else "system_exit"
        logger.finalize(status=status, exit_code=code)
        raise
    except BaseException as exc:
        logger.finalize(
            status="exception",
            exit_code=1,
            error=exc,
            traceback_text=traceback.format_exc(),
        )
        raise
    else:
        logger.finalize(status="success", exit_code=0)
        return result
    finally:
        CURRENT_LOGGER.reset(token)
