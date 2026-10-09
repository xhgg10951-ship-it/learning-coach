# Session：真实学习记录与跨对话续学

Session 是用户本次选定的一段学习，主题可以偏离 Sprint，也可以不关联 Sprint。日期只是元数据，不驱动进度；结束 Session 不等于完成 Sprint。

## Agent 执行规则

1. **开始学习**：读取 `session-context`（无当前位置先 `current` / `select`）。简述当前目标和建议，让用户选择主题；已有明确主题就采用。用户明确开始跟踪学习视为授权，调用 `session-start`，记录返回的稳定 ID。普通一次性答疑、不要求保存的普通聊天和明确拒绝记录时不调用写接口，只在对话内答疑。
2. **继续上次学习**：新对话先读取精简上下文；`mode=resume` 表示尚未结束，用 `session-resume` 读取同一个 ID；`mode=new_session` 表示上一份已完成，参考交接后用新 request-id 调用 `session-start --from-session`。用户可以拒绝建议，学习其他内容。不重新打开已结束 Session，不把旧事实复制成新学习事件。
3. **学习过程**：根据真实提问、关键解释、练习及理解反馈整理批量 JSON。在重要概念告一段落、集中批改后、准备切换对话或用户要求时调用一次 `session-checkpoint`。无需逐题写多份文件。没有实际作答就不能记录正确答案或掌握结论；未做练习不是失败。
4. **结束并保存**：收到“结束并记笔记”“今天就到这里，记录一下”“总结本次学习并保存”等指令，立即停止教学，不强制改错。将尚未落盘的真实事实、验收证据和交接整理为最后一个批次，调用 `session-finish`。如果之前只是未保存的聊天，先在已选 Goal/Track 下创建 Session，再仅保存本次明确授权范围；缺少范围时询问归属，不自行创建目标体系。用户已明确授权，不机械地再次确认。
5. **反馈结果**：成功后给出短摘要、仍需关注的内容和实际保存路径。失败不声称成功，读取权威记录判断是否已提交后重试。Sprint 验收由 Agent 对照证据解释，保留自报与验证的区别；用户明确要求完成 Sprint 时另走 [planning.md](planning.md) 的 `transition`。

用户只说停止而没有要求笔记时，不自行调用 finish 生成笔记；已有获准保存的检查点保持 active，可以后恢复。新建和恢复学习要求 Goal/Track active；上层暂停后仍可保存已经发生的事实并结束，避免丢失记录。

## CLI 和读取范围

所有写操作显式指定 `--goal G --track T`。`session-context`、`session-list` 可省略两者使用当前指针，不能只给其中一个。命令在 Skill 根目录执行，`--hub` 位于子命令前。

| 命令 | 关键参数与结果 |
|---|---|
| `session-start` | `--topic`、`--request-id`，可选 `--sprint`、`--from-session`；返回稳定 Session ID |
| `session-checkpoint` | `--session`、`--data file.json` 或 `--data -`（stdin）；追加一批事实与交接 |
| `session-finish` | 同上；原子完成记录，再生成唯一 `note.md` |
| `session-resume` | `--session`；只读返回 active 会话，不产生重复学习事件 |
| `session-context` | 默认最近 1 次 completed 和当前 active，`--limit 1..10`；不加载其他 Track 历史 |
| `session-list` | `--limit 1..100`，默认 5；按开始时间倒序返回摘要 |
| `session-show` | `--session`、`--offset`、`--limit 1..100`；事实分页，按需核对原始记录 |
| `session-repair` | 重建派生索引、补写缺失笔记；不改写权威事实，不覆盖冲突笔记 |

`session-context` 包含当前 Goal/Track、active Milestone/Sprint、是否允许学习、当前/最近 Session 的实际内容摘要、带 basis 的重点事实、已练习验证的验收证据、薄弱点、未解决问题、理解反馈、下一步建议及笔记路径。只返回 Agent 选择的最多 20 条重点事实，说明省略的事实数量；摘要不足时分页 `session-show` 或读取指定笔记。这是所选 Session 的交接，不是全领域能力评估或完整历史聚合。

## 批量 JSON 合约

详细字段见 [Session 数据结构](../docs/session-schema.md)。输入必须包含 `operation_id`、`events`、`handoff`，可同时保存最多 100 条事实。JSON 文件或 stdin 避免 shell 引号问题。

每条事实有 Session 内稳定唯一 `id`、`kind`、`text`、`basis`、`sources`。sources 必须保留真实消息/资料位置和原话摘录，即使原聊天以后不可访问，也能核对保存内容。不要伪造链接、引用、提问、答案或结果。`basis`：

- `user_report`：用户明确说了什么，包括提问、理解/不理解反馈；不升级成练习验证。
- `ai_assessment`：AI 的解释或判断，明确其推断性质。
- `exercise_verified`：基于已经作答且批改的练习；结论须用 `related_ids` 关联练习。只有正确练习支持的达标证据进入 `verified_abilities`。
- `unverified`：讲过但未验证、尚未解决或无法判断的内容。

