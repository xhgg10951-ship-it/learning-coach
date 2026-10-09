# Learning Coach 架构（Phase 1 + Phase 2A）

## 范围与旧设计处置

本次在现有 Skill、Markdown 模板与标准库 Python 脚本上重构，不引入服务器、数据库、第三方依赖或 Agent 编排框架。运行要求 Python 3.10 或更新版本；本次在 Windows / Python 3.13.15 验证。

| 原设计 | 本阶段处置 |
|---|---|
| 用户基础画像、目标画像、资料语言偏好 | 保留并改为公共画像与 Goal 补充画像，不由时长自动推断能力 |
| 权威资料查找、范围与版本核验 | 保留；按当前 Track 逐步读取与细化 |
| 月目标、ISO 周、复选框状态、自动顺延 | 新版使用非日历的 Milestone/Sprint，状态改由 Python 校验的 JSON 保存 |
| 全局大纲与单文件计划 | 拆为多个独立 Goal/Track，初始化仅保留粗粒度地图 |
| 学习热身、练习批改、结束后笔记与画像更新 | Phase 2A 保存实际练习与批改、生成笔记及交接；不实现教学调度或自动画像 |
| 旧进度脚本与 HTML | 保留只读兼容入口；新版和旧版明确区分，移除日历推进及掌握率推断 |
| 旧模板与已有数据 | 旧模板原样保存到 `resources/templates/legacy/`；不修改已有用户数据 |

## 五级模型与渐进规划

| 层级 | 含义 | 当前实现 |
|---|---|---|
| Goal | 最终想达到的能力，如 Java 后端开发 | 多目标、独立画像、暂停/恢复/完成 |
| Track | 一个相对独立的学习领域，如 Spring Boot | 独立目录、状态、依赖建议与计划 |
| Milestone | 可检验的大阶段能力目标 | 当前阶段与历史，默认参考 20～40 小时 |
| Sprint | 阶段下可检验的学习单元 | 当前单元与历史，默认参考 3～8 小时 |
| Session | 用户选定的一次学习 | 可选 Sprint 关联、计划外主题、追加检查点、结束笔记及跨对话交接 |

创建 Goal → 建立粗粒度 Track 地图 → 用户选择 Track → 创建一个 Milestone → 创建它的第一个 Sprint。后续单元依据现有目标、已完成内容、尚缺能力和用户反馈逐个创建。原计划、完成记录、跳过理由及用户主动修改均保留，不以动态规划为由整体覆盖重建。

一个 Sprint 可以当天完成，也可以持续数周。创建与修改日期只作元数据，不是 ID，不定义逾期，不自动推进。参考工作量只帮助拆分，不能证明掌握。未来内容只能保留粗略方向。

## 文件结构与唯一权威来源

```text
learning-hub/
├── profile.md
├── goals/
│   ├── java-backend/
│   │   ├── goal.md
│   │   ├── state.json
│   │   └── tracks/
│   │       ├── java-core/
│   │       ├── spring-boot/
│   │       │   ├── track.md
│   │       │   ├── state.json
│   │       │   ├── milestones/
│   │       │   │   └── M001.md
│   │       │   ├── sprints/
│   │       │   │   └── SP001.md
│   │       │   └── sessions/
│   │       │       ├── index.json
│   │       │       └── SE-<UUID>/
│   │       │           ├── record.json
│   │       │           └── note.md
│   │       └── mysql/
│   └── english/
│       ├── goal.md
│       ├── state.json
│       └── tracks/
└── state/
    └── active.json
```

