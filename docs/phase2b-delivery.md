# Phase 2B 自适应教学交付与风险报告

基准：已测试的 Phase 2A `302528f`。开发分支：`feature/phase2b-adaptive-teaching`。验收日期：2026-10-11 至 2026-10-12（Asia/Shanghai）。

## 实现范围

教学现在先读取公共画像、Goal/Track 背景、Milestone/Sprint 要求和相关 Session 的实际作答，以已有证据选择起点。自然语言可即时切换 Adaptive、Quick、Guided、Deep、Practice，并分别保存速度、深度、练习意愿、难度及调整理由。模式切换不修改规划生命周期。

新增 `teaching-context` 只读入口，逐项返回 verified、needs_consolidation、user_reported、unverified，以及原始答案、批改理由、来源 Session/事件。综合任务的部分正确不会抹掉已验证分项；新表现可更新判断，更正旧表现仍保留原表现时间，不压过后来实际暴露的缺口。失效证据不能继续支持教学提速。

练习的 `assessment` 保存验证形式、错误类型及对应标准的分项判断。Java、SQL、英语和理论可使用不同形式；计划外任务允许空标准关联。Python 不通过学习时长、题数、解释次数或教学模式计算掌握程度。

继续复用 Phase 2A 的追加事件、原子写入、检查点、自动笔记、幂等重试、结束后更正和跨对话恢复。普通 v1/v2 记录不因读取或修复升级；使用教学扩展时才写 session_version=3。旧程序会拒绝 v3，应使用本分支读取新记录。

组内收束使用 checkpoint 并保持 Session active；用户明确结束本次学习并保存才 finish。Session 可以在没有练习、没有纠错或 Sprint 未验收时正常结束。Sprint 是否完成仍由用户决定，通过独立 transition 操作处理。

主要实现与流程：

- [教学投影及校验](../scripts/teaching.py)、[Session 集成](../scripts/sessions.py)、[统一 CLI](../scripts/learning.py)。
- [Skill 入口](../SKILL.md)、[自适应教学流程](../references/teaching.md)、[Session 流程](../references/session.md)。
- [教学数据合约](teaching-schema.md)、[自动化测试](../tests/test_teaching.py)、[真实场景运行器](../tests/run_agent_scenarios.py)。

## 验证与复现

完整自动化测试：**160 项通过，555.476 秒，OK**，包括原有 137 项回归及新增 23 项教学专项测试。保存了 [完整日志](evals/phase2b/automated-tests.log) 和 [源码哈希/结果元数据](evals/phase2b/automated-tests.json)。最终再核验 Skill 引用及可执行工作流：**2 项通过，37.764 秒**，见 [补充日志](evals/phase2b/skill-workflows.log)；Skill 结构校验也通过。交付源码与完整测试时的 Python 源码哈希一致。

真实教学的最终收集结果：**14 轮实际 Agent 回复，覆盖 12 项验收要求**；逐轮结构断言和四个导出 Hub 的校验均通过。已逐轮审查实际回复的教学行为，而非仅检查模式字段。以下通过结论限定于这些最终样本；早期失败和已知语义风险另列，不计入通过数。

### 真实对话的行为审查

ArrayList 原始输入、实际响应、来源 Agent 和逐轮断言见 [11 轮完整对话](evals/phase2b/arraylist/transcript.json)，对应保存状态见 [逐轮观察](evals/phase2b/arraylist/observations.json)。表中的引文来自实际教师回复。

