# Publishing Checklist

## Before GitHub

- Confirm `git status --short` is clean.
- Confirm `.env` does not exist in Git and `.env.example` contains placeholders only.
- Run sensitive-string scan for keys, tokens, cookies, private paths, and old personal traces.
- Run skill validation:

```powershell
$env:PYTHONUTF8='1'
& "C:\Users\29551\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" `
  C:\Users\29551\.codex\skills\.system\skill-creator\scripts\quick_validate.py `
  .\skills\lang-drill-coach
```

- Run script syntax check:

```powershell
py -m compileall -q scripts
```

## Publish Locally To Codex Skills

```powershell
py .\scripts\publish_skill.py
```

Expected target:

```text
D:\2Folder\skills\lang-drill-coach
```

## Publish To GitHub

Create a repository, add it as `origin`, then push:

```powershell
git remote add origin <github-repo-url>
git branch -M main
git push -u origin main
```

## Skill Marketplace Notes

- Use `skills/lang-drill-coach/` as the canonical skill folder.
- Display name: `语言刷题教练`
- Short description: `根据考纲、学习背景和复习状态生成语言学习测验并回写进度`
- Default prompt: `Use $lang-drill-coach to initialize my language-learning goal, import the syllabus, and run an exam-style drill session.`
- License: MIT License

## Known Publication Boundary

The repository includes Japanese syllabus/reference assets. Review third-party redistribution terms before uploading to public marketplaces that mirror bundled assets.
