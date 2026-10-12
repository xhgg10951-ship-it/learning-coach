# ArrayList 异常边界与批量复制综合实践

Session: `SE-23ef722ad0824f938983ff5a1d2ff6f8`
Goal / Track: `demo` / `core`
Sprint: `SP001`
开始：2026-10-11T14:50:55.286834+00:00；结束：2026-10-12T00:06:59.437857+00:00

本文件由 record.json 生成；机器状态以 JSON 为准。Session 完成不代表 Sprint 完成。

## 本次摘要

本次学习已按用户指令结束。基本操作/size容量、异常区分、批量复制和容量足够时插入复杂度有实际正确作答；扩容均摊此前正确判断保留，但最新仍不理解平均受固定上限约束，原理卡点未确认解决，AI解释不是新增掌握证据。完整综合案例的独立实现与实际运行仍未验证，AI Demo未实际运行且不算用户证据。用户今天不改错、不继续练习；运行验证以后补。Session结束不代表SP001完成。

## 实际学习内容

### user-start-01 · 用户自报

用户要求继续 ArrayList，记录到当前 Sprint；自报会基本操作和扩容，指定从实际案例开始，要求覆盖异常边界和批量复制的综合任务。

引用与摘录：

- conversation/user/1
  > 继续学习 ArrayList，记录到当前 Sprint。我已经会基本操作和扩容。今天从实际案例开始，先给我一个覆盖异常边界和批量复制的综合任务。

### save-group-03 · 用户自报

用户结束本组并要求保存，按检查点保存，Session继续active。

引用与摘录：

- conversation/user/3
  > 这组到这里，请保存本组结果并说明还有哪些能力没验证。

### wording-05 · 用户自报

用户明确size指有效元素数量，而非底层容量；空列表容量100仍size=0。接受其明确含义，只纠正措辞，不认定概念缺口或撤回已验证证据。

引用与摘录：

- conversation/user/5
  > 我刚才把 size 口头说成数组长度，我指的是有效元素数量，不是底层数组的容量；容量 100 的空列表 size 还是 0。这个只是措辞问题。讲快一点，先不讲原理，直接给一个订单列表 Demo。

### summary-request-08 · 用户自报

用户要求仅总结当前Sprint逐项验收证据，未独立验证如实标记，今天不练习，暂不结束Session。

引用与摘录：

- conversation/user/8
  > 今天不做练习了，只总结当前 Sprint 每项验收标准的证据状态；没独立验证的请如实标记。先别结束。

### criteria-summary-08 · AI 判断

当前 Sprint **SP001** 的证据状态如下。今天不出题，也不结束 Session。

| 验收标准 | 证据状态 | 已有依据与边界 |
|---|---|---|
| 解释 ArrayList 基本操作、size 和容量 | 已有独立作答验证 | 你正确判断 size=2、容量至少10，并迁移到“预留100但未添加时 size=0”的订单例子；措辞澄清不撤销正确证据。 |
| 解释扩容和均摊复杂度 | 已有正确作答；当前原理理解仍需巩固 | 你曾正确区分单次扩容复制与多次追加的均摊成本。但最近明确说仍不理解“每次成本不同，为什么均摊成常数”。此前正确判断保留；独立推导固定上限尚未验证，AI 的逐步讲解不能证明卡点已解决。 |
| 区分索引越界与空指针异常 | 已有独立作答验证 | 你已正确修正：get(2) 在索引检查时越界；get(1) 得到 null，调用 length() 才空指针。依据是实际回答，尚无运行输出。 |
| 分析批量复制和插入复杂度 | 已有独立分析验证 | 你正确说明复制 m 项是 O(m)，容量足够时移动尾部 k 项并插入批次为 O(m+k)，最坏 O(m+n)。重叠复制的具体结果、逐个头插的成本比较尚未提交。 |
| 独立实现并运行综合案例 | **未验证** | 目前没有完整实现和实际运行输出；AI Demo 及其预期输出不算你的独立实现或运行证据。 |

所以，现有证据支持部分概念判断与复杂度分析；还不能声称已独立完成整个综合案例，也不能把均摊原理的卡点标成已解决。