| 验收要求 | 实际观察 | 最终样本结果 |
|---|---|---|
| 1. 有基础不从零开始 | 第 1 轮直接说“已有记录验证了基本操作与扩容”，给订单队列的批量插单、异常排查和复制成本综合任务，没有固定水平测试。 | 通过 |
| 2. 连续正确后减少基础重复 | 第 3 轮保留并认可修正后的能力；第 4 轮转入批量导入与审计快照，实现、运行和成本分析合在同一任务，明确“无需重复基础问答”。 | 通过 |
| 3. 概念错误精准补弱 | 第 2 轮只纠正 get(size) 的异常类型和复制 m 项的成本；保留 size、容量及此前扩容的正确证据，没有重讲集合入门。 | 通过 |
| 4. 措辞错误不冗长重讲 | 第 5 轮确认“这只是措辞问题”，不撤销已验证能力，随即提供 Demo。 | 通过 |
| 5. 请求加快立即调整 | 第 5 轮当轮改用 Quick，给完整订单列表小流程；记录为 quick/fast，并注明预期输出未实际运行。 | 通过 |
| 6. 请求深入提高深度 | 第 6 轮解释扩容序列、几何级数和固定上限；第 7 轮对“不理解平均为何受固定上限约束”分步算账，保存 Guided/slow/deep。 | 通过 |
| 7. 拒绝练习停止出题 | 第 7–8 轮只讲解或汇总，没有新题或要求提交答案；exercise_policy=declined，恢复后也继续保留。 | 通过 |
| 8. 随时结束并保存 | 第 9、11 轮收到结束指令即 finish，生成笔记；没有追加收尾测验，也不要求纠错。 | 通过 |
| 9. Sprint 未通过也能结束 | 第 9 轮 Session completed、Sprint active；独立实现与运行仍 unverified。 | 通过 |
| 10. 总结每项标准的证据 | 第 8 轮逐条列出五项标准，区分正确作答、后续自报的理解卡点和没有运行证据；明确 AI 讲解不能证明卡点已解决。 | 通过 |
| 11. 新对话恢复深度、难度和弱点 | 第 10 轮换无聊天历史的教师，仅从 Hub 恢复 Guided/慢速/深入、集合基础以上的难度、均摊原理卡点及运行缺口；没有从零重教。 | 通过 |
| 12. 不同学科采用不同形式 | MySQL 给 SQL 编写和模拟 EXPLAIN；英语用向主管请假的角色交流与语气改写；理论用并发改价造成缓存不一致的时序和权衡分析。 | 通过 |

领域原始对话：[MySQL](evals/phase2b/mysql/transcript.json)、[英语](evals/phase2b/english/transcript.json)、[理论](evals/phase2b/theory/transcript.json)。MySQL 明确 EXPLAIN 为人工教学摘要、未执行；英语和理论尚无学生回答，均未写成已掌握。

第 8 轮还验证了一个重要边界：机器投影保留此前均摊复杂度的正确作答，但教师同时解释最新“仍不理解”的自报和独立推导缺口。不能把标准的 verified 标签扩张成每个细节都已掌握。

### 执行来源与最终状态

最终采用原生独立 Agent 路径，并非声称 CLI 自动运行已完整成功。ArrayList 第 1–6 轮由 `/root/arraylist_verified` 执行；第 7 轮开始因会话中断换 `/root/arraylist_continued`，只传实际历史消息和已保存 Hub；第 10–11 轮由全新 `/root/arraylist_resume_verified` 执行，第 10 轮不提供旧聊天文件。三个教师均为 `gpt-6.1-sol / medium`。理论最终回复由 `gpt-6-luna / medium` 完成；MySQL、英语早期使用继承配置，工具未暴露确切运行模型，如实标为未知。

MySQL、英语、理论使用补充变量定义批改规则之前的 Skill 快照，只验证任务生成，不涉及该规则的答案批改。ArrayList 使用最终教学规则；所有场景使用相同的最终 Python 实现。差异和逐轮哈希见 [运行清单](evals/phase2b/manifest.json)。模型、历史上下文和措辞都会影响结果，不将不同快照混称为完全相同的实验。

- ArrayList 主 Session [`SE-23ef722ad0824f938983ff5a1d2ff6f8`](evals/phase2b/arraylist/hub/goals/demo/tracks/core/sessions/SE-23ef722ad0824f938983ff5a1d2ff6f8/record.json)：completed，9 个检查点。
- 新对话 Session [`SE-cfdcb3c318aa438fa70a3b2c32660e86`](evals/phase2b/arraylist/hub/goals/demo/tracks/core/sessions/SE-cfdcb3c318aa438fa70a3b2c32660e86/record.json)：completed，2 个检查点；只有讲解，没有新增实践。
- ArrayList 的 Sprint `SP001` 仍 active；五项标准中前四项保留已验证作答，独立实现与运行未验证，均摊原理理解卡点仍需后续确认。不存在自动完成 Sprint 的操作。
- MySQL、英语、理论 Session 均 active，等待学生自行选择是否作答；未由测试收尾擅自结束学习。

