# 施工单：把散落的珍珠串成能主动追溯的网（读取层）

> 创建：2026-08-21。目标：先「把门打开」——读取层落地，建的部分后聊。

## 现状（已摸清）

- 后端已在自动建边（`same_event` / `continuation_of` / `related_to`），存于桶 `metadata.relation_links`，双向写入、fire-and-forget。
- 因果边（`caused_by` / `causes`）**永不自动建**（存量手动数据仍可能存在）。
- 但浮现层只露出 `relation_hint` 的两条裸 id（`↳ 前段 → 7f3a…`），无标题、无时间、无方向分组，也没有「顺着走」的入口。
- 桶结构：`{id, content, metadata}`；metadata 有 `title`（120 上限）、`created`、`type`、`relation_links` 等。
- 读桶抓手：`rt.bucket_mgr.get(bucket_id)` / `get_including_archive(bucket_id)`。

## 三刀（按风险从低到高）

### 第一刀：recall（回想）—— 走路的大门 ✅ 已完成
- 位置：新建 `src/tools/recall/__init__.py` + `src/tools/recall/core.py`
- 职责：给定 `bucket_id`，返回该桶正文 + 完整路口（按方向分组：← 之前 / → 之后 / ≈ 同刻 / ↔ 相关，每条带邻居标题 + 日期 + id）。
- 注册：`server.py` 加 `@mcp.tool()` 的 `recall`，薄封装转发。
- 测试：`tests/test_recall.py`（4 用例，带 @pytest.mark.asyncio）。

### 第二刀：thread（串珠）—— 话题时间线 ✅ 已完成
- 位置：新建 `src/tools/thread/__init__.py` + `src/tools/thread/core.py`
- 职责：给定关键词，检索相关桶 → 按创建时间升序排成一条线 → 每站一行（序号 + 日期 + 标题 + id）。0 LLM 调用。
- 复用 recall.core 的 `_bucket_title` / `_bucket_date` / `_EXCLUDED_TYPES`。
- 排序已处理 aware/naive 时区混排（统一转 naive）。
- 注册：`server.py` 加 `@mcp.tool()` 的 `thread`。
- 测试：`tests/test_thread.py`（4 用例，带 @pytest.mark.asyncio）。

### 第三刀：breath 路口升级（分组方向化）✅ 已完成（轻量版）
- 位置：`src/ombrebrain/storage/relation_store.py`
- 职责：
  - 新增共享 `render_junction`（async，完整版：读邻居带标题/日期），供 recall 用。
  - 新增 `bucket_title`（四级回退）/ `bucket_date` / `bucket_type` / `EXCLUDED_RELATION_TYPES` / `DIRECTION_GROUPS`。
  - 升级 `relation_hint` 为「按方向分组 + 目标 id」的轻量版（零 I/O），自动惠及 breath 主浮现 / catalog / dream 三处。
- 重构：`recall/core.py` 改用共享 `render_junction`（删掉自己的重复分组）；`thread/core.py` 改 import 到 relation_store。
- 未改：`_verbatim.py` / `catalog.py` / `dream/output.py`（relation_hint 签名兼容，自动升级）。

### 第四刀：breath inline 标题化 — 决策：保持分层，暂不做
- 目标（原设想）：让主 breath 浮现末尾的路口也带邻居标题/日期。
- 判断（2026-08-21）：暂缓，倾向不做。理由：
  1. token 预算：breath 主浮现有 breath_max_tokens（默认 10000），正文逐字不截断、放不下整桶省略；
     路口带标题日期会吃掉预算、挤占正文，违背「浮现是为了读正文」的初衷。recall 单条展开无此压力。
  2. 回忆的分层本来就是对：breath 给「模糊方向」，recall 给「专注展开」。人回忆先想起「有这条线」，
     细节是「再想一下」才浮现。把 breath 也做完整 = 把 recall 的活重复一遍。
  3. 风险收益不成比例：异步化 render_stored_bucket 改 14 处源码 + 11 处测试，只省一次 recall 点击。
- 折中（若将来要做）：不异步化 render_stored_bucket，而是在 breath 渲染前的 async 循环里批量预取
  邻居标题，把标题 map 作为参数传进渲染函数。改动小、可批量避免 N×M 串行 I/O、不破坏 11 处测试。

## 标签映射（读侧展示用）

| relation 类型 | 路口标签 |
|---|---|
| continuation_of | ← 之前 |
| continues | → 之后 |
| same_event | ≈ 同刻 |
| related_to | ↔ 相关 |
| caused_by（存量） | ← 因为 |
| causes（存量） | → 所以 |
| custom | 自定义·label |

