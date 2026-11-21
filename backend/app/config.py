import os


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    def __init__(self):
        self.llm_api_keys: list[str] = _split_csv(os.getenv("LLM_API_KEYS", ""))
        self.llm_model: str = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
        self.allowed_origins: list[str] = _split_csv(os.getenv("ALLOWED_ORIGINS", "*"))
        self.enable_failure_simulation: bool = os.getenv(
            "ENABLE_FAILURE_SIMULATION", "false"
        ).lower() == "true"
        self.default_system_prompt: str = os.getenv(
            "DEFAULT_SYSTEM_PROMPT", "You are a helpful assistant."
        )

    @property
    def db_path(self) -> str:
        # sqlite:////data/app.db -> /data/app.db ; sqlite:///./data/app.db -> ./data/app.db
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            return self.database_url[len(prefix):]
        return self.database_url

    @property
    def key_ids(self) -> list[str]:
        return [f"key_{i + 1}" for i in range(len(self.llm_api_keys))]


settings = Settings()