| 文件 | 权威内容与职责 |
|---|---|
| `profile.md` | 公共背景、资料偏好等人工可读描述，不包含学习单元状态 |
| `goals/<G>/goal.md` | 本 Goal 的补充背景、偏好和用户原始说明，不包含生命周期状态或受管理画像副本 |
| `goals/<G>/state.json` | Goal ID、标题、状态、四项受管理画像、元数据和修改历史的唯一机器来源 |
| `tracks/<T>/state.json` | 当前 Track、Milestone、Sprint 的 ID、关系、目标、验收标准、状态与历史的唯一机器来源 |
| `track.md` | 范围、资料及粗略未来方向的说明补充 |
| `milestones/<M>.md`、`sprints/<SP>.md` | 可人工编辑的补充说明，不重复维护状态或验收结论 |
| `state/active.json` | 当前 `goal_id`、`track_id` 选择指针及 schema/更新时间；不复制单元状态或掌握信息 |
| `sessions/<SE-ID>/record.json` | 单次学习状态、追加事实、检查点及交接的唯一机器来源 |
| `sessions/index.json`、`sessions/<SE-ID>/note.md` | 从记录派生的定位缓存和学习笔记，不是第二套可编辑状态 |

机器文档使用 `schema_version = 2`。当前选择文件只保存位置指针及必要的 schema/时间元数据。关键字段由程序校验，不从 Markdown、复选框或文件名猜测状态。Markdown 标题和说明只供阅读，JSON 中对应受管理字段发生更新后，说明文件不应作为旧值的权威来源。

数据目录按显式 `--hub`、环境变量 `LEARNING_COACH_HUB`、`Path.home()/learning-hub` 顺序选择。代码与用户数据分离，无用户名或固定 Windows 路径。

## ID、范围与依赖

- Goal ID 在 hub 内唯一，Track ID 在所属 Goal 内唯一；可指定安全 slug 或由程序生成 UUID 形式的稳定 ID。修改标题不重命名 ID/目录。
- Milestone/Sprint ID 在所属 Track 内唯一，默认分别按 `M001`/`SP001` 递增，编号不依赖日期，Sprint 编号不随 Milestone 重置。
- 所有定位使用 Goal/Track 限定上下文；完整标识可理解为 `(goal_id, track_id, kind, id)`，不同 Goal/Track 中同样的短 ID 不会串写。
- Track 前置依赖仅引用同一 Goal 的其他 Track。程序拒绝缺失、自依赖和循环引用；依赖是学习建议，不要求前置 Track 完成才可选择或激活当前 Track。
- Session 使用稳定的 `SE-<UUID>`，记录所属 Goal/Track、可选 Sprint 及验收快照。同 Track 最多一份 active Session；其他 Track 独立保留。实际学习内容不受 Sprint 范围限制，不建立共享知识或跨目标进度同步。

## 状态与层级约束

下面的暂停、跳过和父子推进规则适用于规划层级。Session 独立采用 active → completed，不要求能力验收、不自动完成 Sprint；保存原有事实和结束记录不受上层后来暂停的影响。开始与恢复学习仍要求 Goal/Track active。

| 层级 | 支持的状态 | 终态 |
|---|---|---|
| Goal | `active`、`paused`、`completed` | `completed` |
| Track | `pending`、`active`、`paused`、`completed` | `completed` |
| Milestone / Sprint | `pending`、`active`、`paused`、`completed`、`skipped`、`ended` | `completed`、`skipped`、`ended` |
| Session | `active`、`completed` | `completed`；仅表示本次学习收束 |

`pending` 是待开始，`active` 是进行中，`paused` 是明确暂停，`completed` 是记录了能力验收结果的完成，`skipped` 是用户选择不做，`ended` 是用户提前结束且未声称完成。创建默认 active，支持 pending 的创建入口可按用户要求保存待开始单元；状态转换不提供回到 pending。

