# LangDrill Skill English Intro

LangDrill Skill is an agent skill for language exam preparation and long-term review. It helps Codex, Claude Code, OpenClaw, Cursor, or OpenCode build a learner profile, import syllabus assets, author exam-style drills, grade one question at a time, and update spaced-review state.

## Problem

One-off AI quizzes disappear into chat history. LangDrill keeps the useful state in a local SQLite database: learner goals, syllabus coverage, vocabulary, grammar, authored questions, attempts, mistakes, and future review dates.

## Included Assets

- Japanese: bundled CJT4 2023 and high-school Japanese 2020 resources.
- English: ready entry folder at `data/kb/english/`; import the selected exam syllabus before formal drills.
- Other target languages: copy `data/kb/language-template/`, add vocabulary, grammar, and an exam blueprint, then use the same workflow.

## What Users Need To Configure

Some fields intentionally remain marked as `待确认` or pending. They are not unfinished implementation defects. They are first-run configuration slots that must be filled by the actual learner or maintainer.

Main configurable areas include:

- `data/background/student_profile.md`: learner profile, including target language, exam goal, exam date, daily load, current level, weak areas, and preferences.
- `data/kb/<exam-id>/`: target exam assets, including vocabulary, grammar, exam blueprint, source year, and source scope.
- Learner-owned material: currently studied vocabulary, grammar patterns, textbook excerpts, mistakes, or teacher-assigned content.
- Review and drill preferences: daily study time, question count, section ratio, reminder needs, explanation depth, and wrong-answer callback strength.

In short, LangDrill provides a reusable drill system. The concrete language, exam target, workload, and source materials are meant to be configured per user.

## Quick Start

```powershell
git clone https://github.com/q2955161835-debug/lang-drill-skill.git
cd lang-drill-skill
py .\scripts\init_today.py
```

After initialization, fill `data/background/student_profile.md`. If you see `待确认`, replace it with your actual learning target instead of treating it as a project defect.

Then import a first item:

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

## Configuration And Privacy Boundary

- Templates may be public; real learner profiles, actual progress, private wrong-answer records, and local logs should not be published.
- `.env`, real tokens, cookies, database passwords, and private endpoints must not be written into README files, examples, progress notes, or copyable chat snippets.
- Real papers and textbook materials should default to indexes or source notes. Do not publish full copyrighted exam text unless redistribution rights are clear.

## Good Fit

- Learners who want an AI agent as a persistent exam coach.
- People drilling vocabulary, grammar, reading, listening, or integrated sections from a syllabus.
- Users who want recoverable progress instead of scattered chat transcripts.
- Maintainers who want to turn local learning materials into a reusable drill workflow.

## License

MIT License. Keep the copyright and license notice when copying, modifying, distributing, or using commercially.
