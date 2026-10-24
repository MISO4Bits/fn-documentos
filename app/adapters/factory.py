"""Fábrica simple de adaptadores a partir de la configuración (sin framework de DI)."""

from __future__ import annotations

from app.adapters.memoria import AlmacenEnMemoria, PublicadorQueRegistra
from app.config import Settings
from app.ports import AlmacenDocumentosPort, PublicadorEventosPort

BUCKET_EN_MEMORIA = "bucket-local"


def build_almacen(settings: Settings) -> AlmacenDocumentosPort:
    if settings.almacen_backend == "memory":
        return AlmacenEnMemoria()
    if settings.almacen_backend == "gcs":  # pragma: no cover
        from app.adapters.gcs_almacen import AlmacenGcs

        if not settings.almacen_bucket:
            raise ValueError("FD_ALMACEN_BUCKET es obligatorio con FD_ALMACEN_BACKEND=gcs")
        return AlmacenGcs(settings.almacen_bucket, settings.firmante_email)
    raise ValueError(f"almacen_backend no soportado: {settings.almacen_backend}")


def build_publicador(settings: Settings) -> PublicadorEventosPort:
    if settings.publicador_backend == "logging":
        return PublicadorQueRegistra()
    if settings.publicador_backend == "pubsub":  # pragma: no cover
        from app.adapters.pubsub_publicador import PublicadorPubSub

        if not settings.pubsub_project_id:
            raise ValueError("FD_PUBSUB_PROJECT_ID es obligatorio con FD_PUBLICADOR_BACKEND=pubsub")
        return PublicadorPubSub(settings.pubsub_project_id, settings.pubsub_topic)
    raise ValueError(f"publicador_backend no soportado: {settings.publicador_backend}")


def nombre_del_bucket(settings: Settings) -> str:
    return settings.almacen_bucket or BUCKET_EN_MEMORIA