- `active → paused → active` 表达暂停与恢复；待开始单元可显式激活。完成只允许 `active → completed`，必须提供非空验收说明（可以是用户自报，不强制附件）。Python 检查说明存在，能力内容仍由 Agent 与用户共同判断。
- Milestone/Sprint 的非终态可以按用户选择跳过或提前结束。终态不能直接重开；需要新单元并明确关联旧记录与调整理由。
- 同一 Track 最多一个 active Milestone，同一 Milestone 最多一个 active Sprint。普通创建要求该层前序单元均已终结；未结束时只有显式 `--adjustment` 才可创建调整单元，暂停原 active 单元并保留历史。
- 完成 Milestone 前，子 Sprint 必须均为终态。完成 Track 前，所属 Milestone 必须均为终态。完成 Goal 前，所属 Track 必须均 completed。各层还需要自己的能力验收说明；子项数量或终态比例不是能力证明。
- Milestone 被暂停时，active Sprint 一并暂停；恢复阶段后显式恢复用户选定的 Sprint。Milestone 被跳过或提前结束时，非终态 Sprint 同步成为 skipped/ended，原终态历史保持不变。
- Goal/Track 暂停是上层挂起，保留下属状态，禁止新建、激活或完成其下属。`select` 仍可自由切换，仅移动指针。上层恢复后，继续原有状态；不会重建计划。

`transition` 状态变化和 `update` 重要字段更新必须带 `--note` 并保留历史；创建保存初始决策，调整创建使用 `--adjustment` 记录用户理由。`update` 可修改标题、目标、验收标准、依赖和画像，不能改变 ID 或通过变更内容重开终态记录。

## Agent 与 Python 分工

Phase 2A 中，Agent 从实际会话整理带来源摘录的内容、问题、解释、练习、薄弱点、理解反馈和验收证据，Python 批量校验并持久化。交接区分用户自报、AI 判断、练习验证和未验证，不能把已讲解当成已掌握。收到明确结束保存指令立即停止教学并保存，无须再次机械确认。

Session 记录采用单文件原子提交，笔记与索引是可重建投影。新对话读取 session-context，只展开相关少量记录；active 可以恢复，completed 只能作为新 Session 的参考。索引失效时内存重建；缺失笔记可修复，冲突文件保留。具体协议见 [session-schema.md](session-schema.md)。

Agent 理解目标、复用画像、提出领域结构，生成当前能力目标和验收标准，核验资料，根据已有结果建议下一步并让用户确认重要规划。已授权的具体方案无需再次确认。自由切换、暂停、跳过等用户明确指令直接落实。

Python 负责合法目录与唯一 ID、数据读取、指针、生命周期约束、输入校验、历史和持久化。Agent 不直接改 JSON，不通过字符串替换 Markdown 复选框维护状态。程序成功返回且读回符合预期后才向用户报告完成。

CLI 位于 `scripts/learning.py`；全局 `--hub` 位于子命令之前：

| 命令 | 用途 |
|---|---|
| `init` | 初始化空 hub；不自动迁移旧数据 |
| `goal-create`、`track-create` | 创建独立目标或领域 |
| `select`、`current` | 保存或读取当前 Goal/Track 指针 |
| `list`、`show` | 读取摘要或明确指定的详细上下文 |
| `milestone-create`、`sprint-create` | 一次创建一个当前单元，需目标与验收标准 |
| `transition` | 校验状态转换，要求决策或验收说明 |
| `update` | 更新受管理的内容字段并保存理由 |
| `validate` | 全库结构和状态检查，不修复或覆盖文件 |
| `session-spec` | 保留第一阶段只读兼容描述；真正开始学习使用 session-start |
| `session-start`、`session-checkpoint`、`session-finish` | 稳定 ID、批量事实、重要检查点和结束笔记 |
| `session-context`、`session-resume` | 精简交接、恢复 active；completed 只作为新 Session 的参考 |
| `session-list`、`session-show`、`session-repair` | 最近 N 次摘要、事实分页、派生文件恢复 |

真实可运行示例见 [onboarding](../references/onboarding.md)、[planning](../references/planning.md) 和 [progress](../references/progress.md)。各命令的完整参数以 `python scripts/learning.py <子命令> --help` 为准。

## 局部读取、并发与中断

日常 `show --goal G --track T` / `current` 只读取相关的 Goal 与选中 Track；依赖检查按需要读取同一 Goal 的领域摘要。全库统计、显式 `list` 和 `validate` 才展开对应范围，避免把所有详细学习材料一次性载入上下文。

