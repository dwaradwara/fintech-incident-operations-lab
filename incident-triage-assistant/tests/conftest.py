import pytest


@pytest.fixture(autouse=True)
def deterministic_test_environment(monkeypatch):
    # Unit tests must never call the live LLM unless explicitly mocked.
    monkeypatch.setenv("TRIAGE_ENGINE", "rules")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
