"""Adaptadores en memoria: corren la función sola y sirven de dobles en las pruebas."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.domain import AlmacenNoDisponible, DomainEvent, Enlace, PublicacionFallida

logger = logging.getLogger("fn_documentos.adapters.memoria")


class AlmacenEnMemoria:
    """Guarda los documentos en un diccionario. ``cae=True`` imita al bucket caído."""

    def __init__(self, *, cae: bool = False) -> None:
        self.objetos: dict[str, tuple[bytes, str]] = {}
        self.cae = cae

    def _verificar(self) -> None:
        if self.cae:
            raise AlmacenNoDisponible("el almacén no responde")

    async def existe(self, clave: str) -> bool:
        self._verificar()
        return clave in self.objetos

    async def guardar_si_no_existe(self, clave: str, datos: bytes, content_type: str) -> bool:
        self._verificar()
        if clave in self.objetos:
            return False
        self.objetos[clave] = (datos, content_type)
        return True

    async def enlace_firmado(self, clave: str, nombre_archivo: str, minutos: int) -> Enlace:
        self._verificar()
        if clave not in self.objetos:
            raise AlmacenNoDisponible("el documento no existe")
        ahora = datetime.now(UTC)
        return Enlace(
            f"https://almacen.local/{clave}?archivo={nombre_archivo}",
            ahora + timedelta(minutes=minutos),
        )


class PublicadorEnMemoria:
    """Guarda los eventos publicados. ``falla=True`` imita a Pub/Sub caído."""

    def __init__(self, *, falla: bool = False) -> None:
        self.publicados: list[DomainEvent] = []
        self.falla = falla

    async def publicar(self, evento: DomainEvent) -> None:
        if self.falla:
            raise PublicacionFallida("Pub/Sub no responde")
        self.publicados.append(evento)


class PublicadorQueRegistra:
    """Para correr la función sin Pub/Sub: solo anota el tipo y el id del evento."""

    async def publicar(self, evento: DomainEvent) -> None:
        # Los datos traen el identificador de la póliza y del cliente: no se registran.
        logger.info("evento_dominio: tipo=%s id=%s", evento.tipo, evento.id)