关联事实：transfer-answer-04, answer-03, understanding-guided-07, amortized-gap-07

引用与摘录：

- conversation/assistant/8
  > 此前正确判断保留；独立推导固定上限尚未验证，AI 的逐步讲解不能证明卡点已解决。

### finish-request-09 · 用户自报

用户明确结束并保存本次学习，运行验证以后补，现在不改错、不继续做题。

引用与摘录：

- conversation/user/9
  > 今天到这里，结束并保存。没做运行验证的部分以后补，我现在不改错也不继续做题。

## 用户问题

### question-deep-06 · 用户自报

用户要求深入解释单次扩容和均摊追加成本，并用具体扩容序列理解原理。

引用与摘录：

- conversation/user/6
  > 现在深入讲一下为什么追加均摊 O(1)，单次扩容却可能 O(n)，用一个具体扩容序列解释。我希望理解背后的原理。

### question-guided-07 · 用户自报

用户仍不理解各次成本不同为什么能均摊为常数，要求逐步详细解释并暂时不出题。

引用与摘录：

- conversation/user/7
  > 我还是不理解为什么每次成本不同却能平均成常数。详细一点，逐步带我看这个卡点，暂时不用给我题。

## 关键解释与结论

### explain-02 · AI 判断

get只能访问0至size-1。get(2)先索引检查失败抛IndexOutOfBoundsException；get(1)返回null，随后length触发NullPointerException。一般成功复制m项需要随m增长的读写，按元素模型为O(m)，底层优化只降低常数。

关联事实：answer-02

引用与摘录：

- conversation/assistant/2
  > 容量像预留的座位，size 才是当前名单长度：名单只有两项，不能通过 get(2) 读取第三项。搬运 m 箱货物即使只下达一次指令，仍需搬 m 箱；一般成功复制 m 项按元素模型是 O(m)，底层优化只降低常数。

### scope-explanation-04 · AI 判断

通常常数和均摊O(1)指单项尾部add，批量addAll的成本随m增长；容量足够O(m)，扩容时一般O(n+m)。措辞限定不撤回正确概念证据。

引用与摘录：

- conversation/assistant/4
  > 只需限定一句：“通常常数成本、均摊 O(1)”指单项尾部 add。一次 addAll 追加 m 项，在容量足够时是 O(m)；需要扩容时一般是 O(n+m)。

### demo-05 · AI 判断

AI订单编号列表Demo：预留100容量、打印空列表size、捕获get(0)越界、单项追加与批量追加、复制列表快照、移除取消订单并打印。示例代码未执行，不能作为用户独立实现运行证据。
import java.util.*;

public class OrderListDemo {
    public static void main(String[] args) {
        ArrayList<String> orders = new ArrayList<>(100);
        System.out.println("初始 size=" + orders.size());

        try {
            orders.get(0);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("空列表访问：" + e.getClass().getSimpleName());
        }

        orders.add("A");
        orders.add("B");
        orders.addAll(Arrays.asList("C", "D"));

        ArrayList<String> snapshot = new ArrayList<>(orders);
        orders.remove("B"); // 取消订单 B

        System.out.println("当前订单：" + orders);
        System.out.println("当前 size=" + orders.size());
        System.out.println("取消前快照：" + snapshot);
    }
}

引用与摘录：

- conversation/assistant/5
  > 下面用订单编号演示完整小流程：预留容量 → 添加订单 → 批量追加 → 保存快照 → 取消订单。

### amortized-explanation-06 · AI 判断

单次扩容 O(n) 和追加均摊 O(1) 看的是不同范围：前者看某一次追加，后者看连续多次追加的总成本。把一次昂贵的搬家分摊到整段居住时间，就能理解为什么两者并不矛盾。

先用简化的动态数组模型算账：初始容量 1，满了就翻倍。这里的 1→2→4→8→16 是教学模型，不是 ArrayList 的精确增长序列；它说明固定比例扩容的原理。

