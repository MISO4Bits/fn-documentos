"""Puertos del hexágono. Los adaptadores viven en ``app/adapters``."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain import DomainEvent, Enlace


@runtime_checkable
class AlmacenDocumentosPort(Protocol):
    async def existe(self, clave: str) -> bool: ...

    async def guardar_si_no_existe(self, clave: str, datos: bytes, content_type: str) -> bool:
        """Guarda el documento solo si todavía no existe. ``True`` si lo creó esta llamada,
        ``False`` si ya estaba (otra llamada lo creó antes). Es la precondición que impide que
        dos generaciones simultáneas se pisen o avisen dos veces.

        Lanza ``AlmacenNoDisponible`` si el almacén falla.
        """
        ...

    async def enlace_firmado(self, clave: str, nombre_archivo: str, minutos: int) -> Enlace:
        """Enlace temporal para ver el documento en el visor (no para descargarlo)."""
        ...


@runtime_checkable
class PublicadorEventosPort(Protocol):
    async def publicar(self, evento: DomainEvent) -> None:
        """Publica un evento de dominio. Lanza ``PublicacionFallida`` si no lo logra."""
        ...
