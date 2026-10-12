# ArrayList

Session: `SE-4ca45b96cdd24bf0805525a75db2e4d3`
Goal / Track: `demo` / `core`
Sprint: `SP001`
开始：2026-10-11T14:49:54.664637+00:00；结束：2026-10-11T14:49:54.787239+00:00

本文件由 record.json 生成；机器状态以 JSON 为准。Session 完成不代表 Sprint 完成。

## 本次摘要

合成历史：已有集合基础，异常和复制成本不稳定

## 实际学习内容

未记录。

## 用户问题

未记录。

## 关键解释与结论

未记录。

## 练习与批改

### prior-task · 练习验证

合成学生先前作答

题目：解释 size、容量、扩容、边界异常和批量复制成本

用户答案：size 是元素数；容量是底层空间。扩容需要复制。get(size) 是空指针，批量复制只调一次所以常数时间。

结果：partial

批改：基本操作与扩容机制正确；索引越界及批量复制复杂度判断错误。

引用与摘录：

- synthetic-fixture/user/1
  > size 是元素数；容量是底层空间。扩容需要复制。get(size) 是空指针，批量复制只调一次所以常数时间。

### prior-correct-0 · 练习验证

合成学生先前作答

题目：解释 size、容量、扩容、边界异常和批量复制成本

用户答案：size 是元素数；容量是底层空间。几何扩容需要复制，单次 O(n)，追加均摊 O(1)。

结果：correct

批改：合成历史答案正确，作为验收输入

引用与摘录：

- synthetic-fixture/user/2
  > size 是元素数；容量是底层空间。几何扩容需要复制，单次 O(n)，追加均摊 O(1)。

### prior-correct-1 · 练习验证

合成学生先前作答

题目：解释 size、容量、扩容、边界异常和批量复制成本

用户答案：size 是元素数；容量是底层空间。几何扩容需要复制，单次 O(n)，追加均摊 O(1)。

结果：correct

批改：合成历史答案正确，作为验收输入

引用与摘录：

- synthetic-fixture/user/3
  > size 是元素数；容量是底层空间。几何扩容需要复制，单次 O(n)，追加均摊 O(1)。

## 暴露的薄弱点

### prior-gap · 练习验证

曾混淆索引越界与空指针，误判批量复制复杂度

关联事实：prior-task

引用与摘录：

- synthetic-fixture/user/1
  > size 是元素数；容量是底层空间。扩容需要复制。get(size) 是空指针，批量复制只调一次所以常数时间。

## 未解决的问题

未记录。

## 用户理解反馈

未记录。

## Sprint 验收证据

### prior-evidence-0 · 练习验证

解释 ArrayList 基本操作、size 和容量

验收标准：解释 ArrayList 基本操作、size 和容量

证据判断：met

关联事实：prior-correct-0

引用与摘录：

- synthetic-fixture/user/2
  > size 是元素数；容量是底层空间。几何扩容需要复制，单次 O(n)，追加均摊 O(1)。

### prior-evidence-1 · 练习验证

解释扩容和均摊复杂度

验收标准：解释扩容和均摊复杂度

证据判断：met

关联事实：prior-correct-1

引用与摘录：

- synthetic-fixture/user/3
  > size 是元素数；容量是底层空间。几何扩容需要复制，单次 O(n)，追加均摊 O(1)。

## 下一次交接

用实际案例聚焦异常与批量复制

重点事实：prior-gap

用户可以选择其他主题；完成 Sprint 需另行调用 transition。
