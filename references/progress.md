# 查看进度

1. 运行脚本（把 `<ARTIFACT_DIR>` 换成当前对话的 artifact 目录）：

   ```
   python "C:\Users\Administrator\.gemini\config\skills\learning-coach\scripts\progress.py" --today <今天 YYYY-MM-DD> --html "<ARTIFACT_DIR>\learning_progress.html"
   ```
   - 只看某个目标时加 `--goal <slug>`；需要结构化数据时加 `--json`。
   - stdout 是文字摘要，其中包括 **过期未完成的周目标** 和 **本月是否还没细化周目标**。「开始学习」时也可以只运行脚本（不加 `--html`），用来做偏离检查。

2. 在回复中内联嵌入面板：

   ```
   <agent-embed src="file:///<ARTIFACT_DIR 用正斜杠>/learning_progress.html"></agent-embed>
   ```

3. 面板下面用 2~4 句话点评：本周完成情况、需要处理的偏离（按 [planning.md](./planning.md) 第 4 节）、下次学习建议。保持客观，不催促。

脚本解析失败（数据明显不对）时，检查 plan.md / syllabus.md 是否偏离了模板的标记格式，修正后重新运行。
