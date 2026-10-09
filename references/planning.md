# 渐进规划与状态操作

## 当前层次与范围

Goal 是最终能力目标，Track 是独立学习领域，Milestone 是较大的能力阶段，Sprint 是当前中等颗粒度单元，Session 是一次自主学习及其真实记录。Milestone 约 20～40 小时、Sprint 约 3～8 小时仅作为拆分参考；不对应日历月份或周数。Session 保存和续学见 [session.md](session.md)，结束 Session 不自动推进任何规划状态。

先用 `current` 定位当前 Goal/Track。规划后续单元或调整已有单元前，必须用 `show --goal G --track T` 读取该 Track 的目标、验收标准、全部单元结果与决策历史；`current` 的当前位置摘要不能代替这一步。Agent 结合当前 Track 范围、已完成内容、跳过/结束记录、用户主动修改与尚缺能力规划下一步。不要把被跳过的内容当作已掌握，不要每次重新生成整份计划。

重要规划先展示目标、验收方式和大致工作量。用户已明确授权方案时直接执行；首次创建 Milestone 后，只创建其第一个 Sprint，不生成后续详细单元。

## 可运行的最小流程

在 Skill 根目录运行。下例从全新的 `./planning-demo` 开始；已有同名 ID 时命令会报错，不覆盖历史。

```shell
python scripts/learning.py --hub ./planning-demo init
python scripts/learning.py --hub ./planning-demo goal-create --id java-backend --title "Java 后端开发" --level "了解基本语法" --ability "独立开发基础 REST API"
python scripts/learning.py --hub ./planning-demo track-create --goal java-backend --id spring-boot --title "Spring Boot"
python scripts/learning.py --hub ./planning-demo select --goal java-backend --track spring-boot
python scripts/learning.py --hub ./planning-demo milestone-create --goal java-backend --track spring-boot --id M001 --title "基础 REST API" --objective "独立开发并运行基础 REST API，解释请求处理流程" --criterion "从空项目启动并提供 JSON 接口" --criterion "解释请求从路由到响应的处理路径" --hours 30
python scripts/learning.py --hub ./planning-demo sprint-create --goal java-backend --track spring-boot --milestone M001 --id SP001 --title "启动与请求链路" --objective "理解项目结构、启动方式和基本请求处理" --criterion "独立启动项目，并解释入口、控制器与路由的作用" --hours 5
python scripts/learning.py --hub ./planning-demo current
python scripts/learning.py --hub ./planning-demo show --goal java-backend --track spring-boot
```

创建操作默认 `active`，也可按用户明确选择用 `--status pending` 保存待开始单元。省略 Milestone/Sprint 的 `--id` 时，在当前 Track 中分别按 `M001`、`SP001` 递增；跨 Milestone 不重置 Sprint 编号。标题可修改，ID 保持稳定。

## 完成当前 Sprint，再按需规划下一个

用户确认达成验收要求时记录具体结果，可以是用户自报，不要求上传证据。下面的结果文字只是命令示例，实际操作必须替换为真实情况。

```shell
python scripts/learning.py --hub ./planning-demo transition --goal java-backend --track spring-boot --kind sprint --id SP001 --status completed --note "用户自报：已独立启动项目，能解释入口、控制器和路由如何处理请求"
python scripts/learning.py --hub ./planning-demo sprint-create --goal java-backend --track spring-boot --milestone M001 --id SP002 --title "实现 JSON 接口" --objective "独立实现并验证基础 JSON 接口" --criterion "从项目创建到接口返回 JSON 可以独立完成，并解释请求到响应的路径" --hours 5
python scripts/learning.py --hub ./planning-demo transition --goal java-backend --track spring-boot --kind sprint --id SP002 --status completed --note "用户自报：已独立创建项目并验证 JSON 返回，能完整解释请求处理路径"
```

这几次操作可发生在同一天；即使一个月没有学习，状态也不会按日期改变。创建 SP002 不会自动补齐以后所有 Sprint。`completed` 是针对该单元验收标准的记录，不是全领域掌握率。

评估 Milestone 自身的能力要求后，再独立完成该阶段；所有子 Sprint 结束只是必要条件，不是充分的能力证明。

```shell
python scripts/learning.py --hub ./planning-demo transition --goal java-backend --track spring-boot --kind milestone --id M001 --status completed --note "用户自报：从空项目完成可运行 JSON 接口，并完整说明了请求处理流程，符合两项阶段标准"
```

