# Language Knowledge Base Template

Use this directory as a copyable template for any target language or exam. Create a new sibling folder such as `cet4/`, `jlpt-n2/`, `dele-a2/`, or `topik-ii/`, then keep the same file shapes below.

## Required Naming

- `official_vocab_YYYY.json` or `official_vocab_YYYY.csv`
- `official_grammar_YYYY.json` or `official_grammar_YYYY.csv`
- `exam_blueprint_YYYY.json`
- `README.md` with source name, source URL or local source file, year, and scope notes

`scripts/study_core.py` automatically seeds JSON files matching `data/kb/*/official_vocab_*.json`, `data/kb/*/official_grammar_*.json`, `seed_vocab.json`, and `seed_grammar.json`.

## Vocabulary Schema

```json
[
  {
    "term": "example",
    "reading": "optional pronunciation, kana, pinyin, IPA, or transliteration",
    "meaning": "brief meaning in the learner's explanation language",
    "pos": "part of speech",
    "source_scope": "exam-id",
    "source_type": "official_syllabus_YYYY",
    "difficulty": 2,
    "notes": "source and coverage notes"
  }
]
```

## Grammar Schema

```json
[
  {
    "pattern": "target structure",
    "meaning_cn": "brief meaning or function",
    "core_usage": "usage constraints and common context",
    "example": "one short example sentence",
    "source_scope": "exam-id",
    "source_type": "official_syllabus_YYYY",
    "difficulty": 2,
    "confusable_with": "",
    "notes": "source and coverage notes"
  }
]
```

## Exam Blueprint Schema

```json
{
  "exam_id": "exam-id",
  "language": "target language",
  "year": 2026,
  "sections": [
    {
      "name": "Vocabulary and grammar",
      "question_types": ["multiple_choice", "fill_blank", "sentence_rewrite"],
      "default_ratio": 0.4,
      "notes": "Use only after the source is verified."
    }
  ]
}
```
