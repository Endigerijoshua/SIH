from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    firms_map_key: str = ""
    firms_dataset: str = "VIIRS_SNPP_NRT"
    firms_bbox: str = "68,7,97,37"
    firms_days: int = 1
    buffer_meters: int = 1000
    persistence_radius_km: float = 3.0
    persistence_min_occurrences: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
