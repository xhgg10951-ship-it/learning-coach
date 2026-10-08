# Track 能力地图与资料

## 建立粗粒度领域

读取公共画像、当前 Goal 说明，必要时联网核对官方学习路径、考试大纲或权威课程结构。考试目标按用户的目标年份核验官方要求。结合现有水平提出相对独立的 Track，说明每个领域要解决的问题、粗略能力范围和可选前置依赖；不要为每个 Track 提前生成详细 Milestone、Sprint 或逐日任务。

Track 结构预览得到用户授权后执行，例如：

```shell
python scripts/learning.py --hub ./learning-hub-demo track-create --goal java-backend --id java-core --title "Java 基础"
python scripts/learning.py --hub ./learning-hub-demo track-create --goal java-backend --id spring-boot --title "Spring Boot" --depends-on java-core
python scripts/learning.py --hub ./learning-hub-demo track-create --goal java-backend --id mysql --title "MySQL"
python scripts/learning.py --hub ./learning-hub-demo select --goal java-backend --track spring-boot
```

`--id` 可省略，由程序生成。每个 Track 有自己的 `state.json`、Milestone、Sprint 和预留 Session 目录。可在 `track.md` 记录粗略能力范围、资料、用户偏好和未来方向，参考 [track 模板](../resources/templates/track.md)。原名 [syllabus 模板](../resources/templates/syllabus.md) 用于组织粗粒度能力地图，不再是复选框状态表。

前置依赖只表达建议，可设多项：重复 `--depends-on`。更新时传入的是完整依赖列表；使用 `update ... --clear-dependencies --note "用户决定取消前置建议"` 可以清空依赖。程序检查同一 Goal 内引用是否存在，以及自依赖和循环；它不会根据前置领域是否完成阻止用户选择或学习当前 Track。调整标题或依赖通过 CLI 记录历史，不改目录 ID：

```shell
python scripts/learning.py --hub ./learning-hub-demo update --goal java-backend --track spring-boot --kind track --title "Spring Boot 应用开发" --depends-on java-core --note "用户将领域范围聚焦到应用开发"
```

## 资料规则

原有资料核验原则继续使用，只为当前选中的 Track/Milestone/Sprint 查找必要资料。不要默认扫描所有 Goal 的详细文件。

| 字段 | 要求 |
|---|---|
| 名称 | 正式名称 |
| 作者/机构 | 可核实的作者或发布机构 |
| 版本 | 出版年、版本号或对应的软件版本；以用户目标版本为准 |
| 位置 | 已实际打开核对的 URL，或有出版社来源的 ISBN |
| 范围 | 经核验的章节、小节、页码、课时；暂未细化时注明“当前仅为领域级入口” |
| 使用方式 | 如通读某节、重点理解某机制、跟做某例子 |
| 核验 | `已核验 YYYY-MM-DD`，或 `未验证：具体原因和未核验字段` |

优先级为官方文档、权威教材、官方/高校公开课、可核实的优质社区教程。优先中文；中文版本落后或不适用时，附英文原版、中文导读及原因。不要编造目录或将未核验页码补成看似准确的信息。

## 核验与调整

1. 使用可用的搜索/网页读取工具打开真实页面，检查内容与描述是否一致。
2. 对照官方发布页或出版社信息，确定目标版本是否适用。学习旧版本时按用户目标保留，并说明适用版本，不盲目替换为 latest。
3. 以实际目录核验章节标题、编号和阅读范围；受限资料标明哪些部分未验证。
4. 用户要求重新核验时，检查指定范围，报告失效、版本变化或正常的资料；在用户已授权的更新范围内修改相关 `track.md` 或单元补充说明，不改变状态。

资料过难时优先提供更浅显的权威入口，或给出有来源的简明解释；将替代资料写在当前 Track 的资料说明中。资料调整不会自动重建已完成单元，也不意味着新的能力已经掌握。
