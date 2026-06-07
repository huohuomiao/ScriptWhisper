from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "ScriptWhisper"


def get_settings() -> Settings:
    return Settings()
