from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelInfo(dict):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ACE_", extra="ignore")

    database_url: str = "postgresql://ace:ace@localhost:5445/ace"
    api_port: int = 8040

    # LLM gateway (CLI proxy, OpenAI-compatible). Key intentionally unset by default.
    llm_base_url: str = "http://localhost:8317/v1"
    llm_api_key: str = ""
    # id = Ace-internal id, gateway = model id at the proxy
    llm_models: list[dict] = [
        {"id": "opus-4.8", "label": "Claude Opus 4.8", "gateway": "claude-opus-4-8"},
        {"id": "fable-5", "label": "Claude Fable 5", "gateway": "claude-fable-5"},
        {"id": "gpt-5.5", "label": "GPT-5.5", "gateway": "gpt-5.5"},
        {"id": "gpt-5.6", "label": "GPT-5.6", "gateway": "gpt-5.6"},
    ]
    llm_default_model: str = "gpt-5.5"
    llm_fake: bool = False  # tests/dev without a gateway key use the deterministic fake
    # Deliberate generation: every generated question passes an LLM critic (judge → revise →
    # accept/kill) before it can be served. Doubles generation cost; runs in nightly batch.
    deliberate_generation: bool = True

    # Embeddings: "hash" (deterministic, no deps/network — dev & tests) or "proxy" (gateway /embeddings)
    embedder: str = "hash"
    embedding_dim: int = 256

    jwt_secret: str = "dev-secret-change-me"
    otp_dev_echo: bool = True  # dev: return OTP in API response instead of sending email

    upload_dir: str = "./data/uploads"
    youtube_api_key: str = ""


@lru_cache
def settings() -> Settings:
    return Settings()