`handoff.summary` 总结实际发生的学习；`next_step` 是建议，允许用户拒绝；`focus_ids` 选出续学所需的事实 ID。保留相关薄弱点和未解决问题，不因 AI 讲解过就从交接中删除。每次 checkpoint 更新交接，旧交接保留在检查点历史中。

改正已存内容时追加新事实，用 `supersedes` 引用原事实，交接使用新 ID；原始事实不会删除。引用必须指向已经保存或本批较早出现的事实。不要对相同学习事件使用新 ID 重复追加。

`--request-id` 和 `operation_id` 使用稳定英文小写 slug，例如 `arraylist-start-1`。相同请求重试必须保持 ID 与内容一致；ID 相同而内容不同会报错。重复结束不再次生成学习事件或笔记。completed 会话需要补充新内容时，新开 Session 并引用旧记录。

## 可运行的隔离示例

下面全部是**模拟学习数据**，不得用于真实用户记录。`<SESSION_ID>` 替换为第一条 `session-start` 输出的 `id`；新进程只需要 Hub 路径。示例 JSON 位于 [检查点](../resources/examples/session-checkpoint.json) 和 [结束批次](../resources/examples/session-finish.json)，测试会执行这些示例并检查实际文件。

```shell
python scripts/learning.py --hub ./session-demo init
python scripts/learning.py --hub ./session-demo goal-create --id java --title "Java 后端"
python scripts/learning.py --hub ./session-demo track-create --goal java --id core --title "Java 基础"
python scripts/learning.py --hub ./session-demo select --goal java --track core
python scripts/learning.py --hub ./session-demo milestone-create --goal java --track core --title "集合基础" --objective "使用并解释集合" --criterion "能解释集合使用"
python scripts/learning.py --hub ./session-demo sprint-create --goal java --track core --milestone M001 --title "ArrayList" --objective "区分 size 和容量" --criterion "在具体例子中判断 size" --criterion "解释扩容复制"
python scripts/learning.py --hub ./session-demo session-context
python scripts/learning.py --hub ./session-demo session-start --goal java --track core --sprint SP001 --topic "Java ArrayList" --request-id arraylist-start
python scripts/learning.py --hub ./session-demo session-checkpoint --goal java --track core --session <SESSION_ID> --data resources/examples/session-checkpoint.json
python scripts/learning.py --hub ./session-demo session-resume --goal java --track core --session <SESSION_ID>
python scripts/learning.py --hub ./session-demo session-finish --goal java --track core --session <SESSION_ID> --data resources/examples/session-finish.json
python scripts/learning.py --hub ./session-demo session-finish --goal java --track core --session <SESSION_ID> --data resources/examples/session-finish.json
python scripts/learning.py --hub ./session-demo session-context
python scripts/learning.py --hub ./session-demo session-list --limit 3
python scripts/learning.py --hub ./session-demo session-show --goal java --track core --session <SESSION_ID> --offset 0 --limit 5
python scripts/learning.py --hub ./session-demo session-repair --goal java --track core
python scripts/learning.py --hub ./session-demo validate
python scripts/learning.py --hub ./session-demo session-start --goal java --track core --topic "扩容复制，也可改学其他主题" --request-id arraylist-next --from-session <SESSION_ID>
```

## 兼容与故障处理

规划 schema v2 不变，Session 独立采用 `session_version=1`。第一阶段空 `sessions/` 无须迁移，读取不会创建索引。旧版 Goal 级笔记原样只读，通过 `progress.py` 查看，不能自动解释为新版验收结果。

兼容 `session-spec` 仍只返回临时结构，不负责真正开始学习。以下示例沿用 [planning.md](planning.md) 的数据：

```shell
python scripts/learning.py --hub ./planning-demo session-spec --goal java-backend --track spring-boot --sprint SP001 --topic "理解启动入口与请求处理" --minutes 60
python scripts/learning.py --hub ./planning-demo session-spec --goal java-backend --track spring-boot --topic "用户临时选择：配置文件基础" --minutes 30
```

异常时先读 `session-context` / `session-show`：记录可能已原子提交，而笔记或索引尚未生成。重试原请求或运行 `session-repair`。缺失/过期索引在读取时仅内存重建，返回 `index_status=rebuilt_in_memory`；不会偷偷重写文件。`validate` 会要求补齐派生文件。损坏的权威 JSON、未知版本、笔记冲突、非法引用及残留暂存文件报错并保留。残留写锁须先确认没有写入进程，再备份人工处理；程序不会抢锁。

程序只检查结构和引用关系，不能证明文字内容真实或用户真正掌握。使用 [Session 模板](../resources/templates/session.md) 检查笔记内容，不手工维护第二份状态表。本阶段不做自适应策略、自动画像、复习调度或知识共享。
