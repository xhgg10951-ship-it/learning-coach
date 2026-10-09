# Phase 2A：Session 持久化与跨对话续学交付

日期：2026-10-09。基准：`refactor/phase1-learning-structure` / `10e6b0a`。开发分支：`feature/phase2a-session-persistence`。本次在原仓库开发，没有重建仓库、读取或修改正式 Hub。所有测试和结构校验均使用独立临时目录。

## 实际修改文件

修改 11 个文件：

- `.gitignore`：忽略工作区临时测试目录和日志。
- `SKILL.md`：开始、检查点、结束保存、跨对话续学与授权边界。
- `references/session.md`：完整生命周期、结构化输入、去重、恢复及可执行示例。
- `references/planning.md`、`references/progress.md`、`references/syllabus.md`：规划与 Session 的关系、读取入口和兼容边界。
- `resources/templates/session.md`：真实学习笔记检查指南。
- `scripts/learning.py`：注册 Session CLI，扩展 validate，UTF-8 输入输出。
- `tests/test_skill.py`：实际执行文档示例，核对记录和笔记内容。
- `docs/architecture.md`：更新架构与职责；`docs/phase1-delivery.md`：标注为历史快照，保留原交付事实。

新增 7 个文件：

- `scripts/sessions.py`：Session 存储、结构校验、批次去重、交接与恢复。
- `tests/test_sessions.py`：生命周期、跨进程、隔离、故障注入和端到端测试。
- `resources/examples/session-checkpoint.json`、`resources/examples/session-finish.json`：仅供测试的 ArrayList 模拟数据。
- `docs/phase2a-design.md`：实施前模型/CLI/兼容决策。
- `docs/session-schema.md`：字段、机器权威、读取边界、恢复协议和 Phase 2B 接口。
- `docs/phase2a-delivery.md`：本交付记录。

## 新增 CLI

`session-start`、`session-checkpoint`、`session-finish`、`session-resume`、`session-context`、`session-list`、`session-show`、`session-repair`。

写操作显式指定 Goal/Track。checkpoint/finish 从 UTF-8 JSON 文件或 stdin 批量接收事实和交接。成功 stdout 为 JSON；预期错误 stderr 为 JSON、退出码 2。继续保留无副作用的 `session-spec`。64 条 references 中的 shell 示例由自动化测试在临时 Hub 实际执行，包括动态替换 start 返回的 Session ID。

## Session 模型和跨对话恢复

每个 Track 独立保存 `sessions/SE-<UUID>/record.json`；它是此 Session 唯一权威来源，包含范围、主题、可选 Sprint 验收快照、状态、时间、追加事实、检查点历史及交接。规划 schema v2 不变，Session 增加 `session_version=1`，不重写既有规划数据。`index.json` 为定位缓存，`note.md` 为确定性投影。

记录区分用户自报、AI 判断、练习验证和未验证，保存引用及摘录；练习含题目、用户答案与批改，理解反馈必须来自用户。与 Sprint 相关的已验证能力须有实际正确练习支持。用户可以学计划外内容，无练习、错题未改或 Sprint 未完成均可结束。Session finish 不改变任何规划状态。

新对话只需 Hub 路径：session-context 默认返回当前 Goal/Track、当前阶段/单元、active 与最近 completed 的摘要、验证证据、薄弱点、未解决问题、下一步与笔记路径。active 使用 resume；completed 使用新 start --from-session，不重新打开或重复计入旧事件。用户可以拒绝建议并更换主题。更多事实通过 show 分页读取。

开始 request-id 与 checkpoint operation_id 支持幂等重试，同 ID 不同内容报错。权威记录先原子提交，派生笔记/索引失败时可以重试或 repair；损坏权威记录、冲突笔记和残留锁保留并报告。

## 实际验证

Windows、Python 3.13.15，标准库 unittest。基线 75 项通过（64.582 秒）。首次沙箱运行和工作区临时目录重试因 Python 临时目录 ACL 拒绝访问而失败；改用允许访问临时目录的测试进程后基线通过，没有修改程序来绕过数据保护。

实现期间完整 100 项通过（92.211 秒）；新增故障边界后的完整 107 项通过（98.397 秒）。最终包含 UTF-8 管道输入回归的全量命令 `python -m unittest discover -s tests -v` 已执行：

```text
Ran 108 tests in 103.942s
OK
```

| 测试文件 | 数量 | 最终结果 |
|---|---:|---|
| test_learning.py | 38 | 全部通过 |
| test_persistence.py | 15 | 全部通过 |
| test_progress.py | 20 | 全部通过 |
| test_sessions.py | 33 | 全部通过 |
| test_skill.py | 2 | 全部通过 |
| 总计 | 108 | 0 失败、0 错误、0 跳过 |

最终运行日志位于忽略目录 `.test-tmp/final-108-tests.log`，未提交临时 Hub 或测试日志。

| 用户验收要求 | 实际覆盖 |
|---|---|
| 开始与稳定 ID、增量保存、多次 checkpoint | 真实 record.json、追加顺序、重试快照不变 |
| 正常结束、无练习、计划外内容、重复结束 | 实际笔记内容、空/单问题 Session、无重复事实/检查点 |
| 中断恢复、全新进程、跨目标/领域隔离 | 独立 CLI 进程读取；无关损坏 Goal/Track 不影响当前读取 |
| 结束不自动完成 Sprint | 规划状态文件逐字节不变 |
| 保存异常不破坏既有数据 | replace 失败、提交后中断、笔记/索引失败、修复与冲突保留 |
| 精简上下文与最近 N 次 | 正常缓存下实际只打开最新目标 Session；事实分页与省略计数 |
| 新旧兼容与文档示例 | 原 75 项保留；空 Phase 1 sessions、legacy 只读、64 条文档命令 |
| ArrayList 端到端 | 问题与练习 → 两个薄弱点 → 保存 → 新进程交接 → 新 Session；核对 JSON/Markdown 原文 |

独立结构校验也通过：临时 Hub 中 1 Goal、1 Track、1 completed Session；保存 10 条事实、2 个检查点、2 个薄弱点、1 项练习支持的验收证据及 1 个未解决问题，新进程恢复这些内容；Sprint 文件字节不变。`validate` 返回 valid=true、schema_version=2。临时验证报告保存在忽略目录 `.test-tmp/phase2a-validation.json`。

Skill quick_validate 与 Python 编译检查已通过，差异空白检查无错误。未运行 Linux/macOS 测试、硬件断电试验、多年大数据压力测试或真实用户数据迁移，不将这些记为通过。

## 已知限制与 Phase 2B 接口

- Python 校验结构与引用，不能证明摘录真实或用户真正掌握。交接质量仍依赖 Agent 据实整理，旧重点不会自动变成全 Track 能力汇总。
- 单份 Session JSON 的校验和写入仍处理整份记录；AI 读取有分页和精简摘要。索引重建会读取本 Track 历史，不扫描其他目标。
- 本地锁和原子替换不是多文件数据库事务。派生文件可恢复；残留锁/暂存目录、权威损坏或笔记冲突需人工核对。索引签名与摘要用于事故检测，不是安全签名。
- 没有自动导入旧笔记、共享知识、复习调度、教学策略、FSRS、向量数据库、Web 前端或多 Agent 系统。

Phase 2B 可复用 context/list/show 的读取接口、checkpoint 的事实批次、独立 transition 的规划转换，以及稳定事实 ID、basis、sources、Sprint 快照和预留 knowledge_ids/review_candidates。不得把未来推断反写为本阶段的原始学习事实。