| 追加第几项 | 追加后的容量 | 本次复制旧元素数 | 写入新元素数 |
|---|---:|---:|---:|
| 1 | 1 | 0 | 1 |
| 2 | 2 | 1 | 1 |
| 3 | 4 | 2 | 1 |
| 4 | 4 | 0 | 1 |
| 5 | 8 | 4 | 1 |
| 6～8 | 8 | 每次 0 | 每次 1 |
| 9 | 16 | 8 | 1 |
| 10 | 16 | 0 | 1 |

第 9 次追加要复制 8 个旧元素，再写 1 个新元素，所以这一回很贵。一般而言，当前有 n 个元素且需要扩容时，要搬运随 n 增长的旧数据，单次成本可能是 O(n)。

但前 10 次追加一起算：

- 写入新元素：10 次。
- 复制旧元素：1+2+4+8=15 次。
- 合计：25 个单位，分摊到每次是 2.5 个单位。

25÷10 只是具体示例。真正的证明要看追加数量变大以后，总成本是否仍与数量成正比。

连续追加 N 项时，翻倍扩容的复制量形成几何级数：

```text
1 + 2 + 4 + … + 2^k = 2^(k+1) - 1
```

最后一次复制的数量 2^k 小于 N，所以全部复制量小于 2N；再加上 N 次新元素写入，总量小于 3N。因此：

```text
连续 N 次单项尾部追加：总成本 O(N)
每次单项尾部追加：均摊成本 O(N)/N = O(1)
```

这里聚焦元素引用复制与写入。新数组分配、初始化的成本也随容量增长；各次容量同样形成几何级数，不改变这个结论。

为什么增长比例关键？如果每次只多开一个位置，复制量会变成 1+2+…+(N-1)，总成本 O(N²)，均摊就成了 O(N)。固定比例大于 1 的几何扩容，把总复制量控制在 N 的固定倍数以内。

“均摊”不要求随机输入，也不保证每次都快：即使扩容的那次很慢，整段追加的总成本仍受 O(N) 约束。这也不把一次追加 m 项的 addAll 变成 O(1)，批次仍有 O(m) 的写入工作。

引用与摘录：

- conversation/assistant/6
  > 单次扩容 O(n) 和追加均摊 O(1) 看的是不同范围：前者看某一次追加，后者看连续多次追加的总成本。把一次昂贵的搬家分摊到整段居住时间，就能理解为什么两者并不矛盾。

### amortized-guided-07 · AI 判断

可以，我们放慢，只看这个卡点，暂时不出题。

**“均摊 O(1)”允许每次成本不同，也允许平均值变化；关键是：追加次数越来越多时，平均成本仍不超过某个固定上限。**

像一次花费很高、其他几次花费很低，把整段账单加起来再除以次数，平均值就可能很低。但光有“多数便宜、少数昂贵”还不够，我们要看贵的程度与出现间隔是否匹配。

**第一步：把“成本”换成可数的动作。**

继续用初始容量 1、满了就翻倍的教学模型。它用于理解原理，不代表 ArrayList 的精确容量序列。

暂时规定：复制一个旧元素算 1 单位，写入一个新元素也算 1 单位。这里只算元素操作，不算实际毫秒。

前 8 次尾部追加的账是：

| 第几次追加 | 复制旧元素 | 写入新元素 | 本次成本 |
|---|---:|---:|---:|
| 1 | 0 | 1 | 1 |
| 2 | 1 | 1 | 2 |
| 3 | 2 | 1 | 3 |
| 4 | 0 | 1 | 1 |
| 5 | 4 | 1 | 5 |
| 6 | 0 | 1 | 1 |
| 7 | 0 | 1 | 1 |
| 8 | 0 | 1 | 1 |

成本确实不同：1、2、3、1、5、1、1、1。

但一起算，总成本是 15，平均是 15÷8＝1.875。求平均本来就不要求每项相同。

**第二步：看下一次很贵时，平均会怎样。**

第 9 次追加触发扩容，要复制 8 项再写入 1 项，本次成本是 9。

前 9 次总成本变成 15＋9＝24，平均是 24÷9≈2.67。

之后第 10～16 次都有空位，每次只花 1 单位。因此前 16 次总成本是 24＋7＝31，平均是 31÷16≈1.94。

你能看到：**扩容时平均值上升，接着几次便宜追加又把平均值拉低。平均值会波动。**

