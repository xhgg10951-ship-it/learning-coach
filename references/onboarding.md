# 画像与目标创建

## 最少必要信息

读取 `<hub>/profile.md`（如果存在），复用已有信息，避免重复访谈。缺少信息时一次询问必要项，允许跳过：称呼、背景、相关技能、资料语言与形式偏好、预算。默认优先中文资料。

每个 Goal 保留：目标描述、当前水平与已学内容、动机、期望达到的能力。截止日期或可用时间可以作为用户偏好写入说明，但不决定状态、ID 或自动推进。当前水平以用户自报或已有材料为准，区分自报与已验收结果。本阶段不实现自动水平测试；旧测试结果可作为带来源的画像材料保留，不自动转换成新单元的完成状态。

把重要画像和粗粒度 Track 方案展示给用户；明确授权后执行。命令在 Skill 根目录运行，下例使用独立的 `./learning-hub-demo` 数据目录：

```shell
python scripts/learning.py --hub ./learning-hub-demo init
python scripts/learning.py --hub ./learning-hub-demo goal-create --id java-backend --title "Java 后端开发" --description "独立开发后端服务" --level "会基本编程，尚未使用 Java" --motivation "工作需要" --ability "能够开发、测试并部署基础 REST API"
python scripts/learning.py --hub ./learning-hub-demo goal-create --id english --title "英语口语" --description "应对工作中的日常交流" --level "能阅读简单英文" --motivation "工作交流" --ability "能用英语说明项目进展并回答基本问题"
```

`goal-create` 只创建目标，不自动创建详细计划。`--id` 可省略，由程序生成稳定 ID；一旦创建不随标题变化而重命名。目标使用不同目录，当前进度不会跨 Goal 同步。

## 保存与更新画像

- 基础画像使用 [profile 模板](../resources/templates/profile.md)，保存到 `<hub>/profile.md`。这是可人工编辑的描述文件，不包含任务状态。
- Goal 的目标描述、当前水平、动机、期望能力四项受管理画像与状态，统一以 `goals/<goal_id>/state.json` 为权威。`goal.md` 保存补充背景、偏好和用户原始说明，参考 [goal 模板](../resources/templates/goal.md)。
- 更新目标画像使用 `update --kind goal`，把来源及调整原因写入 `--note`；不得根据一次学习时长推断水平提升。

```shell
python scripts/learning.py --hub ./learning-hub-demo update --goal java-backend --kind goal --level "用户自报已掌握 Java 基本语法" --ability "独立实现带参数校验的 REST API" --note "用户修正了起点和期望能力"
```

允许在 Markdown 补充资料偏好、已学经历和用户明确提供的事实。不要复制 JSON 中的状态、验收结果或历史作为另一套可维护记录。

## 下一步

根据 [syllabus.md](syllabus.md) 只建立粗粒度 Track 结构。用户选择当前 Track 后，按 [planning.md](planning.md) 创建一个 Milestone 及其第一个 Sprint。不要在新建 Goal 时规划所有领域的未来阶段。

暂停、恢复或完成 Goal 使用 `transition --kind goal`，完成需要所有 Track 已完成及独立的能力验收说明。暂停仅挂起下属操作，保留下属状态，切换当前 Goal 不等于暂停原 Goal。
