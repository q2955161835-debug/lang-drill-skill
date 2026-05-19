# LangDrill Skill English Intro

LangDrill Skill is an agent skill for language exam preparation and long-term review. It helps Codex, Claude Code, OpenClaw, Cursor, or OpenCode build a learner profile, import syllabus assets, author exam-style drills, grade one question at a time, and update spaced-review state.

## Problem

One-off AI quizzes disappear into chat history. LangDrill keeps the useful state in a local SQLite database: learner goals, syllabus coverage, vocabulary, grammar, authored questions, attempts, mistakes, and future review dates.

## Included Assets

- Japanese: bundled CJT4 2023 and high-school Japanese 2020 resources.
- English: ready entry folder at `data/kb/english/`; import the selected exam syllabus before formal drills.
- Other target languages: copy `data/kb/language-template/`, add vocabulary, grammar, and an exam blueprint, then use the same workflow.

## Quick Start

```powershell
git clone https://github.com/q2955161835-debug/lang-drill-skill.git
cd lang-drill-skill
py .\scripts\init_today.py
```

Fill `data/background/student_profile.md`, then import a first item:

```powershell
py .\scripts\import_vocab.py --text "example|pronunciation|meaning|noun|first item"
py .\scripts\select_session_content.py --target-minutes 20
```

Publish to the local Codex skills directory:

```powershell
py .\scripts\publish_skill.py
```

## Workflow

1. Create a learner profile.
2. Import syllabus, vocabulary, grammar, or real-paper indexes.
3. Let scripts select candidate knowledge points.
4. Let the agent write a complete exam-style question set.
5. Persist the set before showing questions.
6. Ask one question at a time.
7. Grade immediately and write back state.
8. Reconcile mastery and audit the study day.

## Good Fit

- Learners who want an AI agent as a persistent exam coach.
- People drilling vocabulary, grammar, reading, listening, or integrated sections from a syllabus.
- Users who want recoverable progress instead of scattered chat transcripts.
- Maintainers who want to turn local learning materials into a reusable drill workflow.

## License

MIT License. Keep the copyright and license notice when copying, modifying, distributing, or using commercially.
