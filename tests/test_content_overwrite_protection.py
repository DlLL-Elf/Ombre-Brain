"""原文保护：content 整体替换前，旧正文自动进不可变原文证据层。

覆盖点：bucket_manager.update() 里 post.content = kwargs["content"] 之前的插入块。
依据：rule.md「记忆会被遗忘，但绝不能被抹去」——正文被覆盖也必须留痕。
"""

import pytest

from ombrebrain.storage.source_store import SourceStore


@pytest.mark.asyncio
async def test_content_overwrite_preserves_old_body_as_source_evidence(bucket_mgr):
    """整体替换正文前，旧正文写进 _sources/ 并挂 source_links。"""
    bid = await bucket_mgr.create(content="旧版正文", domain=["测试"])
    await bucket_mgr.update(bid, content="新版正文")

    bucket = await bucket_mgr.get(bid)
    assert bucket["content"] == "新版正文", "内容应确实替换为新的"

    refs = (bucket.get("metadata") or {}).get("source_refs") or []
    assert len(refs) == 1, "旧正文应挂一条 source_refs 到桶上"

    store = SourceStore(bucket_mgr.base_dir)
    assert store.read(refs[0]["ref"]) == "旧版正文", "旧正文应从原文层完整读回"


@pytest.mark.asyncio
async def test_content_overwrite_same_body_adds_no_evidence(bucket_mgr):
    """内容没变时不误触发保护，不产生多余原文引用。"""
    bid = await bucket_mgr.create(content="不变正文", domain=["测试"])
    await bucket_mgr.update(bid, content="不变正文")

    meta = (await bucket_mgr.get(bid)).get("metadata") or {}
    assert not (meta.get("source_refs") or meta.get("source_links")), \
        "相同内容覆盖不应新增原文引用"
