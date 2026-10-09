# 第一阶段重构交付记录

> 历史交付快照：以下“Session 不持久化/后续阶段”等说明仅描述 Phase 1 当时的范围。当前 Session 生命周期、笔记和跨对话恢复已由 [Phase 2A](session-schema.md) 扩展；以当前 [架构](architecture.md) 和 [Session 指令](../references/session.md) 为准。

交付日期：2026-10-08。分支：`refactor/phase1-learning-structure`。

基于仓库原有 12 个文件完成实际重构，保留标准库 Python 与本地文件机制。本次没有读取、迁移或改写仓库外的真实学习数据；所有功能验证都使用独立临时目录。本次仅进行本地 Git 提交，远端推送由用户自行完成；提交记录以 Git 历史为准。

## 1. 修改和新增文件

修改 12 个原有文件：

- `SKILL.md`
- `references/onboarding.md`
- `references/syllabus.md`
- `references/planning.md`
- `references/progress.md`
- `references/session.md`
- `resources/templates/goal.md`
- `resources/templates/profile.md`
- `resources/templates/syllabus.md`
- `resources/templates/plan.md`
- `resources/templates/session.md`
- `scripts/progress.py`

新增 16 个文件：

- `.gitignore`
- `scripts/learning.py`
- `docs/architecture.md`
- `docs/phase1-delivery.md`（本文件）
- `resources/templates/track.md`
- `resources/templates/milestone.md`
- `resources/templates/sprint.md`
- `resources/templates/legacy/README.md`
- `resources/templates/legacy/goal.md`
- `resources/templates/legacy/plan.md`
- `resources/templates/legacy/syllabus.md`
- `resources/templates/legacy/session.md`
- `tests/test_learning.py`
- `tests/test_persistence.py`
- `tests/test_progress.py`
- `tests/test_skill.py`

旧版 4 个格式模板原样保留在 legacy 目录，并明确标为历史格式参考。没有新增第三方运行依赖、后台服务、数据库或 Web 前端。

## 2. 新数据结构

```text
<hub>/
  profile.md
  state/active.json
  goals/<goal_id>/
    goal.md
    state.json
    tracks/<track_id>/
      track.md
      state.json
      milestones/M001.md
      sprints/SP001.md
      sessions/
```

- Goal 的状态和受管理画像只在 Goal `state.json` 保存。
- Track 的状态及其全部 Milestone/Sprint 的目标、验收标准、父子关系、状态和修改历史，只在 Track `state.json` 保存。
- Markdown 保存补充背景、资料和说明；不复制维护另一份关键状态。
- `active.json` 只保存 Goal/Track 选择指针及 schema/时间元数据。切换位置不改变计划状态。
- Goal ID 在 hub 内唯一，Track ID 在 Goal 内唯一，M/SP ID 在 Track 内唯一；完整身份由所属 Goal/Track 限定，跨领域相同短编号不会串写。ID 不随标题或日期改变。
- 使用 `schema_version=2`。目录优先级：`--hub` > `LEARNING_COACH_HUB` > `~/learning-hub`。

完整设计见 [architecture.md](architecture.md)。

## 3. 状态转换与渐进规划

| 层级 | 状态 |
|---|---|
| Goal | active、paused、completed |
| Track | pending、active、paused、completed |
| Milestone / Sprint | pending、active、paused、completed、skipped、ended |

允许待开始后显式激活、暂停与恢复；完成必须从 active 出发并记录非空验收说明。跳过与提前结束分别保留为 skipped / ended，不等同于掌握。终态不重开、不改写其验收内容；新需求建立带说明的新单元。

每个 Track 最多一个 active Milestone，每个 Milestone 最多一个 active Sprint。未结束的前序单元会阻止普通后续创建；用户明确要求调整时使用 `--adjustment`，暂停原 active 单元并保留历史。完成父层要求其孩子已被明确处理，仍需独立能力验收说明，不能依据孩子数量或学时自动完成。

Goal/Track 暂停会挂起下属推进，但保留其原状态。Milestone 暂停会暂停 active Sprint；跳过或提前结束 Milestone 会相应结束非终态 Sprint，已结束历史不变。

创建 Goal 只创建目标；建立 Track 只创建粗粒度领域。用户选定领域后，分别调用创建一个 Milestone 和其第一个 Sprint。之后逐个规划，不自动展开未来全部单元。下一步规划前，Agent 必须读取当前 Track 的历史、完成内容与剩余能力要求。

## 4. 新旧兼容与迁移

`progress.py` 可只读汇总新旧目标。旧格式明确标为 legacy，无法识别的内容给出警告或未知值，不伪装成零进度。旧月份/周标签仅展示原文，不参与延期、顺延或自动推进。

没有自动迁移器。安全方案是保留原始 hub 与备份，核对旧画像和当前能力要求，在另一目录初始化新结构，再由用户确认后切换使用。旧笔记不自动转换，旧勾选不自动成为新标准的验收结果。重复 ID、已有目录、损坏 JSON、重复键、缺失文档等均会明确报错。

HTML 保留为无需网络的只读状态摘要；本阶段未恢复旧版交互标签和热力图外观。报告不输出掌握率，上层暂停时同时说明保存状态和当前有效状态。HTML 输出不得指向 hub 内部。

## 5. 实际测试结果

环境：Windows，Python 3.13.15；测试使用标准库 unittest。

执行：

```shell
python -m unittest discover -s tests -v
```

最终完整运行结果：

```text
Ran 75 tests in 44.552s
OK
```

