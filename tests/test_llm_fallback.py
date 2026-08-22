import os

from extract.llm_fallback import should_use_llm


def test_llm_disabled_by_default(monkeypatch):
    monkeypatch.delenv("UNILOG_LLM_ENABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert should_use_llm(
        identity_method="unknown",
        evidence_count=1,
        category_id="generic_industrial",
        part_desc="3/8 CPLG BRS 150#",
    ) is False


def test_llm_only_when_opted_in_and_gates_pass(monkeypatch):
    monkeypatch.setenv("UNILOG_LLM_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert should_use_llm(
        identity_method="unknown",
        evidence_count=1,
        category_id="generic_industrial",
        part_desc="3/8 CPLG BRS 150#",
    ) is True


def test_llm_skips_known_brand(monkeypatch):
    monkeypatch.setenv("UNILOG_LLM_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert should_use_llm(
        identity_method="part_desc",
        evidence_count=1,
        category_id="generic_industrial",
        part_desc="3/8 CPLG BRS 150#",
    ) is False


def test_llm_skips_rich_evidence(monkeypatch):
    monkeypatch.setenv("UNILOG_LLM_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert should_use_llm(
        identity_method="unknown",
        evidence_count=5,
        category_id="generic_industrial",
        part_desc="3/8 CPLG BRS 150#",
    ) is False
