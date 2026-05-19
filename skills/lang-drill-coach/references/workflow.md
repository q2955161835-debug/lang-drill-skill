# Workflow

## First-Time Initialization

1. Run `scripts/init_today.py`.
2. If the learner profile is incomplete, collect:
   - target language
   - exam or ability goal
   - current level and learning history
   - deadline
   - daily question load or study time
   - preferences, weak areas, and reminder needs
   - preferred vocabulary/grammar entry method
3. Update `data/background/student_profile.md`.
4. Import or research the target exam syllabus. Record source name and year.
5. Convert vocabulary, grammar, and question-type ranges into structured assets under `data/kb/<exam-id>/`. Use `data/kb/language-template/README.md` for new language or exam schemas.
6. Ask whether to index recent real papers as reference material.

## Normal Session

1. Read the profile and latest progress.
2. Run initialization and report the panel.
3. Import new learner content, if any.
4. Run content selection and background extraction.
5. Author the full question set in exam style.
6. Persist the set with accurate `knowledge_tags`.
7. Use `session_status.py` to fetch the next pending question.
8. Ask one question at a time.
9. Grade each answer immediately and explain it.
10. Reconcile and audit when the set is complete.

## Recovery

- If context is lost, read `AGENTS.md`, `doc/项目局部规则.md`, latest `doc/进展记录.md`, and `data/background/student_profile.md`.
- Use `session_status.py` rather than chat memory to recover the active question.
- Use `logs/tool_runs.jsonl` and dated logs only for debugging; the database remains the formal state.

## Syllabus Notes

- Japanese CJT4 2023 and high-school Japanese 2020 assets are included as reusable seeds.
- English exam assets should be imported after the learner chooses an exam target.
- Other target languages can use the same database and review flow once their syllabus assets follow the template schema.
- File names should include the year, for example `official_vocab_2023.json`.
