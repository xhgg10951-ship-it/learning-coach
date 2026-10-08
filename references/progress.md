# 当前学习位置与只读进度

## 日常读取

在 Skill 根目录运行：

```shell
python scripts/learning.py --hub ./learning-hub-demo current
python scripts/learning.py --hub ./learning-hub-demo list
python scripts/learning.py --hub ./learning-hub-demo list --goal java-backend
python scripts/learning.py --hub ./learning-hub-demo show --goal java-backend --track spring-boot
```

`current` 按 `state/active.json` 找到用户选择；`select` 才修改这个指针。当前目标未指定 Track 时，先展示必要的领域摘要，不猜测用户意图。正常处理仅读取当前 Goal 和 Track；明确请求全局概览或排错时再全库读取。

说明当前 Milestone/Sprint 的目标、验收标准、状态与剩余能力即可。列出已完成、跳过和提前结束的记录时保留区别，不以完成条数或预计学时计算“掌握率”，不提出日期触发的重排。

## 文本、JSON 与 HTML

`progress.py` 是只读报告接口，支持新版结构和旧版兼容读取：

```shell
python scripts/progress.py --hub ./learning-hub-demo --goal java-backend --track spring-boot
python scripts/progress.py --hub ./learning-hub-demo --json
python scripts/progress.py --hub ./learning-hub-demo --html ./artifacts/learning-progress.html
```

`--track` 必须同时指定 `--goal`。`--today YYYY-MM-DD` 仅指定报告展示日期，不推进任务。HTML 是诚实的状态摘要，不是新的 Web 系统，不输出虚假的掌握统计。报告输出放在数据目录之外，不能把 HTML 输出路径指向 hub 中的文件。同时使用 `--json --html` 时，标准输出保持纯 JSON，HTML 提示写入标准错误。

用当前环境支持的文件链接或文件预览展示 HTML，不要求特定聊天产品的嵌入标签。反馈聚焦当前能力要求和用户可以选择的下一步，不催促。

## 旧版数据与错误

旧版 `goal.md`、`plan.md`、`syllabus.md` 和 Goal 级 `sessions/` 保留只读兼容。报告会标明 legacy 与警告：旧复选框只是原记录标记，不证明已掌握；旧月份和 ISO 周只用于解释原文，不触发延期、顺延或状态写入。新旧目标可出现在同一报告中，但不能把旧记录当作新版状态解析。

发现非法状态、重复 ID、缺失说明文件、损坏 JSON 或孤儿文件时明确报错，不静默跳过并输出看似完整的统计，也不“修正模板”覆盖原数据。

```shell
python scripts/learning.py --hub ./learning-hub-demo validate
```

`validate` 检查整个新版数据结构。旧数据兼容不是自动迁移；遇到旧格式、混合格式或无法安全判断的情况，保留原文件，并按 [架构文档的兼容方案](../docs/architecture.md#兼容与迁移) 在独立新目录人工确认后建立结构。