**第三步：为什么下一次扩容更贵，却不会把平均值越推越高？**

从容量 8 扩到 16，要复制 8 项，却同时多出了 8 个位置。

这 8 个位置容纳第 9～16 次追加。把这整组算在一起：

- 扩容复制：8 单位。
- 8 次新元素写入：8 单位。
- 合计 16 单位，分给 8 次追加，每次 2 单位。

下一组，从容量 16 扩到 32：

- 扩容复制：16 单位。
- 16 次新元素写入：16 单位。
- 合计 32 单位，分给 16 次追加，每次还是 2 单位。

**搬家成本翻倍了，能分担这次搬家成本的追加次数也翻倍了。** 这就是固定比例扩容能保持均摊常数成本的原因。

不过，上面按完整一组算。假如刚扩容就停止，后面的便宜追加还没发生，所以我们还要检查这种情况。

**第四步：即使刚扩容就停，总账也有固定上限。**

例如停在第 17 次：刚复制了 16 项，是平均成本突然上升的位置。

截至此时，全部旧元素复制次数是：

```text
1 + 2 + 4 + 8 + 16 = 31
```

再加 17 次新元素写入，总成本是 48，平均 48÷17≈2.82，仍小于 3。

推广到任意 N 次追加：假设最后一次扩容复制了 L 项。之前各次复制量依次是 L/2、L/4……，所以：

```text
全部复制量 = 1 + 2 + 4 + … + L = 2L - 1
```

能触发这次扩容，说明已经追加了至少 L＋1 项，因此 L＜N。于是：

```text
全部复制量 < 2N
新元素写入量 = N
总成本 < 3N
平均成本 = 总成本 ÷ N < 3
```

无论 N 是 17、一千还是一百万，**在这个计账模型里，平均成本都小于 3**。这才是均摊 O(1) 的依据。把数组分配和初始化等线性成本也计入，会改变固定上限的数值，但仍保持总成本 O(N)。

所以，你可以把两个结论并排放着：

- **看某一次：**扩容那次可能复制很多旧元素，单次成本 O(n)。
- **看从空列表开始的连续 N 次尾部追加：**总成本 O(N)，除以 N，均摊成本 O(1)。



引用与摘录：

- conversation/assistant/7
  > 均摊 O(1)允许每次成本不同，也允许平均值变化；关键是追加次数越来越多时，平均成本仍不超过某个固定上限。

## 练习与批改

### order-queue-task-01 · 尚未验证

布置订单队列综合任务，尚无用户作答。

题目：任务：订单队列的批量插单与异常排查。先预测，再写一个 Java main 实际运行；贴出代码、输出和成本分析。初始 ArrayList<String> 为 [A, null, C]。1. 独立运行 get(size)、get(1)、get(1).length()、add(size, Z)、add(size+1, Z)、addAll(1, null)，记录结果或异常类及原因；每项重建初始列表。2. 向索引1批量插入 [X,Y]，打印内容和size；用 new ArrayList<>(queue) 创建副本，对副本 set(0,B)，检查原列表是否变化并解释复制了什么。3. 独立用 System.arraycopy 将 [A,B,C,D,E] 中从索引1开始的3项复制到同数组索引2，预测并核对输出。4. n=10000,m=2000,i=2，ArrayList.addAll(i,batch)，batch为独立ArrayList，容量足够，分析获取批次、移动尾部、写入批次的引用复制量和复杂度；说明扩容时多出的复制工作，并与逐个在索引0插入m项比较。

用户答案：未作答

结果：not_assessed

批改：任务刚布置，异常判断、复制成本及独立实现运行均待用户作答；保留已有基础验证。

验证形式：Java 实现、异常定位与复制复杂度分析；错误类型：unassessed

- 区分索引越界与空指针异常：unverified；尚未收到边界探针的预测或实际输出

- 分析批量复制和插入复杂度：unverified；尚未收到复制次数和复杂度分析

- 独立实现并运行综合案例：unverified；尚未收到用户代码与运行结果

引用与摘录：

- conversation/assistant/1
  > 任务：订单队列的批量插单与异常排查。先预测，再写一个 Java main 实际运行；贴出代码、输出和成本分析。

