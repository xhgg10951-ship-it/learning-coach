# Phase 2A 独立审查核对与修复

日期：2026-10-10。核对起点为 `5669b1b7f2aff5504911e203c8ef21f28a20ed8d`，分支保持 `feature/phase2a-session-persistence`，起始工作区干净。重复出现的审查文本按三项独立问题核对。

## 逐项结论与证据

三个问题均确认成立，没有需要驳回的事实性意见。先添加三个回归测试，在未修改实现时执行：三项全部失败，分别捕获笔记缺少有效性标记、默认返回 B 而非显式前序 A，以及一次 checkpoint 的四次 load 调用覆盖全部三份 Session。

| 审查项 | 代码原因 | 修复及验证 |
|---|---|---|
| P0 纠正后的达标证据仍在笔记中呈现为有效 | 原 check_handoff 排除失效重点，render_note 却直接显示所有历史事件的 basis/outcome | 抽出 event_validity，共用于交接、精简摘要、笔记和分页展示。旧练习标为已更正，派生验证结论标为依据已失效，给出相关 ID，原文及历史 met 不删除 |
| P1 C 指定从 A 继续却读取 B | 原 context 仅按完成时间选择，resume 只返回 C，未跟随 previous_session_id | 当前 handoff 为空时仅展开显式直接前序；context 在限额内优先放 A，resume 返回 reference_session；continuation 明示来源和交接。C 的空事件及空 handoff 保持原状，不复制历史 |
| P2 每个 checkpoint 完整读取历史 | 原 write_index 无条件调用 catalog(force=True) | 签名与缓存结构合法时复用未变化条目，仅加载变化记录。三份 Session 示例由四次 load 降为两次，均为当前 Session；validate/repair 和 start 前置检查保留全量校验 |

P2 是本地读取成本增长，不是向模型输入全部历史；这一边界与审查报告一致。没有依据该问题引入数据库、事件框架、共享知识或其他 Phase 2B 功能。

当前实现可查 [sessions.py](../scripts/sessions.py) 的 event_validity、render_note、continuation、context、catalog、write_index；复现与回归在 [test_sessions.py](../tests/test_sessions.py) 的 test_review_*。

## 兼容与保护

- 不修改 schema v2 或 session_version=1；有效性、交接来源都是只读投影字段，权威学习事实不变。
- 保留原字节的历史事实和检查点；只在新笔记中解释哪些旧结论已失效。新的独立有效证据仍可正常显示为已验证。
- 原程序生成的纠错笔记会因缺少标记被 validate 报告。仅显式 session-repair 且旧笔记逐字节匹配原确定性渲染结果时升级，记录 JSON 不变；任何人工补充均拒绝覆盖。修复前真实生成的模拟笔记已保存为兼容测试夹具。
- 读取、resume 和 finish 重试不偷偷升级旧笔记。升级写入失败保留旧字节；原有写锁、路径保护与提交后重试机制保留。
- 显式前序缺失、损坏或生命周期不合法时报错，不回退到 B。已有当前 checkpoint 时优先当前交接，不加载前序；没有前序不编造交接。
- 增量索引不能替代全量检查。索引损坏时全量恢复，记录签名变化时重新校验；显式 validate/repair 即使签名没变也会读取权威 JSON。

没有执行任何正式用户 Hub 的读取、升级或写入，所有验证均使用独立临时 Hub。

## 回归与实际运行

新增 14 项回归：三个原始问题；旧笔记显式升级、人工修改保护、升级失败保护；失效传播与新证据；恢复读取范围、当前交接优先、损坏前序、无前序；变化历史重校验、坏缓存全量回退、全量检查不信任文件签名。

实际已执行的针对性验证：

- 修复前 `python -m unittest discover -s tests -p test_sessions.py -k review_ -v`：3 项失败，确认问题。
- 修复后同命令：3 项全部通过。
- 增补边界后的 Session 回归：46 项通过，42.911 秒（此后另加升级写入失败测试，纳入最终全量运行）。
- Skill quick_validate 通过，Python 编译检查和 git diff --check 通过。

最终执行 `python -m unittest discover -s tests -v`：**122 项全部通过，0 项失败，耗时 117.321 秒**。其中 Session 测试 47 项，包含新增的 14 项回归；同时通过全部第一阶段测试和实际执行 CLI 示例的 Skill 测试。测试在允许访问独立临时目录的进程中运行，日志保留在忽略目录 `.test-tmp/review-full-tests.log`。

最终澄清 Skill 中旧版数据只读与 Phase 2A 派生笔记显式修复的区别后，另执行 `python -m unittest discover -s tests -p test_skill.py -v`：2 项通过，8.644 秒。

## 修改范围

修改 scripts/sessions.py、tests/test_sessions.py、SKILL.md、references/session.md、resources/templates/session.md、docs/session-schema.md、docs/architecture.md、docs/phase2a-delivery.md；新增本核对记录和 tests/fixtures/session-note-before-validity.md。没有更改 Phase 1 规划状态转换或 progress.py。

## 尚存风险与未验证边界

- Agent 仍需正确摘录真实对话、同步更正自然语言 summary/next_step。程序能处理显式事实引用，不能判断所有自由文本是否真实或学习者是否掌握；本次没有验证完整“真实教学 → Agent 提取 → 保存”流程。
- 旧笔记只支持精确识别的原生成格式升级；人工编辑文件必须先人工核对，程序不会覆盖。
- 文件大小/mtime 是缓存新鲜度依据，不是防篡改机制。元数据被刻意保留时普通缓存读取可能不发现变化；全量 validate/repair 的回归已验证可以发现损坏。
- 目录签名枚举和索引读写仍为 O(N)，单个 Session 的校验与写入仍处理完整 JSON；start 的前置检查仍全量读取。没有长期压力测试，不能把本次读取次数回归解释为性能上限证明。
- 仍仅验证 Windows；故障测试以异常注入为主，未进行强杀进程、硬件断电或网络共享盘并发试验。残留锁、暂存文件及损坏权威记录仍需要备份后人工核对。

已确认的 P0、P1、P2 均有修复及对应回归；以上边界未被宣称为已解决。
