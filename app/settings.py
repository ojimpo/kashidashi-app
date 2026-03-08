from __future__ import annotations

import os
from dataclasses import dataclass

from .domain import DEFAULT_LIBRARY, JST_TIMEZONE


@dataclass(slots=True, frozen=True)
class Settings:
    app_name: str = "kashidashi"
    database_url: str = "sqlite:////data/kashidashi.db"
    default_library: str = DEFAULT_LIBRARY
    display_timezone: str = JST_TIMEZONE


def load_settings() -> Settings:
    return Settings(
        app_name=os.getenv("KASHIDASHI_APP_NAME", "kashidashi"),
        database_url=os.getenv("KASHIDASHI_DATABASE_URL", "sqlite:////data/kashidashi.db"),
    )