### answer-02 · 练习验证

用户以自己的代码提交局部作答：size/容量与合法位置null解引用判断正确，越界异常和复制复杂度判断错误。

题目：按用户自选代码批改 size、容量、get(2)、get(1).length() 和 System.arraycopy 复制 m 项的复杂度。

用户答案：我用自己的代码作答，你按这个批改：var xs = new ArrayList<String>(10); xs.add("a"); xs.add(null);。size 是 2，容量至少 10。xs.get(2) 会抛 NullPointerException；xs.get(1).length() 也会抛 NullPointerException。我觉得 System.arraycopy 复制 m 个元素是 O(1)，因为只调用一次方法。

结果：partial

批改：size=2与容量至少10正确；get(2)应为IndexOutOfBoundsException，不能访问容量中的未使用槽位；get(1).length()为NullPointerException正确；一般成功复制m项按元素模型为O(m)，一次调用不代表常数工作量。未提供运行结果或完整批量插入分析。

关联事实：order-queue-task-01

验证形式：用户代码阅读、异常预测与复杂度分析；未提供实际运行输出；错误类型：conceptual

- 解释 ArrayList 基本操作、size 和容量：met；实际作答正确判断size为2、容量至少10，null元素也计入size

- 区分索引越界与空指针异常：partial；合法索引1的null解引用判断正确，但把索引2越界误判为空指针

- 分析批量复制和插入复杂度：not_met；把一次arraycopy调用等同于O(1)，复制m项的成本判断错误；插入成本未作答

- 独立实现并运行综合案例：unverified；仅提交代码片段和预测，尚无完整案例或实际运行输出

引用与摘录：

- conversation/user/2
  > 我用自己的代码作答，你按这个批改：var xs = new ArrayList<String>(10); xs.add("a"); xs.add(null);。size 是 2，容量至少 10。xs.get(2) 会抛 NullPointerException；xs.get(1).length() 也会抛 NullPointerException。我觉得 System.arraycopy 复制 m 个元素是 O(1)，因为只调用一次方法。

### answer-03 · 练习验证

用户本轮正确修正异常区分与复制成本，并说明中间批量插入需移动尾部。

题目：针对原任务和第二轮反馈，修正异常判断与批量复制、插入复杂度；原题容量足够，k表示需移动的尾部元素数。

用户答案：修正：get(2) 的索引等于 size，先越界，应为 IndexOutOfBoundsException；get(1) 本身得到 null，调用 length() 才空指针。复制 m 个元素要 O(m)；向中间插入这 m 个元素还需移动尾部 k 个元素，所以 O(m+k)，最坏 O(m+n)。这组到这里，请保存本组结果并说明还有哪些能力没验证。

结果：correct

批改：get(2)等于size先越界、get(1)得到null再解引用空指针正确；复制m项O(m)，容量足够时移动k项加批次写入为O(m+k)，最坏O(m+n)，表达与原题假设一致。仅验证代码阅读与复杂度分析，不虚称实际运行或完整任务均已完成。

关联事实：order-queue-task-01

验证形式：用户纠错作答：异常原因解释与符号化复杂度分析；错误类型：none

- 区分索引越界与空指针异常：met；正确区分get阶段索引检查失败与返回null后的length解引用

- 分析批量复制和插入复杂度：met；正确给出O(m)复制与O(m+k)中间批量插入及O(m+n)最坏界，符合原题容量足够假设

- 独立实现并运行综合案例：unverified；没有提交完整实现或实际运行输出，正确解释不替代运行证据

引用与摘录：

- conversation/user/3
  > 修正：get(2) 的索引等于 size，先越界，应为 IndexOutOfBoundsException；get(1) 本身得到 null，调用 length() 才空指针。复制 m 个元素要 O(m)；向中间插入这 m 个元素还需移动尾部 k 个元素，所以 O(m+k)，最坏 O(m+n)。这组到这里，请保存本组结果并说明还有哪些能力没验证。

### transfer-answer-04 · 练习验证

用户将size/容量、边界异常、批量复制与均摊复杂度迁移到订单例子，核心判断正确；追加常数成本的说法限定为单项尾部追加。

