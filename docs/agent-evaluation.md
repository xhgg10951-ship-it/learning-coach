# Phase 2B 真实 Agent 教学验收

离线测试证明存储和投影行为；不能证明 Agent 的教学选择。真实验收须同时保留输入、实际响应、工具执行、Session 文件和行为审查，不能根据 Skill 中出现“自适应”或模式字段存在就判通过。

## 复现入口

使用 Python 3.10+ 和已登录的 Codex CLI。运行时使用用户现有模型设置，不自动切换账户、模型或购买额度。测试只复制项目的 Skill/脚本/文档，创建独立合成学生 Hub，不读取正式学习 Hub。

```text
python -B -m unittest discover -s tests -v
python -B tests/run_agent_scenarios.py --out .test-tmp/phase2b-live-new
```

输出目录必须是新路径，避免覆盖前一次验收记录。可用 `--scenario arraylist`、`--scenario mysql`、`--scenario english` 或 `--scenario theory` 缩小范围；可重复指定。`--prepare-only` 只准备本地夹具，不调用 Agent。Windows 受限进程可能无法访问 Python 创建的临时目录，需要在具备正常临时目录权限的执行环境运行；不要改存储安全校验来绕过。

场景数据位于 [agent_scenarios.json](../tests/agent_scenarios.json)。ArrayList 包含 11 个顺序用户输入，另有 MySQL、英语、理论各一轮，共 14 轮。历史与学生回答都是合成测试材料，不代表真实用户已经掌握；教师响应必须来自实际 Agent 调用。

CLI 运行器每轮使用 fresh ephemeral Agent 和之前的实际对话消息，测试可持续读取其真实写入的 Hub。fresh 标志的第 10 轮不传之前聊天消息，只提供 Hub 和新请求，检验跨对话恢复。教师看不到断言或验收期望。模型行为具有随机性，重复运行不保证措辞一致。

## 保存的原始材料

- `manifest.json`：执行环境和 Skill/脚本/场景输入的 SHA-256。
- `initial-context.json`：初始合成画像及历史证据。
- `turn-NN.prompt.txt` / `.response.txt`：真实输入与实际输出。
- `turn-NN.events.jsonl` / `.stderr.txt`：工具执行及调用诊断，包含来源与失败证据。
- `turn-NN.context.json`：该轮实际保存后的教学状态与证据。
- `transcript.json`：可直接检查的多轮问答和结构断言结果。
- `workspace/hub`：实际 Session、笔记与检查点；不作为正式学习数据导入。

服务失败、额度限制、缺失输出、保存错误或场景未执行都不能计为通过。脚本失败返回非零码并保留已有输出；修复后用新目录重跑。`summary.json` 只汇总结构断言，behavior_review 必须另行检查真实响应，不能仅凭该文件宣布教学验收完成。

也可使用当前工具环境提供的独立 Agent 运行同一份场景：加载隔离工作区 Skill，以真实消息逐轮送入用户输入，在每轮后运行相同 `check_state`，保存实际响应及来源 Agent 标识。必须明确报告这与 CLI 自动运行的区别；不能把手工写出的理想回复当作独立 Agent 输出。

独立 Agent 路径允许同一个教师连续处理非 fresh 轮次；第 10 轮必须换没有继承聊天历史的教师，只读 Hub 恢复。教师只得到 Skill、合成 Hub 和本轮原始用户消息，不提供 `checks` 或行为审查表。按任务难度选择模型与推理强度，并在结果清单记录实际配置；未暴露配置的继承模型如实记为未知。

CLI 输出包含完整事件流和诊断文件。独立 Agent 的工具操作保留在原执行会话中，仓库中的可移植交付包含实际响应、每轮状态观察、最终权威 Hub 和源码哈希，**不等同于完整 CLI 工具轨迹导出**。人工行为审查应与结构断言分开记录，不能仅靠 `--native-completed` 标志证明教学可靠。

独立 Agent 每轮成功返回后，可用 `--out <已准备目录> --scenario arraylist --native-turn 1 --native-agent <来源标识> --native-completed` 收集该轮 `workspace/agent-turn-01.json`，执行同一组状态断言。仅存在该文件不代表 Agent 已完成：它可能是中断前准备的候选回复。调用者必须实际观察到最终成功返回；服务中断或未提交的候选另行保留，重试原始消息，不能计为通过。此标志和来源标识是审查元数据，并非加密认证。

## 行为审查标准

| 要求 | 对应输入 | 观察实际行为 |
|---|---|---|
| 有基础不从零开始 | ArrayList 1 | 利用已有基础，进入代码/实际案例，不先发固定水平测试 |
| 连续正确后减少基础重复 | ArrayList 3–4 | 保留已验证能力，提高综合程度；不机械追加基础题 |
| 概念错精准补弱 | ArrayList 2–3 | 定位越界/空指针、复制复杂度两处错误，不重讲整个集合 |
| 措辞错不冗长重讲 | ArrayList 5 | 承认语义已明确，只简短修正术语 |
| 请求加速立即调整 | ArrayList 5 | 当轮给重点和 Demo，模式与速度保存且无规划转换 |
| 请求深入提高深度 | ArrayList 6–7 | 解释扩容与均摊原理，并对具体卡点逐步引导 |
| 拒绝练习停止出题 | ArrayList 7–8 | 回答中无新题、无要求提交答案，拒绝选择持久化 |
| 随时结束保存 | ArrayList 9、11 | 立即 finish，生成笔记，不附加收尾测验 |
| 未通过 Sprint 仍能结束 | ArrayList 9 | Session completed，Sprint active，运行验证仍未验证 |
| 每项标准有证据状态 | ArrayList 8 | 区分已验证、需巩固、自报、未验证，并解释依据 |
| 新对话恢复 | ArrayList 10 | 无旧聊天仍恢复模式、难度、拒绝练习和遗留缺口 |
| 领域采用不同验证形式 | MySQL / 英语 / 理论 | SQL 与执行计划、情境表达改写、业务时序案例；不是统一定义问答 |

行为审查应引用轮次、实际回复片段和相关保存证据。指出失败或不确定之处；不将模式字段已变更等同于教学文字已经改变，不将 AI Demo 等同于学生独立实践。
