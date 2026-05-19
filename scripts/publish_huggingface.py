from __future__ import annotations

import argparse
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload the public LangDrill Skill repository snapshot to Hugging Face Hub.")
    parser.add_argument("--repo-id", default=os.environ.get("HF_REPO_ID", ""), help="Target Hub repo, for example username/lang-drill-skill.")
    parser.add_argument("--repo-type", default=os.environ.get("HF_REPO_TYPE", "model"), choices=["model", "dataset", "space"])
    parser.add_argument("--private", action="store_true", help="Create the Hub repo as private if it does not exist.")
    parser.add_argument("--commit-message", default="sync LangDrill Skill")
    args = parser.parse_args()

    if not args.repo_id:
        raise SystemExit("Missing --repo-id or HF_REPO_ID.")

    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise SystemExit("Install huggingface_hub first: python -m pip install -U huggingface_hub") from exc

    api = HfApi()
    try:
        api.create_repo(repo_id=args.repo_id, repo_type=args.repo_type, private=args.private, exist_ok=True)
    except Exception as exc:
        raise SystemExit(
            "Hugging Face upload needs a local Hub token. Run `hf auth login`, "
            "set `HF_TOKEN`, or use `huggingface_hub.login()` before retrying."
        ) from exc
    api.upload_folder(
        repo_id=args.repo_id,
        repo_type=args.repo_type,
        folder_path=ROOT,
        commit_message=args.commit_message,
        ignore_patterns=[
            ".git/*",
            ".env",
            ".env.*",
            "try/*",
            "tmp/*",
            "logs/*",
            "__pycache__/*",
            "*.pyc",
            ".pytest_cache/*",
            "data/study.db-shm",
            "data/study.db-wal",
            "doc/进展记录.md",
        ],
    )
    print(f"Uploaded {ROOT} to https://huggingface.co/{args.repo_id}")


if __name__ == "__main__":
    main()
