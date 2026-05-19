# Publishing Checklist

## Discovery Rules We Optimize For

`find-skill` searches a local catalogue by `name`, `description`, and `tags`, filters by compatible agent, then sorts with source trust and GitHub stars. Its installer first checks for a root `SKILL.md`; if absent, it searches up to four levels deep and may pick the first match in a monorepo.

Therefore this project keeps:

- Root `SKILL.md` for direct installer detection.
- Keyword-rich frontmatter: `language learning`, `exam prep`, `vocabulary`, `grammar`, `spaced repetition`, `wrong-answer review`, `Japanese`, `English`, `Codex`, `Claude Code`.
- A short GitHub/Hugging Face README path for humans.
- Canonical source at `skills/lang-drill-coach/` for local Codex publishing.

## Before GitHub Or Hugging Face

- Confirm `git status --short` has only intentional changes.
- Confirm `.env` is not tracked and `.env.example` contains placeholders only.
- Confirm root `SKILL.md` exists and has valid frontmatter.
- Run sensitive-string scan for keys, tokens, cookies, private paths, and old personal traces.
- Run skill validation:

```powershell
$env:PYTHONUTF8='1'
python C:\Users\29551\.codex\skills\.system\skill-creator\scripts\quick_validate.py .\skills\lang-drill-coach
python C:\Users\29551\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
```

- Run script syntax check:

```powershell
py -m compileall -q scripts
```

## Publish Locally To Codex Skills

```powershell
py .\scripts\publish_skill.py
```

Expected target:

```text
D:\2Folder\skills\lang-drill-coach
```

## Publish To GitHub

```powershell
git push -u origin master
```

Recommended repository settings:

- Description: `Agent skill for language exam drills, syllabus import, spaced review, grading, and SQLite-backed progress tracking.`
- Website: Hugging Face mirror URL after upload.
- Topics: `agent-skill`, `skill-md`, `codex`, `claude-code`, `language-learning`, `exam-prep`, `spaced-repetition`, `vocabulary`, `grammar`, `japanese`, `english`, `sqlite`.

## Publish To Hugging Face

Install/update the official Hub client if needed:

```powershell
python -m pip install -U huggingface_hub
```

Login once with a token stored by the Hub client, not in this repo:

```powershell
hf auth login
```

Upload a synchronized public snapshot:

```powershell
python .\scripts\publish_huggingface.py --repo-id <namespace>/lang-drill-skill
```

The script respects the public boundary by ignoring `.env`, `try/`, `tmp/`, `logs/`, transient SQLite files, and `doc/进展记录.md`.

## Skill Marketplace Notes

- Skill name: `lang-drill-coach`
- Display name: `Lang Drill Coach`
- Short description: `Exam-style language drills with syllabus import, spaced review, grading, and progress write-back`
- Default prompt: `Use $lang-drill-coach to set up my target language exam, import the syllabus, and run a one-question-at-a-time drill session.`
- License: MIT License

## Known Publication Boundary

The repository includes Japanese syllabus/reference assets. Review third-party redistribution terms before uploading to public marketplaces that mirror bundled assets.
