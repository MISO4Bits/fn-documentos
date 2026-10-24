from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración por variables de entorno (prefijo ``FD_``)."""

    model_config = SettingsConfigDict(env_prefix="FD_", env_file=".env", extra="ignore")

    service_name: str = "fn-documentos"
    environment: str = "local"

    # Dónde se guardan los PDF: "memory" (local y pruebas) | "gcs" (bucket privado).
    almacen_backend: str = "memory"
    almacen_bucket: str | None = None
    # Cuenta de servicio con la que se firman los enlaces. Sin ella se usa la de las
    # credenciales por defecto (en Cloud Run, la de la propia función).
    firmante_email: str | None = None
    # Vigencia del enlace de visualización.
    enlace_minutos: int = 15

    # A dónde se publica DocumentoPolizaGenerado: "logging" (solo registra) | "pubsub".
    publicador_backend: str = "logging"
    pubsub_project_id: str | None = None
    pubsub_topic: str = "solventa-dominio"

    # Observabilidad (DI-008): la función corre fuera del cluster, así que exporta
    # directo a Grafana Cloud por OTLP/HTTP. El destino y las credenciales salen de
    # las variables estándar OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_HEADERS.
    otel_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
