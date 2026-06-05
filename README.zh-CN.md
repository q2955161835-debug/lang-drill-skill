# LangDrill Skill 中文简介

当前版本：`0.2.0`。

LangDrill Skill 是一个面向语言考试和长期复习的 agent skill。它让 Codex、Claude Code、OpenClaw、Cursor 或 OpenCode 先了解学习者目标，再围绕考纲、已学内容、错题和复习周期生成训练。

## 它解决什么问题

普通 AI 刷题往往只是在聊天里临时出几道题，做完就散了。LangDrill 把学习档案、考纲范围、词汇语法、题单、作答、错题、复习时间都放进本地 SQLite，方便跨会话恢复和长期追踪。

## 已有内容

- 日语：内置大学日语四级 2023 考纲和高中日语 2020 课程/词法资源。
- 英语：内置高考英语 2020 课标词汇/语法范围、大学英语四级/六级 2016 大纲词表、题型蓝图和近三年试卷索引。
- 其他目标语言：复制 `data/kb/language-template/`，按模板加入词汇、语法和考试题型蓝图即可进入同一套流程。

## 用户需要自定义什么

本项目故意保留了一些 `待确认` 字段。它们不是未完成实现，也不是错误，而是首次使用时必须由具体学习者填写的配置插槽。

主要自定义项包括：

- `data/background/student_profile.md`：学习者档案，例如目标语言、考试目标、考试时间、每日题量、当前水平、薄弱项和偏好。
- `data/kb/<exam-id>/`：目标考试资料，例如词汇表、语法表、题型蓝图、来源年份和来源范围。
- 用户材料：自己正在背的词、正在学的语法、教材摘录、错题或老师要求掌握的内容。
- 复习与训练偏好：每日学习时长、题量、题型比例、是否需要提醒、讲解深度和错题回流强度。

换句话说，LangDrill 提供的是一套可复用的刷题系统；具体练哪门语言、考什么试、按什么强度练，需要由使用者完成初始化配置。

## 最快上手

```powershell
git clone https://github.com/q2955161835-debug/lang-drill-skill.git
cd lang-drill-skill
py .\scripts\init_today.py
```

运行初始化后，先补齐 `data/background/student_profile.md`。如果看到 `待确认`，请按自己的学习目标改写，不需要把它当成项目缺陷。

如果需要把设置恢复到首次使用模板：

```powershell
py .\scripts\restore_default_settings.py
```

该命令会备份原 `data/background/student_profile.md` 到 `D:\0文件夹\备份\lang-drill-settings-YYYYMMDD_HHMM\`，然后只恢复学习者档案默认设置，不清空 `data/study.db`。

如需用 Mimo 测试 agent 做连通性验证：

```powershell
py .\scripts\mimo_agent_smoke_test.py --api-key-file "D:\0文件夹\API key\mimo.txt"
```

脚本默认使用 `mimo-v2.5`，也可通过 `.env` 中的 `MIMO_API_KEY`、`MIMO_BASE_URL`、`MIMO_MODEL` 配置；真实 key 不会打印，也不要提交。

随后导入一条材料：

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

## 配置与隐私边界

- 模板字段可以公开；真实学习档案、真实学习进度、私人错题和本地日志不应进入公开发布分支。
- `.env`、真实 token、cookie、数据库密码和私有地址禁止写进 README、示例文件或进展记录。
- 真题和教材默认只建立索引或来源说明；除非授权明确，不应把完整试题全文作为默认资产发布。

## 适合谁

- 想把 AI agent 变成私人语言学习教练的人。
- 需要围绕考纲刷词汇、语法、阅读、听力或综合题的人。
- 希望练习可恢复、可追踪、可复习的人。
- 想把自己的本地资料整理成可复用训练流程的人。

## 许可证

MIT License。复制、修改、分发或商业使用时保留版权和许可证声明即可。
