# LangDrill Skill

![LangDrill Skill cover](assets/cover.png)

LangDrill Skill turns Codex, Claude Code, OpenClaw, Cursor, or OpenCode into a persistent language exam coach. It creates a learner profile, imports syllabus assets, writes exam-style drills, asks one question at a time, grades answers, and stores review state in SQLite.

LangDrill Skill 是一个可长期维护进度的语言刷题 skill：先建档，再导入考纲，随后生成考试风格练习、逐题判题、回写复习状态和错题记录。

- Chinese intro: [README.zh-CN.md](README.zh-CN.md)
- English intro: [README.en.md](README.en.md)
- Skill entry: [SKILL.md](SKILL.md)
- Canonical skill folder: [skills/lang-drill-coach/](skills/lang-drill-coach/)

## Why It Exists

Most AI language drills vanish into chat history. LangDrill keeps the boring but important state: what the learner knows, what is due, which syllabus range is covered, which questions were missed, and what should come back later.

## Quick Start

```powershell
git clone https://github.com/q2955161835-debug/lang-drill-skill.git
cd lang-drill-skill
py .\scripts\init_today.py
```

Then fill `data/background/student_profile.md` and import the first vocabulary or grammar item:

```powershell
py .\scripts\import_vocab.py --text "example|pronunciation|meaning|noun|first item"
py .\scripts\select_session_content.py --target-minutes 20
```

For Codex local skill discovery:

```powershell
py .\scripts\publish_skill.py
```

Default local target:

```text
D:\2Folder\skills\lang-drill-coach
```

Hugging Face mirror upload, after `hf auth login` or another local Hub token setup:

```powershell
python .\scripts\publish_huggingface.py --repo-id <namespace>/lang-drill-skill
```

## Install As A Skill

This repository has a root `SKILL.md` so installers can find it without monorepo guessing.

Manual install:

```powershell
git clone https://github.com/q2955161835-debug/lang-drill-skill.git
```

With `find-skill`, search keywords such as `language drill`, `exam prep`, `vocabulary`, `grammar`, `spaced repetition`, `Japanese`, `English`, `Codex`, or `Claude Code`.

## Supported Targets

- Japanese: bundled CJT4 2023 and high-school Japanese 2020 assets.
- English: ready `data/kb/english/` entry; import the chosen exam syllabus before formal drills.
- Other target languages: copy `data/kb/language-template/`, add official/reliable vocabulary, grammar, and exam-blueprint files, then use the same workflow.

## Core Flow

1. Initialize learner profile with `scripts/init_today.py`.
2. Import syllabus and learner material into `data/kb/<exam-id>/` and `data/study.db`.
3. Select candidates with `select_session_content.py`.
4. Let the agent author a complete question set.
5. Persist it with `persist_authored_session.py`.
6. Ask one question at a time.
7. Grade with `grade_answer.py`.
8. Reconcile and audit the session.

## Repository Map

- `SKILL.md`: root entry for GitHub, Hugging Face, and skill installers.
- `skills/lang-drill-coach/`: canonical skill source.
- `scripts/`: import, selection, persistence, grading, review, audit, and publishing utilities.
- `data/kb/`: reusable syllabus and exam assets.
- `data/kb/language-template/`: template for adding a new language or exam.
- `data/study.db`: SQLite state store.
- `doc/`: project rules, progress notes, wrong-answer notebook, and human-readable logs.

## Publication Boundary

Public releases should not include real `.env` values, personal study history, private logs, private notes, or unreleased copyrighted exam text. The repository keeps templates and reusable syllabus indexes only.

## License

MIT License. Keep the copyright and license notice when copying or redistributing.
