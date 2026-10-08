# 旧版格式参考（只读）

本目录原样保留第一阶段重构前的 goal、plan、syllabus 和 session 模板，用于辨识、查看已有学习文件与讨论人工迁移。里面的月份、ISO 周、复选框、旧状态和笔记字段都是历史格式，不是当前 Skill 的执行指令。

新建数据使用上一级模板与 `scripts/learning.py`。禁止用旧模板继续创建日历驱动计划，禁止依照旧标记自动顺延或把旧状态猜测成新的能力结论。

`scripts/progress.py` 可以只读汇总旧记录，明确标注 legacy。它不会修改用户的原文件，不将旧完成数量/学时当作掌握率。迁移方案见 [architecture.md](../../../docs/architecture.md#兼容与迁移)。