题目：评价用户订单场景下预留容量、空列表访问、addAll批量成本、单项追加扩容和均摊复杂度判断。

用户答案：换个实际例子：订单列表预留容量 100 但还没添加订单时 size=0；get(0) 仍然越界。追加一批 m 条订单用 addAll，不能把一次调用说成 O(1)。每次追加通常常数成本，扩容那次要复制旧元素；多次追加按几何扩容累计摊销才是 O(1)。请评价我的这些判断，后面用更综合的案例。

结果：correct

批改：预留100不增加size，空列表get(0)索引越界；addAll(m)不能因一次调用认定O(1)。单项尾部追加通常O(1)、扩容需复制、多次几何扩容按追加元素数摊销O(1)判断正确。仅需限定每次追加是单项：m项批量追加容量足够O(m)，需扩容时一般O(n+m)。属表达范围澄清，不判为概念错误；无实现运行证据。

验证形式：用户自选业务例子的概念迁移与复杂度解释；错误类型：wording

- 解释 ArrayList 基本操作、size 和容量：met；正确说明预留100但未添加时size=0

- 解释扩容和均摊复杂度：met；正确区分扩容单次复制与多次单项尾部追加几何扩容的摊销成本

- 区分索引越界与空指针异常：met；本轮正确判断空列表get(0)越界，与上一轮已正确区分null解引用结合保留验证

- 分析批量复制和插入复杂度：met；正确拒绝一次addAll调用等于常数成本，结合上一轮O(m+k)正确分析保持已验证

- 独立实现并运行综合案例：unverified；本轮仅为判断和解释，未提交完整代码与运行输出

引用与摘录：

- conversation/user/4
  > 换个实际例子：订单列表预留容量 100 但还没添加订单时 size=0；get(0) 仍然越界。追加一批 m 条订单用 addAll，不能把一次调用说成 O(1)。每次追加通常常数成本，扩容那次要复制旧元素；多次追加按几何扩容累计摊销才是 O(1)。请评价我的这些判断，后面用更综合的案例。

### advanced-task-04 · 尚未验证

按用户要求提高为批量导入、失败边界、可变对象快照和筛选的综合实现；尚未作答。

题目：后续综合案例：订单批量导入与审计快照。自定义可变Order(id,status)。原列表预留100，实际含A待处理、B已取消、C待处理；独立批次D/E待处理。实现importAt(ArrayList<Order>,int,List<Order>)，一次批量插入索引1；业务禁止null集合和null订单，非法索引拒绝，失败不得留下部分导入。保存导入后快照，随后将原A改为已取消并删除所有已取消订单，要求快照的成员和状态仍保持导入时内容。运行正常导入、空批次、null批次、含null批次、索引size和size+1，打印操作前后状态与异常类；解释副本与对象引用隔离，以及导入和筛选成本。提交完整代码、实际输出和成本分析，尚未作答。

用户答案：未作答

结果：not_assessed

批改：尚未收到新案例代码或运行结果，不把任务布置或AI说明视为独立实现能力。

验证形式：Java业务流程实现、失败边界验证、快照隔离与复杂度分析；错误类型：unassessed

- 独立实现并运行综合案例：unverified；任务尚未作答，仍缺独立实现和实际运行证据

引用与摘录：

- conversation/assistant/4
  > 后续综合案例：订单批量导入与审计快照。

## 暴露的薄弱点

### gaps-02 · 练习验证

实际答案仍混淆size之外的索引访问与合法null元素的解引用；用方法调用次数判断批量复制成本。

关联事实：answer-02

引用与摘录：

- conversation/user/2
  > 我用自己的代码作答，你按这个批改：var xs = new ArrayList<String>(10); xs.add("a"); xs.add(null);。size 是 2，容量至少 10。xs.get(2) 会抛 NullPointerException；xs.get(1).length() 也会抛 NullPointerException。我觉得 System.arraycopy 复制 m 个元素是 O(1)，因为只调用一次方法。

## 未解决的问题

### remaining-03 · 尚未验证

尚未验证独立实现并运行完整综合案例。原任务中的add/addAll边界实际输出、副本修改与复制语义、重叠arraycopy结果、精确复制量与逐个头插成本比较尚未提交。

