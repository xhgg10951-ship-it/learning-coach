# Session schema 与恢复协议

实现位于 `scripts/sessions.py`，由 `scripts/learning.py` 统一提供 JSON CLI，只使用 Python 标准库。Agent 工作流和可运行示例见 [session.md](../references/session.md)。

## 文件与权威来源

```text
goals/<G>/tracks/<T>/sessions/
  index.json                    # 可重建的定位索引
  SE-<32 位 UUID>/
    record.json                 # 此 Session 的唯一权威文件
    note.md                     # completed 后的确定性投影
```

规划文件保持 `schema_version=2`，Session 文件使用相同封装版本并增加 `session_version=1`。不迁移、不回填、不改写已有规划文件。空 sessions 目录保持第一阶段行为；旧版 Goal 级笔记仍由 progress 只读读取。

| record.json 字段 | 约定 |
|---|---|
| `kind`、`id` | `session`、Python 分配的 `SE-` 加 UUID4；不依赖日期或标题 |
| `goal_id`、`track_id` | 与目录严格匹配；写操作显式限定两个范围 |
| `sprint_id`、`sprint_snapshot` | 可为 null；关联时保存 ID、Milestone ID、objective、criteria 快照，规划修改不重解释旧证据 |
| `topic` | 实际主题，最多 500 字符，可为计划外内容 |
| `status` | active/completed；中断保持 active，不靠时间猜状态 |
| `created_at`、`updated_at`、`completed_at` | Python 生成 UTC ISO 时间，包含时区；完成前 completed_at 为 null |
| `start_request_id` | 调用方稳定请求键，同 Track 唯一，用于开始操作重试 |
| `previous_session_id` | 同 Track 已结束记录 ID 或 null；只关联，不复制事实 |
| `events` | 顺序追加的事实，不覆盖旧内容 |
| `checkpoints` | operation_id、kind、at、event_ids、当时的 handoff、内容 SHA-256；顺序覆盖全部事实，finish 必须最后 |
| `handoff` | 最后检查点的交接；尚无检查点为 null |
| `extensions` | knowledge_ids 和 review_candidates 空数组，仅预留 |

同 Track 最多一份 active Session，不同 Track 独立保留。select 不修改 Session。completed 仅表示本次学习收束，不触发 Sprint/Milestone/Track/Goal 转换。

## 事实与输入校验

每条事实必填 `id`、`kind`、`text`、`basis`、`sources`。ID 使用小写字母、数字和连字符，最长 64，Session 内唯一；text 最长 8000 字符。sources 为 1～8 个 `{ref, quote}`，ref 最长 500、quote 最长 4000 字符，保留真实位置与摘录，不要求永久在线链接。

basis 只能是 user_report（用户自报）、ai_assessment（AI 判断）、exercise_verified（练习验证）、unverified（尚未验证）。

| kind | 专属字段与约束 |
|---|---|
| content | 实际学习内容 |
| question | 用户实质提问，必须 user_report |
| explanation | 关键解释，不能标为 exercise_verified |
| exercise | 必填 prompt、answer、result、feedback；result 为 correct/partial/incorrect/not_assessed，空答案只能 not_assessed |
| weakness | 真实薄弱点与依据 |
| unresolved | 未解决问题与来源 |
| understanding | understanding 为 understood/not_understood/unsure；必须 user_report |
| evidence | criterion 精确匹配 Sprint 快照标准；outcome 为 met/partial/not_met/unverified |

可选 `related_ids`、`supersedes` 引用已保存或本批较早出现的事实，不允许缺失、循环或前向引用。supersedes 表示修订，保留旧原文；当前重点不能指向已被替代的事实。可选 knowledge_ids/review_candidates 字符串 ID 数组仅保存，不执行知识关联或复习逻辑。

非 exercise 的 exercise_verified 结论必须关联已作答且批改、basis 为 exercise_verified 的练习。evidence 的 met 还需正确练习支持。用户自报的 met 不进入已验证能力。程序不能证明引用真实或结论语义正确，Agent 必须从实际会话整理，不能虚构或把讲解视为掌握。

## 检查点与精简交接

checkpoint / finish 输入三个字段：

```json
{
  "operation_id": "stable-request-key",
  "events": [],
  "handoff": {
    "summary": "真实摘要，最多 1200 字符",
    "next_step": "可拒绝的建议，最多 800 字符",
    "focus_ids": []
  }
}
```

events 每批 0～100 条，handoff 每次必填。focus_ids 最多 20 个，引用现存有效事实。无练习、只有一个问题、未完成 Sprint 或没有学习事实都可结束，不得为填满笔记编造内容。

context 默认只展开当前 Track 的 active 和最近一份 completed。返回交接、重点事实（text 最多 500 字符，截断带标记）、verified_abilities、unstable_points、unresolved_questions、understanding、omitted_event_count 与路径。仅覆盖选定交接，不是整个 Track 能力汇总；不足时 session-show 按 offset/limit 分页读取。正常读取不加载其他 Session 事实或其他 Goal/Track 历史；规划依赖检查沿用第一阶段规则。

索引保存定位摘要（ID、状态、主题、时间、请求键、关联 ID），以及记录文件大小/修改时间签名和索引内容摘要。失效时会在内存扫描本 Track 全部 Session 恢复定位，返回 rebuilt_in_memory；不将全部历史返回 AI，也不偷偷写文件。Python 校验仍读完整单份 JSON，每次 checkpoint 原子重写当前 Session，尚未做大文件分片。

## 提交与恢复

复用 Hub 互斥锁、安全路径、同目录临时文件、flush/fsync 与原子替换。开始时准备完整目录再重命名发布。

提交顺序：校验整个批次 → 原子替换 record.json → 结束时生成 note.md → 刷新 index.json。record.json 是唯一提交点；没有跨文件数据库事务。

| 故障位置 | 恢复方式 |
|---|---|
| 记录提交前 | 既有原字节不变，重试原请求 |
| 记录提交后 | 新事实已保存，重试原 operation_id 不重复追加 |
| 笔记/索引失败 | context 从记录恢复；重试或 session-repair 补齐派生文件 |
| 笔记冲突/人工修改 | 保留并报错，不自动覆盖；先备份核对 |
| 权威 JSON 损坏、版本未知、摘要不一致 | 报错保留，人工从可信备份恢复；repair 不猜事实 |
| 残留锁/暂存文件 | 确认没有写入者后人工检查，程序不抢锁或删除 |

相同 operation_id、相同内容重试为无操作；同 ID 不同内容/操作报错。已完成记录的新 finish 请求仅在无新事实且 handoff 相同时按无操作处理，否则拒绝。去重以请求 ID 为边界，无法可靠识别不同 ID 下语义相同的自然语言事实。

validate 全库只读检查结构、范围、历史摘要、引用、状态、笔记与索引，不自动迁移。mtime/size 和 SHA-256 用于事故检测和缓存一致性，不是防恶意篡改签名。网络盘、多机器并发、硬件断电持久性未验证。

## Phase 2B 接口

可通过 session-context 获取交接、session-list / session-show 分页取证、批量 checkpoint 追加观察，按独立 transition 提交用户授权的规划转换。保留事实 ID、sources、basis、Sprint 快照和 knowledge_ids/review_candidates；后续画像、共享知识或复习引擎需有自己的版本与授权边界，不得改写原始事实。
