# Phase 2B 教学数据与 CLI

`scripts/teaching.py` 提供纯读取的证据投影和教学字段校验。没有定时器、题数计数器、掌握分数或自动规划转换；自然语言理解、任务选择与批改由使用 [教学 Skill](../references/teaching.md) 的 Agent 负责。

## 读取

```text
python scripts/learning.py --hub <hub> teaching-context [--goal G --track T] [--session SE-...] [--sprint SP001] [--topic ArrayList] [--limit 10]
```

goal/track 同时提供或同时省略。默认使用 active Session 关联的 Sprint，否则使用当前 active Sprint；显式 sprint 覆盖选择。使用同 Track 的匹配 Sprint 或主题的最近 Session。显式 Session 与其直接 previous_session_id 优先保留，不受 limit 挤出；模式只从这条明确关联恢复，避免被其他较新记录覆盖。无指定 Session 时用最近相关记录。跨 Goal/Track 不查找或共享知识。

输出含 profiles（原始公共/Goal/Track 背景）、current_milestone/current_sprint、teaching_state、criteria（每项标准的状态及证据）、原始 exercises、薄弱点和相关 Session 摘要。Track 现有结构没有单独 level 字段，当前水平来自 Track 原始说明和 Session 证据，不擅自回填画像。history 表明选中记录、截断数和范围；recommendation 是带依据的建议，lifecycle_action 恒为 none。历史读取不完整时不建议 Sprint 完成。读取不改变任何文件。

每条标准保留所有已加载的当前有效证据，最新的独立批改决定 verified 或 needs_consolidation；没有独立证据时，自报单列 user_reported，否则 unverified。旧 Sprint 目标不匹配的记录不参与当前验收；同目标下只匹配仍相同的标准文本。这个投影不能证明引用真实或批改语义正确。

证据同时显示保存时间 at 和表现来源时间 observed_at。更正旧作答或补写它的证据时沿引用保留原表现时间，避免一次迟来的旧记录纠错覆盖后来真实暴露的薄弱点。

## Session 兼容

沿用 Phase 2A 的 record.json、追加 events、检查点摘要、幂等键、笔记投影、锁和原子提交。只有保存下述新字段的记录才使用 `session_version=3`；既有 v1/v2 读取、重试和 repair 均不自动迁移。v3 支持原有 correction；纠错后笔记重建可识别 v1/v2/v3 历史前缀。旧程序会拒绝 v3，不能拿旧程序写回新记录。

`session-context` / `session-resume` 的各 Session 摘要新增 teaching_state 和 criteria_evidence；完整画像及跨 Session 验收使用 teaching-context。教学状态通过原始教学事件计算，不在 handoff 或 extensions 再维护副本。相关证据撤回后，依赖它的 teaching 事件失效；用户偏好事件可独立记录，避免误把偏好当作能力判断。

## 事件扩展

所有事件继续要求 id/kind/text/basis/sources，来源保存 ref 与原文 quote。

`kind=teaching` 必须包含 teaching 对象：

```json
{
  "id": "mode-quick", "kind": "teaching", "text": "用户要求讲快一点，本轮改用重点与 Demo。",
  "basis": "user_report", "sources": [{"ref": "conversation/user/4", "quote": "讲快一点，先不讲原理"}],
  "teaching": {
    "mode": "quick", "pace": "fast", "depth": "overview", "exercise_policy": "allowed",
    "difficulty": "已有集合基础，从 ArrayList 的异常边界和批量操作实例开始",
    "reason": "按用户本轮指令加速；能力判断仍以作答为准。"
  }
}
```

mode: adaptive/quick/guided/deep/practice；pace: fast/balanced/slow；depth: overview/standard/deep；exercise_policy: allowed/declined。difficulty 是有依据的文字描述，不能由时长计算。reason 必填。basis 只允许 user_report 或 ai_assessment；后者引用本 Session 的练习时使用 related_ids，撤回依据会使这条教学推断失效。

exercise 新增可选的 assessment 对象（Phase 2B 新练习应填写；旧练习继续可读）：

```json
{
  "form": "代码阅读与复杂度分析",
  "error_type": "conceptual",
  "checks": [
    {"criterion": "准确区分 size 与容量", "outcome": "met", "reason": "实际答案正确区分二者"},
    {"criterion": "解释批量复制复杂度", "outcome": "not_met", "reason": "误把一次方法调用当作常数成本"}
  ]
}
```

form 是开放文本，适应不同学科。error_type 为 none/wording/conceptual/reasoning/implementation/procedure/mixed/unassessed。checks 的标准必须唯一、精确匹配本 Session Sprint 快照，结果为 met/partial/not_met/unverified，逐项附 reason。综合题的整体 result 用 partial，允许部分 checks 达标；后续 evidence.met 可关联这些局部达标结果。含 checks 的练习不能凭整体 correct 为未覆盖标准提供达标证据。计划外任务用空 checks，不伪造 Sprint 关联。

not_assessed 只能 unassessed/unverified。无答案不可批改。已验证结论仍要求 exercise_verified 和有效作答；讲解不计为掌握，用户自报不自动升级。

上述 JSON 是协议示意，不是真实用户学习证据。批次仍用 operation_id/events/handoff，结束与更正完全复用 [Session 协议](session-schema.md)。
