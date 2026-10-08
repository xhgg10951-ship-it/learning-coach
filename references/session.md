# Session：第一阶段兼容边界

Session 表示用户本次选择的一段学习活动，建议约 60 分钟，可按难度和意愿调整。用户可以选当前 Sprint 相关主题，也可以学习计划外内容，可以随时结束。选择或结束主题本身不会完成 Sprint。

## 开始一次学习的结构接口

先运行 `current`，按需读取当前 Goal/Track 说明和当前单元的目标、验收标准。只读取相关资料，不执行过期检查，不加载全库旧笔记来模拟尚未实现的跨对话续学。

以下示例沿用 [planning.md](planning.md) 中的 `planning-demo` 数据。`session-spec` 返回包含目标、领域、可选 Sprint、主题和建议分钟数的兼容描述，不创建记录、不分配 Session 生命周期、不写入 `sessions/`：

```shell
python scripts/learning.py --hub ./planning-demo session-spec --goal java-backend --track spring-boot --sprint SP001 --topic "理解启动入口与请求处理" --minutes 60
python scripts/learning.py --hub ./planning-demo session-spec --goal java-backend --track spring-boot --topic "用户临时选择：配置文件基础" --minutes 30
```

第二条不绑定 Sprint。未来的数据结构不能强制实际学习内容归属某个 Sprint。展示主题、预计时长与关联的验收要求即可；说明用户可以更换内容或随时停止。可参考 [session 模板](../resources/templates/session.md)，它只是接口展示说明。

## 用户结束或要求生成笔记时

立即尊重结束意愿。第一阶段不创建持久化 Session、不生成学习笔记、不触发练习批改、画像更新或自动验收。清楚说明当前范围；若用户明确要求完成或跳过 Sprint，则转入 [planning.md](planning.md)，由 Python 校验和记录该独立操作。

原版本中学习中答疑、热身题、出题批改、结束后笔记、按笔记更新画像等设计保留为后续阶段需求。本次不实现这些教学闭环，也不把它们伪装成已落盘能力。普通回答用户当下的问题无需创建 Session 状态。

## 旧记录保留

旧 `goals/<goal_id>/sessions/` 笔记保持原样，可人工查看，旧版进度读取会明确标为旧记录。旧 [session 模板](../resources/templates/legacy/session.md) 仅供辨识格式，不适用于新数据写入。第二阶段再设计 Session ID、生命周期、持久化实际内容和续学接口；本阶段不自动转换旧笔记，不推断其中的掌握结论。