[结构结果](evals/phase2b/results.json) 与 [证据文件哈希](evals/phase2b/artifact-sha256.json) 可直接复核。原生 Agent 的工具操作保留在执行会话中；仓库交付响应、逐轮观察、最终权威记录及笔记，不包含完整原生工具事件流。该限制不同于 CLI 运行器可输出的 JSONL 工具轨迹。

证据目录通过 `.gitattributes` 保持原始字节，避免 Git 换行转换破坏哈希或生成笔记的一致性。仅原始生成笔记中的空引用行允许保留行尾空格，未改写教学记录来消除格式告警。

### 复现命令

复现自动化测试：

```text
python -B -m unittest discover -s tests -v
```

复现真实教学场景，需要已登录、额度及正常审批服务可用的 Codex CLI。以下命令使用当前模型设置，只创建隔离合成 Hub：

```text
python -B tests/run_agent_scenarios.py --out .test-tmp/phase2b-reproduce
```

可重复指定 `--scenario arraylist|mysql|english|theory`。`--prepare-only` 只创建夹具，可配合独立 Agent 和 `--native-turn` 进行同一场景的验收。完整输入、断言、原始轨迹格式及审查标准见 [真实 Agent 验收说明](agent-evaluation.md)。模型回复存在随机性，复现检查的是行为和实际记录，不要求逐字相同。

## 实测发现与修复

一次实际教师把“这组到这里，请保存本组结果”错误理解成结束 Session。已保留 [原始失败证据](evals/phase2b/failed-group-finish.json)，修正 Skill 中的小组收束边界，并在相同输入增加 active 状态断言。失败尝试不计入通过结果。

另一轮实际批改沿用了题干中同名符号的含义，没有采用学生已明确的变量定义，低估了等价的复杂度分析。已保留 [变量定义误判证据](evals/phase2b/failed-variable-definition.json)，补充按明确假设和等价推导批改的规则。使用原误判上下文、相同 `gpt-6-sol / medium` 的 [重试仍然失败](evals/phase2b/failed-variable-retry.json)，没有把这次重试算作修复成功。

之后使用干净的合成夹具和常规模型 `gpt-6.1-sol / medium` 重跑。新任务采用了不同的变量名，因此新流程正确认可等价分析，也不能证明旧的同名变量冲突已被彻底解决。这是仍需保留的语义批改风险，不能用最终成功样本覆盖原失败。

中断测试还出现过候选回复已写出、Session 尚未提交的情况。原始候选被保留且不计为完成；独立 Agent 收集入口现在要求调用方实际观察成功返回，随后校验权威记录，而不是看见回复文件就宣称保存成功。

CLI 尝试遭遇 Windows 测试目录权限错误和自动审批服务额度限制。未移除审批、未更改账户或购买额度；未完成的 CLI 运行不计为通过。真实教学验收使用当前工具环境的独立 Agent，和 CLI 自动运行作明确区分。

## 风险与边界

- 教学选择、自然语言意图理解和批改语义由 Agent 完成；Python 验证字段、引用、状态及持久化，不能证明引用原文真实或批改内容正确。已观察到变量定义误判以及同一上下文重试仍失败；最终成功样本不构成所有模型、所有表达或自动纠错能力的保证。
- 学生消息、画像和历史都是合成夹具；教师回复来自实际 Agent。AI Demo、人工编写的 EXPLAIN 和只看讲解均不属于学生独立实践。验收没有访问正式学习 Hub，也没有把测试结果导入真实学习记录。
- 证据读取限定当前 Track，默认读取最近相关 10 份 Session；截断数量会明确显示。需要更早证据时应增加 limit 或分页读取。没有跨目标知识共享或检索数据库。
- v3 与旧版二进制不向后兼容；现有 v1/v2 数据和原始笔记保留。多文件派生写入仍沿用 Phase 2A 的可恢复机制，不是数据库事务。
- 真实 Agent 测试需要服务可用；权限、审批或额度失败须保留记录并如实报告。独立 Agent 标识、源码哈希和完成观察是审查元数据，不是密码学证明。
- 未实现 FSRS、自动复习调度、自动画像更新、跨目标共享、RAG/向量库、Web 前端或产品运行时多 Agent 编排。