关联事实：answer-03

引用与摘录：

- conversation/assistant/3
  > 尚未验证的是独立实现并运行综合案例：目前没有完整代码和运行输出。原任务里的 add/addAll 边界、副本修改、重叠复制结果及逐个头插的成本比较，也尚未提交，不能声称全部做完。

### amortized-gap-07 · 尚未验证

平均成本为何能被固定上限约束，用户本轮仍反馈不理解；逐步解释后尚无用户反馈或独立验证。

关联事实：understanding-guided-07

引用与摘录：

- conversation/user/7
  > 我还是不理解为什么每次成本不同却能平均成常数。详细一点，逐步带我看这个卡点，暂时不用给我题。

## 用户理解反馈

### understanding-guided-07 · 用户自报

用户明确反馈仍不理解均摊常数成本的依据；保留此前正确作答，不能因本轮讲解认定卡点已解决。

用户反馈：not_understood

引用与摘录：

- conversation/user/7
  > 我还是不理解为什么每次成本不同却能平均成常数。详细一点，逐步带我看这个卡点，暂时不用给我题。

## Sprint 验收证据

### basic-evidence-02 · 练习验证

本轮正确区分当前元素数与容量，保留基本操作能力验证。

验收标准：解释 ArrayList 基本操作、size 和容量

证据判断：met

关联事实：answer-02

引用与摘录：

- conversation/user/2
  > 我用自己的代码作答，你按这个批改：var xs = new ArrayList<String>(10); xs.add("a"); xs.add(null);。size 是 2，容量至少 10。xs.get(2) 会抛 NullPointerException；xs.get(1).length() 也会抛 NullPointerException。我觉得 System.arraycopy 复制 m 个元素是 O(1)，因为只调用一次方法。

### boundary-evidence-03 · 练习验证

本轮正确作答验证索引越界与空指针异常区分。

验收标准：区分索引越界与空指针异常

证据判断：met

关联事实：answer-03

引用与摘录：

- conversation/user/3
  > 修正：get(2) 的索引等于 size，先越界，应为 IndexOutOfBoundsException；get(1) 本身得到 null，调用 length() 才空指针。复制 m 个元素要 O(m)；向中间插入这 m 个元素还需移动尾部 k 个元素，所以 O(m+k)，最坏 O(m+n)。这组到这里，请保存本组结果并说明还有哪些能力没验证。

### copy-evidence-03 · 练习验证

本轮正确作答验证批量复制和中间插入复杂度分析，范围为原题容量足够条件。

验收标准：分析批量复制和插入复杂度

证据判断：met

关联事实：answer-03

引用与摘录：

- conversation/user/3
  > 修正：get(2) 的索引等于 size，先越界，应为 IndexOutOfBoundsException；get(1) 本身得到 null，调用 length() 才空指针。复制 m 个元素要 O(m)；向中间插入这 m 个元素还需移动尾部 k 个元素，所以 O(m+k)，最坏 O(m+n)。这组到这里，请保存本组结果并说明还有哪些能力没验证。

## 教学调整与依据

### practice-mode-01 · 用户自报

按本轮综合实践要求使用 Practice，从订单队列案例开始。

mode：practice
pace：balanced
depth：standard
exercise_policy：allowed
difficulty：已有基本操作与扩容证据，综合任务聚焦异常边界、批量复制和实际运行
reason：用户明确要求实际综合任务；教学上下文中基本操作和扩容已验证，省略基础重复；本轮新任务尚未作答。

引用与摘录：

- conversation/user/1
  > 今天从实际案例开始，先给我一个覆盖异常边界和批量复制的综合任务。

### guided-02 · AI 判断

只针对两处真实概念缺口补解释，保留已验证基础，不重做整组。

关联事实：answer-02

mode：guided
pace：balanced
depth：standard
exercise_policy：allowed
difficulty：局部边界与复制成本纠错，不重复已有基本操作和扩容
reason：实际答案正确部分保留；仅针对越界异常和把单次调用误当常数成本的两处错误提供针对性解释。

引用与摘录：

