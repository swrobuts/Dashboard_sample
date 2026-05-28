from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DB
    postgres_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag_apple"
    neo4j_url: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # LLM — Gemini
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "text-embedding-004"
    gemini_embedding_dim: int = 768

    # LLM — local (LM Studio, OpenAI-compatible)
    local_llm_url: str = "http://localhost:1234/v1"
    local_llm_model: str = "google/gemma-3-12b"

    # Source
    wikipedia_url: str = "https://de.wikipedia.org/wiki/Apple"
    wikipedia_user_agent: str = "UC5-RAG-Apple/0.1 (kontakt@example.com)"

    # Limits
    max_llm_calls_per_query: int = 8
    max_tokens_per_call: int = 4096

    # UE1
    ue1_chunk_tokens: int = Field(default=400)
    ue1_chunk_overlap: int = Field(default=50)
    ue1_top_k: int = Field(default=8)


@lru_cache
def get_settings() -> Settings:
    return Settings()
