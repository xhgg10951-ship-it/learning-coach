# Phase 2A 第二轮审查核对与修复

日期：2026-10-10。核对起点为 `0011e4017507de4bf951047c9b57a8dfd2839c8b`，当前分支 `feature/phase2a-session-persistence`，起始工作区干净。

## 逐项核对

三条问题均成立，没有需要驳回的事实性意见。先加入三个复现回归，在未修改实现的 0011e40 上运行：3 项全部失败，170.599 秒，日志位于 `.test-tmp/review2-reproduction.log`。

| 报告项 | 核对证据 | 修复 |
|---|---|---|
| P1 已结束后无法撤回错误证据 | 普通 checkpoint 拒绝 completed；新 Session 的 supersedes 不能引用原 Session。写普通解释后旧 claim 仍为 current；新增 session-correct 测试失败于缺少命令 | 专用纠错命令在原 Session 追加更正；共享有效性判断撤回旧达标证据，更新交接和笔记；保留原事实、完成状态及完成时间 |
| P2 历史超过 100 条无法翻页 | 通过真实 start/finish 创建并结束 101 份记录，首屏仅 100 条；旧 CLI 拒绝 --offset 100 | 增加 offset/next_offset，保留单页大小限制，默认排序不变；回归检查两页覆盖全部真实文件 ID |
| P2 损坏记录泄漏堆栈 | 仅反转 finish 检查点的 event_ids，旧 session-context 退出码 1，KeyError: ex-1 | 计算交接有效性前先核验事实的连续分配顺序；load 的数据校验边界返回带文件路径的 LearningError，CLI 为 JSON error / 退出码 2 |

P1 是原本的设计缺口，不是自动编造事实；本轮只补齐 Session 内的受控纠错，不实现跨会话知识聚合或自动能力判断。

## 实施前约定与最终接口

- 保持 record.json 为单份 Session 的唯一权威，继续使用现有锁和原子提交，不增加知识系统。
- 新增显式 session-correct，输入 operation_id、reason、events、handoff。仅适用于 completed，追加更正及与更正关联的事实；不重新打开学习，不修改原完成时间或任何规划状态。新的学习仍开新 Session。
- 正常创建与保存继续使用 session_version=1；首次显式结束后纠错升级该份记录到 session_version=2。版本 2 增加 finish 后的 correction 检查点和 reason，原始事实及检查点保留。读取旧记录不会迁移。旧程序会拒绝版本 2，不能用旧程序写更正后的文件。
- 更正更新当前交接，笔记用同一有效性规则呈现。只允许替换与权威历史确定性渲染逐字节匹配的派生笔记；提交后中断可以从历史版本识别旧笔记并重试，人工修改拒绝覆盖。
- session-list 增加 offset/next_offset，保留每页 1～100 条限制及既有排序。
- 在交接有效性计算前核对检查点与事实顺序；权威记录损坏使用带路径的 LearningError，CLI 继续返回 JSON 错误、退出码 2。

所有复现、故障注入、数据结构校验和 CLI 验证均使用独立临时 Hub，不读取或修改正式学习数据。

## 实际验证

修改前全量基线：`python -B -m unittest discover -s tests -v`，122 项通过，121.412 秒。使用允许访问独立临时目录的进程；日志位于忽略目录 `.test-tmp/review2-baseline.log`。

新增 15 项回归，包括三个原始问题、纠错重试及再次纠错、无关/无效输入、纠错后的前序恢复、暂停后的纠错及历史排序、人工笔记保护、记录提交失败、笔记失败重试、历史笔记修复、分页边界与读取范围、损坏检查点变体、索引故障，以及真实子进程提交后退出。

第一次边界运行：13 项中 12 项通过，1 项因新测试的 transition 参数顺序写错而报错；已修正夹具。随后针对修正夹具与新加故障场景运行 3 项，全部通过（4.968 秒）。文档示例回归 2 项通过（11.095 秒），实际执行更正、幂等重试与翻页。Skill quick_validate 和 git diff --check 通过。

最终执行 `python -B -m unittest discover -s tests -v`：**137 项全部通过，0 项失败，311.036 秒**。包括原有 122 项测试和新增 15 项回归；Session 测试共 62 项。测试中的独立进程执行了 validate 数据结构校验、纠错后续学和文档 CLI 示例；旧结构兼容、规划状态和文件保护测试继续通过。完整日志位于忽略目录 `.test-tmp/review2-full-tests.log`。

进程退出回归在记录提交后令子进程 os._exit(73)，断言新进程能读取更正后的权威事实，残留写锁阻止继续写入。测试已确认自己的子进程退出，才移走临时锁；随后 repair 和重复纠错恢复笔记且权威记录字节不变。生产程序仍不会抢锁或自动清锁。

## 文件与兼容范围

- scripts/sessions.py：受控更正、版本兼容、历史笔记安全重建、列表分页及损坏记录诊断。
- tests/test_sessions.py、tests/test_skill.py：新增回归与实际文档执行断言。
- resources/examples/session-correction.json：明确标为模拟数据的可执行纠错批次。
- SKILL.md、references/session.md、resources/templates/session.md：用户纠错意图、输入、保留历史和笔记呈现。
- docs/session-schema.md、docs/architecture.md：当前协议、状态和兼容说明。
- docs/phase2a-design.md、docs/phase2a-delivery.md、docs/phase2a-review-fixes.md：保留先前交付事实，链接到本轮记录；本文件记录本轮验证。

没有修改 scripts/learning.py、progress.py、Phase 1 状态转换或正式用户 Hub。Session 纠错后仍不能 resume；新的学习仍必须新建 Session。只有结束后更正这一显式写操作升级单份 Session，不批量迁移历史。

## 尚存风险

- 来源摘录、批改及自然语言交接的真实性仍由 Agent 和用户核对，未验证完整真实教学闭环；程序只验证结构、引用和明确的更正关系。
- 更正不会自动传播到其他 Session 已写下的总结或已完成 Sprint 的验收。无当前交接时引用前序会读到更正结果；已有自己的交接仍优先自身。需要复核时按 ID 读取原记录，不能把它当跨会话知识系统。
- 人工修改过的笔记无法安全自动覆盖，纠错会在提交前报冲突；提交后才出现人工修改时 repair 也会保留并报错，需要备份核对。
- 版本 2 记录不能交给只支持版本 1 的旧程序处理；这是明确的兼容边界。当前程序仍读取版本 1，旧版 Goal 级笔记仍只读。
- 偏移分页不提供并发快照；分页期间新增记录可能导致重复或漏项，应在稳定历史上重读。目录枚举、start 全量校验、单 Session JSON 及纠错历史渲染仍随数据增长，未做长期压力测试。
- 仅在 Windows 验证；真实子进程退出不等于硬件断电、网络盘并发或跨平台保证。残留锁、暂存文件和损坏权威文件仍需人工核对。