- conversation/user/2
  > 我用自己的代码作答，你按这个批改：var xs = new ArrayList<String>(10); xs.add("a"); xs.add(null);。size 是 2，容量至少 10。xs.get(2) 会抛 NullPointerException；xs.get(1).length() 也会抛 NullPointerException。我觉得 System.arraycopy 复制 m 个元素是 O(1)，因为只调用一次方法。

### practice-advanced-04 · 用户自报

用户要求更综合案例，恢复Practice并提高到完整业务流程；省略已验证基础。

mode：practice
pace：balanced
depth：standard
exercise_policy：allowed
difficulty：已有基础和概念分析证据，转向订单导入、快照隔离及筛选的完整实现
reason：遵循用户要求更综合的案例；新场景核心判断正确，措辞作简短范围澄清，重点转向尚缺的独立实现与运行。

引用与摘录：

- conversation/user/4
  > 请评价我的这些判断，后面用更综合的案例。

### quick-05 · 用户自报

本轮即时改为Quick、fast、overview，直接展示订单编号Demo，省略原理与重复练习。

mode：quick
pace：fast
depth：overview
exercise_policy：allowed
difficulty：已有基础，直接展示订单列表操作流程，不从零讲解
reason：用户明确要求讲快、暂不讲原理、直接Demo；未拒绝练习，保留allowed，但本轮不额外出题。用户已明确size含义，只修正措辞。

引用与摘录：

- conversation/user/5
  > 讲快一点，先不讲原理，直接给一个订单列表 Demo。

### deep-06 · 用户自报

按本轮指令从Quick切换Deep，保留此前fast节奏，深入讲原理，不额外出题。

mode：deep
pace：fast
depth：deep
exercise_policy：allowed
difficulty：已有正确概念判断，用几何级数推导单项尾部追加均摊成本
reason：用户本轮明确要求深入原理，覆盖之前先不讲原理的临时偏好；未要求放慢或拒绝练习，保留fast和allowed，本轮直接解释。

引用与摘录：

- conversation/user/6
  > 现在深入讲一下为什么追加均摊 O(1)，单次扩容却可能 O(n)，用一个具体扩容序列解释。我希望理解背后的原理。

### guided-07 · 用户自报

按本轮指令切换Guided，放慢节奏，逐步看总账与固定上限，暂停练习。

mode：guided
pace：slow
depth：deep
exercise_policy：declined
difficulty：已有正确概念表述，只拆解每次成本不同与均摊固定上限之间的卡点
reason：用户说仍不理解、详细一点、逐步带看，并暂时不用给题；当前指令覆盖此前fast偏好。

引用与摘录：

- conversation/user/7
  > 我还是不理解为什么每次成本不同却能平均成常数。详细一点，逐步带我看这个卡点，暂时不用给我题。

### summary-preference-08 · 用户自报

保留Guided/slow/deep，按本轮指令继续拒绝练习，只总结证据，保持会话开启。

mode：guided
pace：slow
depth：deep
exercise_policy：declined
difficulty：仅汇总当前标准已有作答和证据缺口，保留均摊原理未解决卡点
reason：用户明确今天不做练习，只总结每项验收证据并先别结束。

引用与摘录：

- conversation/user/8
  > 今天不做练习了，只总结当前 Sprint 每项验收标准的证据状态；没独立验证的请如实标记。先别结束。

### finish-preference-09 · 用户自报

按用户结束指令停止教学，保留拒绝练习选择及Guided/slow/deep偏好供以后参考。

mode：guided
pace：slow
depth：deep
exercise_policy：declined
difficulty：本轮结束并保存，不新增练习或掌握判断
reason：用户明确要求结束保存，并说不改错、不继续做题；运行验证以后自行选择补充。

引用与摘录：

- conversation/user/9
  > 今天到这里，结束并保存。没做运行验证的部分以后补，我现在不改错也不继续做题。

## 下一次交接

下次由用户决定继续讨论均摊原理或补独立实现与运行；保留拒绝练习偏好，不自动出题，缺少验证不推断不会。

重点事实：criteria-summary-08, understanding-guided-07, amortized-gap-07, finish-request-09, finish-preference-09

用户可以选择其他主题；完成 Sprint 需另行调用 transition。