完成后仅建议下一阶段方向，用户授权具体规划后才执行新的 `milestone-create` 和一个 `sprint-create`。不要自动完成 Track 或 Goal。

## 切换、暂停与恢复

`select` 保存 Goal/Track 当前位置，不改生命周期；原 Sprint 未结束也能自由切换。返回后读取原状态和历史继续推进。

```shell
python scripts/learning.py --hub ./planning-demo goal-create --id english --title "英语口语"
python scripts/learning.py --hub ./planning-demo track-create --goal english --id speaking --title "工作交流"
python scripts/learning.py --hub ./planning-demo select --goal english --track speaking
python scripts/learning.py --hub ./planning-demo select --goal java-backend --track spring-boot
python scripts/learning.py --hub ./planning-demo transition --goal java-backend --track spring-boot --kind track --status paused --note "用户希望暂缓这个领域"
python scripts/learning.py --hub ./planning-demo transition --goal java-backend --track spring-boot --kind track --status active --note "用户决定恢复这个领域"
```

Goal/Track 暂停是上层挂起，下属原状态保持不变；挂起期间不能新建、激活或完成下属单元。恢复上层不会丢失记录。Milestone 暂停则会暂停其当前 active Sprint；恢复 Milestone 后，需显式恢复所选 Sprint。

## 修改、跳过、提前结束与切换单元

- 只改变当前目标描述或验收要求：用 `update`，保留 ID，并在 `--note` 说明变更。多个 `--criterion` 表示更新后的完整标准列表。
- 不再学习某单元：用 `transition --status skipped`；提前收束但尚未达到完成标准：用 `--status ended`。必须写明原因，不能代记为 `completed`。
- 希望保留未结束内容、转到新的能力单元：创建时必须加 `--adjustment "用户要求和理由"`。程序暂停原 active 单元，新建所选单元并保留历史。不得为了绕过约束编造调整理由。

以新建但尚未完成的单元为例（下面使用独立数据目录，可直接运行）：

```shell
python scripts/learning.py --hub ./adjustment-demo init
python scripts/learning.py --hub ./adjustment-demo goal-create --id python --title "Python 数据分析"
python scripts/learning.py --hub ./adjustment-demo track-create --goal python --id basics --title "Python 基础"
python scripts/learning.py --hub ./adjustment-demo milestone-create --goal python --track basics --title "处理小型数据文件" --objective "能够清洗并汇总简单数据" --criterion "独立读入文件并输出汇总结果"
python scripts/learning.py --hub ./adjustment-demo sprint-create --goal python --track basics --milestone M001 --title "读取文件" --objective "读取文本文件并处理空行" --criterion "解释读取逻辑并处理空行"
python scripts/learning.py --hub ./adjustment-demo update --goal python --track basics --kind sprint --id SP001 --objective "读取 UTF-8 文本并处理空行" --criterion "读入 UTF-8 文本并过滤空行，说明处理方法" --note "用户明确了文件编码与范围"
python scripts/learning.py --hub ./adjustment-demo sprint-create --goal python --track basics --milestone M001 --title "先学习容器" --objective "理解列表与字典的基本操作" --criterion "按给定结构创建、读取和更新列表与字典" --adjustment "用户要求先补列表与字典，保留读取文件单元待恢复"
python scripts/learning.py --hub ./adjustment-demo transition --goal python --track basics --kind sprint --id SP002 --status skipped --note "用户选择跳过；未进行能力验收"
python scripts/learning.py --hub ./adjustment-demo transition --goal python --track basics --kind milestone --id M001 --status ended --note "用户决定提前结束此阶段，仍有能力要求未验收"
```

Milestone 跳过或提前结束时，其所有非终态 Sprint 一并记为相同状态；已完成、已跳过、已结束历史保持原样。终态单元不能直接重开，需要新的调整单元并在理由中关联旧单元。

## 不变量与失败处理

- 同一 Track 最多一个 active Milestone；同一 Milestone 最多一个 active Sprint。已有未结束单元时，普通 create 被拒绝；仅用户明确调整可例外。
- 完成必须从 `active` 出发，且有实际验收说明。Milestone 有非终态 Sprint 时不能完成；Track 完成要求所有 Milestone 终态；Goal 完成要求所有 Track 已完成。各层仍需要各自的能力说明。
- 前置依赖是建议，允许不按固定领域顺序学习；上层暂停与有效状态约束仍由程序执行。
- 命令报错时不宣称成功，不用 Markdown 替代写入。读取错误信息，必要时运行 `validate`；保留原始文件，修复方案明确后再操作。