写入以 hub 级互斥锁串行执行，避免两个进程同时读改写。JSON 使用同目录临时文件后原子替换；新目录先准备再重命名。Track 的全部单元状态和历史在同一 JSON 内更新，减少跨文件状态矛盾。错误会带定位信息返回非零退出码。

原子替换降低半写入风险，但不是跨目录、多文件的数据库事务。崩溃后可能留有暂存目录或孤儿说明文件；验证器应明确报告并保留，不静默删除、接管或覆盖。遇到残留锁，先确认无写入程序运行，并备份检查后人工处理；不把删除锁当作默认重试策略。文件可人工查看与编辑，但关键机器字段的正常更改必须通过 CLI；人工损坏应通过校验发现。

## 兼容与迁移

`scripts/progress.py` 保留 `--hub`、`--goal`、`--today`、`--json`、`--html`，增加可选 `--track`（需要 `--goal`）。旧版解析只读保留，报告明确给出 legacy 标识与警告。旧月份/ISO 周和复选框作为原始记录展示，不自动顺延、延期或计算掌握率。新版按 schema 读取；遇到缺失状态、损坏 JSON、孤儿文件或混合结构不安全时明确报告，不把坏数据伪装为零进度。

`--today` 只指定报告日期。HTML 仅为状态摘要，输出在 hub 之外；`--json --html` 的标准输出保持纯 JSON。这个报告不需要网络、前端构建或第三方依赖。

本阶段没有自动迁移器。建议的可恢复手工流程：

1. 对旧 hub 做只读报告，保留原始目录和备份；不要调用任何覆盖原文件的模板流程。
2. 与用户确认目标画像、粗粒度 Track 对应关系、当前真正想继续的能力阶段。旧“已完成”标记本身不等于新标准已经验收。
3. 在不同的新目录执行 `init`、`goal-create`、`track-create`，只建立当前一个 Milestone 和 Sprint。把需要保留的旧资料作为描述性来源明确引用，不复制旧复选框作为新状态。
4. 用户核对新结构后运行 `validate`，显式切换以后使用的 hub。旧笔记继续原样保留查看，尚未实现 Session 导入。

无法明确映射的内容留在旧目录，报告未迁移项。重复 ID、已存在旧 Goal 目录或不合法的新版结构均应拒绝覆盖。新旧数据可以被只读报告汇总，但重构不是自动重写用户资料的授权。

## 本阶段边界与已知风险

已实现多目标、多领域、渐进规划、自由切换、显式状态更新、历史与兼容报告，以及 Phase 2A Session 生命周期、真实事实持久化、Markdown 笔记和跨对话续学。模型、字段、限量读取、提交与恢复协议见 [session-schema.md](session-schema.md)，实施前约定见 [phase2a-design.md](phase2a-design.md)。

修改清单、实际测试结果与限制见 [Phase 2A 交付记录](phase2a-delivery.md)。

本阶段不实现自适应教学、练习调度、自动画像、共享知识库、跨 Goal 掌握同步、复习调度、FSRS、向量数据库/RAG、Web 前端或多 Agent 系统。knowledge_ids/review_candidates 只预留字段。Agent 记录真实事实，Python 校验结构、引用和写入，程序不生成不存在的学习事实。

JSON 能校验结构与状态，不能判定学习者是否真正掌握；验收说明的质量由用户与 Agent 负责。多文件创建不是完整事务，异常恢复需备份和人工核对。旧数据需要人工解释，不能自动得到可信的新能力结论。没有强制资料联网依赖，无法核验时必须如实标注；联网资料的版本变化不自动改写已完成历史。

单 Track 的单元与历史保存在一个 JSON 中，长期使用后文件会增长；本阶段未做归档/性能压力优化。`current` 返回简短位置摘要，下一步规划必须显式 `show` 阅读该 Track 的已有结果和历史。命令返回错误也可能发生在原子提交刚完成之后，此时先读取并校验现有状态，不盲目重建；恢复逻辑保留已提交状态引用的说明文件。
