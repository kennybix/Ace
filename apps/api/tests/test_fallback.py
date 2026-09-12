"""Automatic model fallback: selected model errors → next in llm_fallback_order answers,
and provenance (last_model_used) records the model that actually wrote the content."""

import pytest

from ace_api.config import Settings
from ace_api.llm import client as llm


def _real_settings(**over):
    base = Settings(llm_fake=False, llm_api_key="test-key", **over)
    return lambda: base


def _gateway_fake(failing: set[str], answered: list[str]):
    async def fake(task, model, system, user, temperature, max_tokens):
        if model["id"] in failing:
            raise llm.LLMError(f"gateway 503: auth_unavailable ({model['id']})")
        answered.append(model["id"])
        return {"ok": True, "by": model["id"]}
    return fake


@pytest.mark.asyncio
async def test_falls_back_to_next_model(monkeypatch):
    monkeypatch.setattr(llm, "settings", _real_settings())
    answered: list[str] = []
    monkeypatch.setattr(llm, "_gateway_json", _gateway_fake({"gpt-5.5", "opus-5"}, answered))
    out = await llm.chat_json("plan_rationale", "sys", "{}", model_id="gpt-5.5")
    assert out["ok"] is True
    # chain: gpt-5.5 (fails) → opus-5 (fails) → next in llm_fallback_order that works
    assert answered == ["opus-4.8"]
    assert llm.last_model_used() == "opus-4.8"


@pytest.mark.asyncio
async def test_primary_success_no_fallback(monkeypatch):
    monkeypatch.setattr(llm, "settings", _real_settings())
    answered: list[str] = []
    monkeypatch.setattr(llm, "_gateway_json", _gateway_fake(set(), answered))
    out = await llm.chat_json("plan_rationale", "sys", "{}", model_id="fable-5.1")
    assert out["by"] == "fable-5.1"
    assert answered == ["fable-5.1"]
    assert llm.last_model_used() == "fable-5.1"


@pytest.mark.asyncio
async def test_all_models_down_raises_friendly_error(monkeypatch):
    monkeypatch.setattr(llm, "settings", _real_settings())
    all_ids = {m["id"] for m in Settings().llm_models}
    monkeypatch.setattr(llm, "_gateway_json", _gateway_fake(all_ids, []))
    with pytest.raises(llm.LLMError) as e:
        await llm.chat_json("plan_rationale", "sys", "{}")
    assert "budget" in str(e.value).lower()
    assert "auth_unavailable" not in str(e.value)  # gory details go to logs, not the app


@pytest.mark.asyncio
async def test_fallback_disabled_fails_fast(monkeypatch):
    monkeypatch.setattr(llm, "settings", _real_settings(llm_fallback=False))
    answered: list[str] = []
    monkeypatch.setattr(llm, "_gateway_json", _gateway_fake({"gpt-5.5"}, answered))
    with pytest.raises(llm.LLMError):
        await llm.chat_json("plan_rationale", "sys", "{}", model_id="gpt-5.5")
    assert answered == []


@pytest.mark.asyncio
async def test_new_anthropic_models_registered():
    s = Settings()
    ids = {m["id"]: m["gateway"] for m in s.llm_models}
    assert ids["opus-5"] == "claude-opus-5"
    assert ids["fable-5.1"] == "claude-fable-5-1"
    # claude-* models must never receive a temperature param — gateway ids must keep prefix
    assert all(g.startswith("claude") for i, g in ids.items() if "opus" in i or "fable" in i)
