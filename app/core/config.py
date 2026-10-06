"""Configuración de la aplicación, leída del entorno."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DentalMaster API"
    debug: bool = False

    database_url: str = "postgresql+psycopg://dental:dental@localhost:5432/odonto"

    # Autenticación
    secret_key: str = "cambiar-en-produccion"
    algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 14

    # Se declara como str, no como list[str]: pydantic-settings intenta
    # json.loads() sobre los campos complejos antes de que corra cualquier
    # validador, así que "http://a,http://b" reventaría. Se parte en la
    # propiedad de abajo.
    cors_origins: str = "http://localhost:5173"

    # El servidor corre en UTC; «hoy» y las horas que se muestran son las de la clínica.
    zona_horaria: str = "America/Santo_Domingo"

    # Almacén de archivos (fotos, exámenes, comprobantes): un volumen aparte.
    almacen_dir: str = "/srv/almacen"
    archivo_max_mb: int = 25

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
