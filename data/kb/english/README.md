# English Knowledge Base

This directory is the ready entry point for English exam syllabi and reference materials.

Create one subdirectory or file set per exam after the learner chooses a target, for example:

- `cet4/official_vocab_YYYY.json`
- `ielts/official_vocab_YYYY.json`
- `toefl/official_grammar_YYYY.json`
- `exam_blueprint_YYYY.json`

Use `data/kb/language-template/README.md` for the exact JSON/CSV shape. The core scripts automatically seed any JSON files named `official_vocab_*.json`, `official_grammar_*.json`, `seed_vocab.json`, or `seed_grammar.json` under `data/kb/*/`.

Record the source name, year, and `source_scope` in every structured asset.
