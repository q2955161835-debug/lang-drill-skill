# lang-drill-skill

通用语言学习刷题 skill，让 Codex、OpenClaw、Claude Code 等智能体变成可维护学习进度的语言学习助手。

它会根据目标语言、考试目标、学习背景、考纲范围、当前掌握情况和复习算法，生成考试风格练习题，逐题判分讲解，并把词汇、语法、错题和下次复习时间写回本地数据库。

## 当前状态

- 支持方向：日语、英语。
- 已内置日语资料：大学日语四级 2023 考纲、高中日语 2020 课程/词法资源。
- 英语资料：预留 `data/kb/english/`，需要在用户确认考试目标后导入对应考纲。
- 个人历史：已清空。模板数据库只保留可复用考纲与资料索引。

## Skill 入口

项目内 skill 源码：

```text
skills/lang-drill-coach/
```

同步到本机 Codex skills 目录：

```powershell
py .\scripts\publish_skill.py
```

## 首次使用流程

1. 运行初始化：

```powershell
py .\scripts\init_today.py
```

2. 补齐学习者档案：

```text
data/background/student_profile.md
```

3. 导入或搜索目标考试考纲，并把词汇、语法、题型等结构化到 `data/kb/<exam-id>/`。

4. 导入当天新词或语法：

```powershell
py .\scripts\import_vocab.py --text "term|reading_or_pronunciation|meaning|pos|notes"
py .\scripts\import_grammar.py --text "pattern|meaning|usage|example|confusable_with"
```

5. 生成候选，agent 编写完整题单后落库：

```powershell
py .\scripts\select_session_content.py --target-minutes 35
py .\scripts\extract_background_candidates.py --target-minutes 35
py .\scripts\persist_authored_session.py --input-json .\tmp\authored_session.json
```

6. 逐题练习与判分：

```powershell
py .\scripts\session_status.py
py .\scripts\grade_answer.py --question-id 1 --user-answer A
```

## 目录说明

- `skills/lang-drill-coach/`：skill 源码。
- `scripts/`：导入、选材、落库、判题、复习校准和发布脚本。
- `data/study.db`：本地学习数据库。
- `data/kb/`：考纲、词表、真题索引和资料源。
- `data/background/student_profile.md`：学习者档案模板。
- `doc/进展记录.md`：阶段进展记录。
- `assets/cover.png`：发布封面素材。

## 许可证

本项目采用 Creative Commons Attribution-NonCommercial 4.0 International License（CC BY-NC 4.0）。

你可以在非商业目的下共享和改编本项目，但必须按许可证要求保留署名、许可证链接，并标明是否作出修改。未经额外授权，不得将本项目用于商业目的。详见 `LICENSE` 与 `ATTRIBUTION.md`。
