# LangDrill Skill 中文简介

LangDrill Skill 是一个面向语言考试和长期复习的 agent skill。它让 Codex、Claude Code、OpenClaw、Cursor 或 OpenCode 先了解学习者目标，再围绕考纲、已学内容、错题和复习周期生成训练。

## 它解决什么问题

普通 AI 刷题往往只是在聊天里临时出几道题，做完就散了。LangDrill 把学习档案、考纲范围、词汇语法、题单、作答、错题、复习时间都放进本地 SQLite，方便跨会话恢复和长期追踪。

## 已有内容

- 日语：内置大学日语四级 2023 考纲和高中日语 2020 课程/词法资源。
- 英语：提供 `data/kb/english/` 入口，确认考试目标后导入对应考纲。
- 其他目标语言：复制 `data/kb/language-template/`，按模板加入词汇、语法和考试题型蓝图即可进入同一套流程。

## 最快上手

```powershell
git clone https://github.com/q2955161835-debug/lang-drill-skill.git
cd lang-drill-skill
py .\scripts\init_today.py
```

补齐 `data/background/student_profile.md` 后，先导入一条材料：

```powershell
py .\scripts\import_vocab.py --text "example|pronunciation|meaning|noun|first item"
py .\scripts\select_session_content.py --target-minutes 20
```

本机 Codex skill 同步：

```powershell
py .\scripts\publish_skill.py
```

## 核心流程

1. 建立学习者档案。
2. 导入考纲、词汇、语法或真题索引。
3. 脚本选择候选知识点。
4. Agent 编写整套考试风格题单。
5. 题单先落库，再逐题展示。
6. 每答一题立即判题、讲解、回写状态。
7. 会话结束后校准熟练度并审计当天数据。

## 适合谁

- 想把 AI agent 变成私人语言学习教练的人。
- 需要围绕考纲刷词汇、语法、阅读、听力或综合题的人。
- 希望练习可恢复、可追踪、可复习的人。
- 想把自己的本地资料整理成可复用训练流程的人。

## 许可证

MIT License。复制、修改、分发或商业使用时保留版权和许可证声明即可。
