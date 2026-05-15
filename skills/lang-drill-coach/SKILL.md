---
name: lang-drill-coach
description: Universal language-learning drill coach for agentic coding assistants. Use when Codex/OpenClaw/Claude Code should become a language tutor that initializes a learner profile, imports or researches exam syllabi, stores vocabulary and grammar ranges, generates exam-style practice questions, runs one-question-at-a-time quizzes, grades answers, updates spaced-review state, maintains wrong-answer records, and supports Japanese or English exam preparation from a local SQLite-backed project.
---

# Lang Drill Coach

## Purpose

Use this skill inside the `lang-drill-skill` project to turn an agent into a language-learning assistant. The agent owns teaching quality; scripts own structured storage, scheduling, grading write-back, logs, and recovery.

Default supported languages:
- Japanese: reusable CJT4 2023 and high-school Japanese 2020 syllabus assets are bundled.
- English: create or import a target exam syllabus before formal drills.

## Startup Checklist

Before generating questions or touching learning data:
1. Read `AGENTS.md`.
2. Read `doc/项目局部规则.md`.
3. Read the latest entry in `doc/进展记录.md`.
4. Read `data/background/student_profile.md`.
5. Run `py scripts/init_today.py` from the project root and report its initialization panel.
6. If profile fields are incomplete, ask for: target language, exam/ability goal, current background, deadline, daily question load, preferences, current mastery, vocabulary-entry method, and reminder needs.
7. If the exam syllabus is missing, ask whether to import local files or search official/public sources. Record syllabus year in the imported asset path or notes.
8. Ask whether to collect/import recent real papers for question-type reference.

## Syllabus Workflow

Use official or reliable public materials whenever possible.

1. Place raw local materials in `data/kb/material-inbox/`.
2. Convert syllabus vocabulary and grammar into structured JSON/CSV under `data/kb/<exam-id>/`.
3. Import structured ranges into `data/study.db` with non-`user` `source_scope` values such as `cjt4`, `gaokao`, `cet4`, `ielts`, `toefl`, or another exam id.
4. Mark each syllabus file with the exam name and year, for example `official_vocab_2023.json`.
5. Define the target question types before generating drills. For Japanese CJT4, keep the bundled Japanese section shapes; for English exams, infer or import section shapes from the chosen exam.
6. Keep real papers as reference/index assets, not as default generated-question output.

## Daily Drill Workflow

1. Import learner input:
   - Vocabulary: `py scripts/import_vocab.py --text "term|reading_or_pronunciation|meaning|pos|notes"`
   - Grammar: `py scripts/import_grammar.py --text "pattern|meaning|usage|example|confusable_with"`
   - Prepared JSON/CSV files are accepted through the same import scripts.
2. Select content before authoring:
   - `py scripts/select_session_content.py --target-minutes 35`
   - `py scripts/extract_background_candidates.py --target-minutes 35`
3. Author the complete question set in the agent. Scripts may select candidates but must not be trusted as final question writers.
4. Persist authored questions before showing them:
   - `py scripts/persist_authored_session.py --input-json .\tmp\authored_session.json`
5. Recover the active session:
   - `py scripts/session_status.py`
6. Present one question at a time as `第 N 题 / 共 M 题`.
7. Grade each answer immediately:
   - `py scripts/grade_answer.py --question-id <id> --user-answer "<answer>"`
8. Explain correctness, review linked knowledge, and ask whether to continue.
9. When the session finishes, run:
   - `py scripts/reconcile_session.py --session-date YYYY-MM-DD`
   - `py scripts/audit_study_day.py --session-date YYYY-MM-DD --apply-status-fixes`
10. At a phase boundary, append a progress snapshot with `py scripts/sync_progress_snapshot.py`.

## Question Authoring Rules

- Match the chosen exam's real section style and difficulty.
- Prefer questions that cover multiple vocabulary/grammar points when clarity remains high.
- Use learner-known content first, then due review, active review, wrong-answer callbacks, and finally syllabus fallback.
- Use syllabus fallback to fill coverage or section requirements; do not let it dominate when user content is available.
- Keep grouped reading/listening/dialogue materials contiguous in the stored session.
- Shuffle multiple-choice options before persistence.
- Verify the answer key, explanation, option plausibility, and knowledge tags before showing the first question.
- Do not dump the full set into chat; the database is the formal source.

## Review Algorithm Rules

Use the database state as the formal memory:
- New user content starts with empty/low mastery unless imported with explicit mastery evidence.
- Content learned before this skill was initialized should get a conservative onboarding review plan because exact first-study dates are unknown.
- After every answer, write attempts, question status, linked vocabulary/grammar mastery, mistake records, and next due dates immediately.
- Wrong answers stay open until reviewed through later drills.

## Commands Reference

Read `references/commands.md` when command syntax is needed. Read `references/workflow.md` when the session flow or recovery flow is unclear.

## Publishing

The project-local source of truth is `skills/lang-drill-coach/`.
To sync it to the external skills folder:

```powershell
py scripts/publish_skill.py
```
