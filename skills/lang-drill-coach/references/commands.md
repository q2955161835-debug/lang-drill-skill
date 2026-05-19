# Commands

Run commands from the project root.

## Initialize

```powershell
py .\scripts\init_today.py
```

## Import Vocabulary

```powershell
py .\scripts\import_vocab.py --text "term|reading_or_pronunciation|meaning|pos|notes"
```

Use `--source-scope user` for learner-owned material. Use an exam id such as `cjt4`, `gaokao`, `cet4`, `ielts`, or `toefl` for syllabus material.

## Import Grammar

```powershell
py .\scripts\import_grammar.py --text "pattern|meaning|usage|example|confusable_with"
```

## Import Prepared Files

```powershell
py .\scripts\import_vocab.py --file .\data\kb\<exam-id>\official_vocab_YYYY.json --source-scope <exam-id> --source-type syllabus
py .\scripts\import_grammar.py --file .\data\kb\<exam-id>\official_grammar_YYYY.json --source-scope <exam-id> --source-type syllabus
```

For a new language or exam, copy the schemas from `data/kb/language-template/README.md`. JSON files named `official_vocab_*.json`, `official_grammar_*.json`, `seed_vocab.json`, or `seed_grammar.json` are automatically seeded when the database initializes.

## Select And Author A Session

```powershell
py .\scripts\select_session_content.py --target-minutes 35
py .\scripts\extract_background_candidates.py --target-minutes 35
py .\scripts\persist_authored_session.py --input-json .\tmp\authored_session.json
py .\scripts\session_status.py
```

`generate_session.py` is intentionally disabled. The agent must write the final prompts, then persist them.

## Grade And Reconcile

```powershell
py .\scripts\grade_answer.py --question-id 1 --user-answer A
py .\scripts\reconcile_session.py --session-date 2026-05-15
py .\scripts\audit_study_day.py --session-date 2026-05-15 --apply-status-fixes
```

## Progress Snapshot

```powershell
py .\scripts\sync_progress_snapshot.py `
  --title "阶段标题" `
  --completed "完成事项" `
  --files "文件与用途" `
  --next-steps "下一步"
```

## Publish Skill

```powershell
py .\scripts\publish_skill.py
```

## Publish Hugging Face Mirror

```powershell
py .\scripts\publish_huggingface.py --repo-id <namespace>/lang-drill-skill
```