| 测试文件 | 数量 | 结果 |
|---|---:|---|
| test_learning.py | 38 | 全部通过 |
| test_persistence.py | 15 | 全部通过 |
| test_progress.py | 20 | 全部通过 |
| test_skill.py | 2 | 全部通过 |
| 合计 | 75 | 0 失败、0 错误、0 跳过 |

用户要求的十类验收均已覆盖并执行：

| 要求 | 实际验证 |
|---|---|
| 多目标 | Java 后端与英语画像、状态互不干扰 |
| 多领域 | Java 基础、Spring Boot、MySQL 独立状态与目录 |
| 渐进规划 | 创建一个阶段及首个单元，不自动生成未来单元 |
| 快速学习 | 同一天完成 SP001、创建并完成 SP002 |
| 长期未学习 | 时间改为一个月前，读取不改变状态；报告跨年也不推进 |
| 自由切换 | 未完成 Sprint 时切换 Goal/Track，再返回内容和状态不变 |
| 状态约束 | 重复 ID、重复 active、非法激活/完成、缺少说明被拒绝 |
| 持久化 | 每条 CLI 使用新进程，重启后位置、状态、历史一致 |
| 旧版数据 | 逐字节比较原文件不变，拒绝覆盖和错误回退解析 |
| Agent 入口 | 引用可达；46 条文档示例命令在临时目录实际执行 |

额外覆盖：原子替换失败、提交后中断、创建目录失败、跨进程写锁、残留暂存文件、孤儿文档、循环依赖、无关领域损坏隔离、NaN/Infinity/重复 JSON 键、标题修改后 ID 稳定、状态操作幂等、计划调整保留原标准、Session 不落盘。

Skill 的 quick_validate 检查通过，`git diff --check` 无错误。开发中发现的参数错误输出、格式边界和中断恢复问题均已修复并回归。尚未执行 Linux/macOS 平台测试、真实断电试验、长年大规模数据压力测试或真实用户旧数据迁移；这些没有记为通过。

## 6. 命令示例

以下在仓库根目录执行，使用全新的独立示例 hub。相同流程和参数已在文档验收中验证；验收说明中的文字必须在真实使用时换成用户实际结果。

```shell
python scripts/learning.py --hub ./planning-demo init
python scripts/learning.py --hub ./planning-demo goal-create --id java-backend --title "Java 后端开发" --level "了解基本语法" --ability "独立开发基础 REST API"
python scripts/learning.py --hub ./planning-demo track-create --goal java-backend --id spring-boot --title "Spring Boot"
python scripts/learning.py --hub ./planning-demo select --goal java-backend --track spring-boot
python scripts/learning.py --hub ./planning-demo milestone-create --goal java-backend --track spring-boot --title "基础 REST API" --objective "独立开发并运行 REST API" --criterion "从空项目实现 JSON 接口并解释请求流程"
python scripts/learning.py --hub ./planning-demo sprint-create --goal java-backend --track spring-boot --milestone M001 --title "启动项目" --objective "理解项目结构与启动方式" --criterion "独立启动并解释入口和路由"
python scripts/learning.py --hub ./planning-demo current
python scripts/learning.py --hub ./planning-demo transition --goal java-backend --track spring-boot --kind sprint --id SP001 --status completed --note "示例：用户自报已独立启动并说明入口和路由"
python scripts/learning.py --hub ./planning-demo show --goal java-backend --track spring-boot
python scripts/learning.py --hub ./planning-demo sprint-create --goal java-backend --track spring-boot --milestone M001 --title "JSON 接口" --objective "实现 JSON 请求响应" --criterion "独立演示接口并解释请求流程"
python scripts/learning.py --hub ./planning-demo validate
python scripts/progress.py --hub ./planning-demo --goal java-backend --track spring-boot --json
```

上述最后创建的单元为 SP002，仍在进行中。完整完成阶段、切换目标、修改、暂停、跳过和提前结束的可运行示例见 [planning.md](../references/planning.md)。`python scripts/learning.py <子命令> --help` 可查具体参数。成功时 stdout 是 JSON；错误时 stderr 是 JSON 且退出码为 2。

## 7. 第一阶段已实现

多 Goal 和独立 Track、稳定 ID、画像保留、可选前置依赖、单个当前阶段与单元的渐进创建、能力目标与验收标准、人工完成/跳过/提前结束、暂停恢复、自由切换和当前位置、带理由的历史修改、可靠读取与校验、原子文件替换、串行写锁、旧数据只读报告及错误定位。

Session 只返回包含 Goal/Track、可选 Sprint、主题、建议时长的兼容描述，明确 `persisted=false`，不创建学习记录。

## 8. 后续阶段能力

第二阶段再处理 Session 生命周期与持久化实际学习记录、笔记与相应教学闭环。跨对话 Session Handoff、共享知识库、跨 Goal 掌握同步、复习队列、FSRS、RAG、Web 前端和多 Agent 协作均未实现，也未为其引入框架。

## 9. 架构风险与限制

- Python 校验结构、状态和验收说明是否存在，无法证明用户真正掌握；Agent 与用户需要对具体能力作判断。
- 原子替换不是完整的多文件事务。已覆盖常见失败与提交后中断；真实崩溃仍可能留下锁、暂存目录或孤儿文件，必须保留、核对备份并人工恢复，不自动删除。
- hub 写锁串行化本地写操作。只读过程中若与新建操作交错，可能报告暂存/孤儿文件；等待写入结束后重读。没有为网络共享盘、跨机器并发提供保证。
- 每个 Track 的状态与历史会随长期使用增长；当前实现适合轻量本地使用，尚未做历史归档和大规模性能优化。
- 旧数据按原模板尽可能读取，但无法确定的新语义必须人工确认，不能自动得到可信的能力验收结论。
