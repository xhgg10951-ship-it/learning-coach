# Phase 2A 实施约定

开发基线：`refactor/phase1-learning-structure`，提交 `10e6b0a`。实现分支：`feature/phase2a-session-persistence`。

实施前确定以下接口和兼容边界：

- 保留规划 schema v2、状态转换、历史及只读 `session-spec`；不迁移或重写旧文件。
- 每个 Track 的 `sessions/<SE-UUID>/record.json` 是该 Session 的唯一权威来源，增加独立 `session_version=1`。包含所属范围、可选 Sprint 的验收快照、实际主题、时间、状态、追加事实、检查点及交接摘要。
- `index.json` 是可重建的定位缓存，`note.md` 是完成记录的确定性 Markdown 投影。缓存失效时从权威记录恢复读取；缺失笔记可重建，冲突笔记保留并报错。
- 开始请求和检查点都有调用方稳定请求 ID；相同请求可安全重试，复用 ID 修改内容会报错。结束只提交一次，不修改任何规划状态。
- 批量检查点保存带引用的事实及精简交接。事实区分用户自报、AI 判断、练习验证、未验证；练习验证必须关联真实作答与结果。修订追加新事实并显式引用被替代事实，保留原文。
- `session-start` 开始，`session-checkpoint` 批量保存，`session-finish` 保存并生成笔记，`session-resume` 读取中断会话，`session-context` 获取局部交接，`session-list` 读取最近 N 次，`session-show` 分页取事实，`session-repair` 重建派生文件。
- 写接口显式限定 Goal/Track；context/list 可使用当前选择。恢复 active 会话与从 completed 会话新建严格区分。每个 Track 最多一份 active Session，其他 Track 独立保留。
- 新建与恢复学习遵守 Goal/Track 激活规则；已发生的事实允许在上层暂停后补存和结束，结束不等于能力验收。Sprint 关联仅作证据定位，不限制主题。
- 普通答疑或明确拒绝保存时不调用写接口。明确开始跟踪学习或结束保存就是授权，不重复确认；程序不生成学习事实或教学策略。

验证全部使用独立临时 Hub。第一阶段 75 项测试在允许访问临时目录的进程中通过（64.582 秒）；沙箱首次运行及工作区临时目录重试均因 Windows Python 临时目录 ACL 失败，不算功能基线失败。
