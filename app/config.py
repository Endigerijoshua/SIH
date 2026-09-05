from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    firms_map_key: str = ""
    firms_dataset: str = "VIIRS_SNPP_NRT"
    firms_bbox: str = "68,6,97,37"
    firms_days: int = 3
    buffer_meters: int = 1000
    fire_history_db: str = "fire_history.db"
    persistence_radius_m: int = 300
    persistence_min_occurrences: int = 2
    persistence_lookback_days: int = 14
    clustering_eps_m: int = 500
    clustering_min_samples: int = 2
    industrial_states: dict[str, str] = {
        "gujarat": "67.5,20,75,25",
        "jharkhand": "83,21.5,88,25.5",
        "maharashtra": "72,15,81,22.5",
    }
    overpass_timeout: int = 180
    industrial_cache_file: str = "industrial_zones_cache.json"
    vegetation_cache_file: str = "vegetation_zones_cache.json"
    industrial_cache_max_age_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