## 边界（不碰）

- 只碰读取 / 展示层。不碰写入、不碰建边、不碰遗忘/衰减、不碰原文证据、不碰删除/归档。
- 因果边维持「不自动建」；读侧保留对存量因果边的显示。

## 建的部分（8月21日定案）

- 经历线「补线」：✅ 开成 link 工具（手动声明一条边，3.0.0 关闭的手动入口重开）。
  复用现有类型 + source=manual，开放 references / continuation_of / related_to 三种；
  双向同步写、幂等、软边（只指方向不删记忆、不 bump 活跃度）。3.5.0 落地。
- 话题线「固化」：❌ 先不做，thread 现查现排。将来按需 thread_pin（某话题反复
  查询才冻成固定线，刷新挂 dream）。

## 环境变量 / 路径依赖

- 本批改动不新增、不修改任何环境变量，不新增磁盘路径。

---

# 建边篇：event_time + references（8月21日，方案已对齐）

> 决策来源：设计备忘 002（event_time 谁来填）、003（建边类型复用+只新增 references）。

## 结论

- **event_time**：hold 时模型主动填（可选参数，默认 created）；系统解析兜底**不做**（定案 2026-08-21：大多数记忆「记录时刻=事件时刻」，需要特殊标注的由模型手动填、或事后用 trace(event_time=...) 修正；系统解析反而可能出错）。来源打标 manual/fallback（无 parsed 层）。优先级恒为 manual > fallback(created)。
- **建边**：三层边是"怎么发现"（来源策略），现有类型是"存成什么"（语义），解耦。≈同刻→same_event、之前/之后→continuation_of、相关→related_to 均已有；唯一新增 references（有向，反向 referenced_by）。caused_by/causes 原样保留，只增量不迁移。
- **本次最小集**：1 字段(event_time) + 1 类型(references) + thread/recall 接到现有类型。

## 改动清单（9 文件，从底层往上）

1. `src/ombrebrain/storage/relation_store.py`：_FIXED_RELATION_TYPES + references/referenced_by；_REVERSE；display label（引用/被引用）；DIRECTION_GROUPS 加 references（🔗 引用）。
2. `src/bucket_manager.py` create()：加 event_time（落 metadata.event_time，来源 manual；不传不写，读侧回退 created）、references（落 relation_links 的 references 边，auto=False）。
3. `src/tools/thread/core.py`：排序优先 event_time，回退 created；bucket_date 优先 event_time。
4. `src/tools/_common.py`：merge_or_create + _merge_or_create_inner 透传 event_time/references。
5. `src/tools/hold/core.py`：store_core 透传。
6. `src/tools/hold/feel.py`、`pinned.py`：store_feel/store_pinned 透传（直调 create）。
7. `src/tools/hold/__init__.py` dispatch：加参数 + 转发。
8. `src/server.py`：hold 工具签名 + docstring 加 event_time/references。
9. `tests/`：新增测试（event_time 排序、references 边渲染）。

## 关键用例（一手证据）

- 「一条回溯写下的记忆」(BUCKET_A) references 「它提到的那段对话」(BUCKET_B)，两桶 event_time 都是 2025-12-05（回溯记忆，created 是 2026-08-10）。thread 排序必须用 event_time 才能串对。

## 状态（8月21日）

- ✅ 已完成：写侧（create + 三条 hold 路径透传 event_time/references）+ 读侧（thread 排序、bucket_date、references 边渲染）+ 测试。
- ✅ 已完成（3.4.1，8月21日续）：references 反向边自动补齐——dream 全量扫时幂等补 referenced_by（`collect_missing_reference_reverse` 纯判定 + `backfill_reference_reverse_links` 写入，挂 dream dispatch 的 fire-and-forget）。trace 工具新增 event_time 参数，支持事后修正（非空覆盖并标 manual）或清除（`\clear`，回到 created 回退）。
- ❌ 不做（定案）：event_time 系统解析兜底（parsed 来源）——见上「结论」。
- ✅ 已完成（3.5.0，8月21日）：补线 link 工具（`src/tools/link/`）——手动声明
  references / continuation_of / related_to 边，双向写 + source=manual + 幂等 +
  软边；relation_store 的 normalize 保留 source 字段；server.py 注册 @mcp.tool。
- 版本：3.3.0 → 3.4.0 → 3.4.1 → 3.5.0。
