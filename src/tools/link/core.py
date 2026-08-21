"""link —— 手动补一根线（3.5.0）。

时间线（thread）给「顺序」（然后呢），补线给「叙事」（所以呢）——
跨越时间的经历连续。例：很久以前的一段对话，与很久以后的一次回望，
中间隔了几百条，但经历上是同一件事的两端。算法发现不了，只有活过的人知道。

link 是 3.0.0 关闭的手动建边入口的重新打开，但开成「手动声明」而非
「自动发现」：只加边、不删任何东西、不 bump 活跃度、带 source=manual，
和自动建的边（auto=True）区分开。

复用现有类型（不新开平行结构）：
- references        A 正文提到了 B（引用，最可靠：自己写下的关系）
- continuation_of   A 是 B 的后续（经历连续，跨时间）
- related_to        两者相关

软边护栏：只指方向、不删记忆；边只是 hint，写不进也不影响记忆本身。
"""

from __future__ import annotations

from .. import _runtime as rt
from .._common import check_metadata_size
from ombrebrain.storage.relation_store import (
    EXCLUDED_RELATION_TYPES,
    MAX_RELATION_LINKS,
    normalize_relation_label,
    normalize_relation_links,
    reverse_relation_type,
)

# 补线只开放这三种：引用 / 连续 / 相关。
# caused_by/causes 是因果存量类型（不自动建、也不手动补）；same_event 是时间重叠
# 的自动类型，不该手动指定。
_LINKABLE_TYPES = ("references", "continuation_of", "related_to")


def _eligible(meta: dict) -> bool:
    if not isinstance(meta, dict):
        return True
    t = str(meta.get("type") or "dynamic").strip().lower()
    if t in EXCLUDED_RELATION_TYPES:
        return False
    return not (meta.get("deleted_at") or meta.get("tombstone"))


def _links(meta: dict) -> list[dict]:
    try:
        return normalize_relation_links((meta or {}).get("relation_links"))
    except ValueError:
        return []


def _has(meta: dict, tid: str, rtype: str) -> bool:
    return any(
        l.get("target_bucket_id") == tid
        and l.get("type") == rtype
        and l.get("status") == "active"
        for l in _links(meta)
    )


async def link(
    bucket_id: str,
    target_bucket_id: str,
    relation_type: str = "references",
    label: str = "",
) -> str:
    bucket_id = "" if bucket_id is None else str(bucket_id).strip()
    target_bucket_id = "" if target_bucket_id is None else str(target_bucket_id).strip()
    relation_type = str(relation_type or "references").strip().lower()
    label = "" if label is None else str(label)

    if not bucket_id or not target_bucket_id:
        return "补线需要两个 bucket_id：这条，和连到的那条。"
    if bucket_id == target_bucket_id:
        return "补线不能连到自己身上。"
    if relation_type not in _LINKABLE_TYPES:
        return (
            f"relation_type 只支持 {', '.join(_LINKABLE_TYPES)}；"
            f"收到的是 {relation_type!r}。"
        )
    try:
        label = normalize_relation_label(label)
    except ValueError as exc:
        return f"label 不合法：{exc}"

    metadata_err = check_metadata_size(bucket_id=bucket_id)
    if metadata_err:
        return metadata_err

    if rt.mark_op:
        rt.mark_op("link")

    source = await rt.bucket_mgr.get(bucket_id)
    target = await rt.bucket_mgr.get(target_bucket_id)
    if not source:
        return f"未找到记忆桶: {bucket_id}"
    if not target:
        return f"未找到记忆桶: {target_bucket_id}"
    source_meta = source.get("metadata") or {}
    target_meta = target.get("metadata") or {}
    if not _eligible(source_meta):
        return f"{bucket_id} 是分层桶（plan/feel/letter/i）或已归档，不参与关系网。"
    if not _eligible(target_meta):
        return f"{target_bucket_id} 是分层桶（plan/feel/letter/i）或已归档，不参与关系网。"

    reverse_type = reverse_relation_type(relation_type)

    left_has = _has(source_meta, target_bucket_id, relation_type)
    right_has = _has(target_meta, bucket_id, reverse_type)
    if left_has and right_has:
        return f"这条线已经在了：{bucket_id} ↔ {target_bucket_id}。"

    def _mutation(left_post, right_post):
        left_links = _links(left_post.metadata)
        right_links = _links(right_post.metadata)
        left_changed = False
        right_changed = False
        if not _has(left_post.metadata, target_bucket_id, relation_type):
            if len(left_links) >= MAX_RELATION_LINKS:
                return False, False, -1
            left_links.append(
                {
                    "target_bucket_id": target_bucket_id,
                    "type": relation_type,
                    "label": label,
                    "status": "active",
                    "source": "manual",
                }
            )
            try:
                left_post["relation_links"] = normalize_relation_links(left_links)
            except ValueError:
                return False, False, -1
            left_changed = True
        if not _has(right_post.metadata, bucket_id, reverse_type):
            if len(right_links) >= MAX_RELATION_LINKS:
                return False, False, -1
            right_links.append(
                {
                    "target_bucket_id": bucket_id,
                    "type": reverse_type,
                    "label": label,
                    "status": "active",
                    "source": "manual",
                }
            )
            try:
                right_post["relation_links"] = normalize_relation_links(right_links)
            except ValueError:
                return False, False, -1
            right_changed = True
        return left_changed, right_changed, int(left_changed or right_changed)

    try:
        result = await rt.bucket_mgr.mutate_relation_pair(
            bucket_id, target_bucket_id, _mutation
        )
    except Exception as exc:  # noqa: BLE001
        return f"补线失败：{type(exc).__name__}: {exc}"

    if result == -1:
        return "补线失败：某一侧的 relation_links 已达上限。"
    if result == 0:
        return f"补线没有生效（{bucket_id} ↔ {target_bucket_id}）。"
    return (
        f"已补线：{bucket_id} --{relation_type}--> {target_bucket_id}"
        f"（反向 {reverse_type} 已同步，source=manual）。"
    )
