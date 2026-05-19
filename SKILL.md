---
name: lang-drill-coach
description: Agent skill for language learning, exam prep, vocabulary drills, grammar drills, one-question-at-a-time quizzes, spaced repetition, wrong-answer review, syllabus import, and SQLite-backed progress tracking. Use when Codex, Claude Code, OpenClaw, Cursor, or OpenCode should coach Japanese, English, or another target-language exam by first creating a learner profile, then importing official/reliable syllabus assets, authoring exam-style practice, grading answers, and updating long-term review state.
---

# Lang Drill Coach

Use this skill from the repository root. A nested copy also lives at `skills/lang-drill-coach/`; this root file exists so GitHub, Hugging Face, `find-skill`, and manual installers can discover the skill immediately.

## First Run

1. Read `AGENTS.md` and `doc/项目局部规则.md`.
2. Run `py scripts/init_today.py`.
3. If the profile is incomplete, collect target language, exam or ability goal, current level, deadline, daily load, preferences, weak areas, vocabulary/grammar input method, and reminder needs.
4. Update `data/background/student_profile.md`.
5. If the syllabus is missing, import local official/reliable materials or search public sources, then record source name and year.

## Language And Exam Assets

- Japanese seeds are bundled: CJT4 2023 and high-school Japanese 2020.
- English has a ready entry folder at `data/kb/english/`.
- Other target languages are supported by copying `data/kb/language-template/` into a new exam folder and adding `official_vocab_YYYY.json`, `official_grammar_YYYY.json`, and `exam_blueprint_YYYY.json`.
- The core script automatically seeds JSON files matching `data/kb/*/official_vocab_*.json`, `data/kb/*/official_grammar_*.json`, `seed_vocab.json`, and `seed_grammar.json`.

## Daily Drill

1. Import learner material:
   - `py scripts/import_vocab.py --text "term|reading_or_pronunciation|meaning|pos|notes"`
   - `py scripts/import_grammar.py --text "pattern|meaning|usage|example|confusable_with"`
2. Select candidates:
   - `py scripts/select_session_content.py --target-minutes 35`
   - `py scripts/extract_background_candidates.py --target-minutes 35`
3. The agent writes the complete exam-style question set. Scripts select candidates and persist state; they are not the final question author.
4. Persist before showing questions:
   - `py scripts/persist_authored_session.py --input-json .\tmp\authored_session.json`
5. Present one question at a time as `第 N 题 / 共 M 题`.
6. Grade and write back immediately:
   - `py scripts/grade_answer.py --question-id <id> --user-answer "<answer>"`
7. Finish with reconciliation and audit:
   - `py scripts/reconcile_session.py --session-date YYYY-MM-DD`
   - `py scripts/audit_study_day.py --session-date YYYY-MM-DD --apply-status-fixes`

## Authoring Rules

- Match the chosen exam's real section style and difficulty.
- Use learner-owned material first, then due review, active review, wrong-answer callbacks, and syllabus fallback.
- Shuffle multiple-choice options before persistence.
- Verify the answer key, explanation, option plausibility, and knowledge tags before showing the first question.
- Keep real papers as reference/index assets unless their redistribution rights are clear.

## References

Read `skills/lang-drill-coach/references/commands.md` for exact commands. Read `skills/lang-drill-coach/references/workflow.md` for recovery and session flow.
