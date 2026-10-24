"""Casos de uso: generar el documento de una póliza y entregar el enlace para verlo."""

from __future__ import annotations

import logging
from collections.abc import Callable

from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind

from app.domain import (
    CONTENT_TYPE_PDF,
    EVENTO_DOCUMENTO_GENERADO,
    DatosPoliza,
    DomainEvent,
    Enlace,
    clave_del_documento,
)
from app.pdf import generar_pdf
from app.ports import AlmacenDocumentosPort, PublicadorEventosPort

logger = logging.getLogger("fn_documentos.documentos")
tracer = trace.get_tracer("fn_documentos")


class DocumentosService:
    def __init__(
        self,
        almacen: AlmacenDocumentosPort,
        publicador: PublicadorEventosPort,
        *,
        bucket: str,
        enlace_minutos: int = 15,
        generador: Callable[[DatosPoliza], bytes] = generar_pdf,
    ) -> None:
        self._almacen = almacen
        self._publicador = publicador
        self._bucket = bucket
        self._enlace_minutos = enlace_minutos
        self._generador = generador

    async def generar_por_evento(self, datos: DatosPoliza, atributos: dict[str, str]) -> bool:
        """``PolizaEmitida``: deja el PDF en el bucket y avisa con ``DocumentoPolizaGenerado``.

        Avisa **siempre**, también si el PDF ya existía (lo generó antes una consulta o una
        entrega anterior del mismo mensaje): así el aviso no se pierde si la publicación
        falló la primera vez. Quien lo recibe (Core) no manda dos correos por el mismo
        documento. Devuelve ``True`` si el PDF se creó en esta llamada.

        Lanza ``AlmacenNoDisponible`` / ``PublicacionFallida`` (Pub/Sub debe reentregar).
        """
        contexto = propagate.extract(atributos)
        with tracer.start_as_current_span(
            "documentos.generar_poliza", context=contexto, kind=SpanKind.CONSUMER
        ):
            creado = await self._asegurar(datos)
            await self._avisar(datos)
            return creado

    async def enlace_de_visualizacion(self, datos: DatosPoliza) -> Enlace:
        """Consulta desde Core: si el PDF no existe todavía (el evento se perdió o aún no
        llegó) se genera ahora, y se devuelve el enlace temporal para verlo."""
        with tracer.start_as_current_span("documentos.enlace_poliza"):
            creado = await self._asegurar(datos)
            if creado:
                # Lo creó esta consulta: el evento no lo ha procesado, así que el aviso sale
                # de aquí para que el correo con el adjunto no dependa de ese evento.
                await self._avisar(datos)
            return await self._almacen.enlace_firmado(
                clave_del_documento(datos.poliza_id),
                f"Poliza-{datos.numero}.pdf",
                self._enlace_minutos,
            )

    async def _asegurar(self, datos: DatosPoliza) -> bool:
        clave = clave_del_documento(datos.poliza_id)
        if await self._almacen.existe(clave):
            logger.info("documento ya existe poliza_id=%s", datos.poliza_id)
            return False
        pdf = self._generador(datos)
        creado = await self._almacen.guardar_si_no_existe(clave, pdf, CONTENT_TYPE_PDF)
        logger.info(
            "documento %s poliza_id=%s bytes=%d",
            "generado" if creado else "ya lo había generado otra llamada",
            datos.poliza_id,
            len(pdf),
        )
        return creado

    async def _avisar(self, datos: DatosPoliza) -> None:
        await self._publicador.publicar(
            DomainEvent(
                EVENTO_DOCUMENTO_GENERADO,
                {
                    "polizaId": datos.poliza_id,
                    "clienteId": datos.cliente_id,
                    "numero": datos.numero,
                    "bucket": self._bucket,
                    "objeto": clave_del_documento(datos.poliza_id),
                    "nombreArchivo": f"Poliza-{datos.numero}.pdf",
                    "contentType": CONTENT_TYPE_PDF,
                },
            )
        )
