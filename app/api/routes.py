from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.schemas import EnlaceOut, SobrePush
from app.domain import (
    AlmacenNoDisponible,
    DatosPoliza,
    MensajeInvalido,
    PublicacionFallida,
    decodificar,
    parsear_evento,
)
from app.services import DocumentosService
from app.telemetry import vaciar

logger = logging.getLogger("fn_documentos.api")
router = APIRouter()


def get_service(request: Request) -> DocumentosService:
    return request.app.state.service


ServiceDep = Annotated[DocumentosService, Depends(get_service)]


@router.post(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Pub/Sub"],
    responses={503: {"description": "La generación falló; Pub/Sub debe reentregar el mensaje."}},
)
async def recibir_mensaje(sobre: SobrePush, request: Request, service: ServiceDep) -> Response:
    """Endpoint de la suscripción *push*: cualquier 2xx confirma el mensaje, cualquier otro
    código hace que Pub/Sub lo reentregue con espera creciente.

    Un mensaje que nunca podrá procesarse (mal formado) se confirma igual, registrando el
    error: devolverlo solo lo haría circular sin fin.
    """
    mensaje = sobre.message
    # Solo nombres de atributos y el tipo de evento: ningún dato del cliente.
    logger.info(
        "mensaje recibido id=%s intento_entrega=%s publicado=%s tipo=%s atributos=%s",
        mensaje.message_id,
        sobre.delivery_attempt if sobre.delivery_attempt is not None else "-",
        mensaje.publish_time or "-",
        mensaje.attributes.get("tipo", "-"),
        sorted(mensaje.attributes),
    )
    inicio = time.perf_counter()
    resultado = "error"
    try:
        datos = parsear_evento(decodificar(mensaje.data))
        if datos is None:
            resultado = "ignorado"
            logger.info("mensaje ignorado: no es un PolizaEmitida")
        else:
            creado = await service.generar_por_evento(datos, mensaje.attributes)
            resultado = "generado" if creado else "ya_existia"
    except MensajeInvalido as exc:
        resultado = "descartado"
        logger.error("mensaje descartado id=%s motivo=%s", mensaje.message_id, exc)
    except (AlmacenNoDisponible, PublicacionFallida) as exc:
        resultado = "reintentar"
        logger.warning("mensaje se devuelve a Pub/Sub id=%s motivo=%s", mensaje.message_id, exc)
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    finally:
        logger.info(
            "mensaje procesado id=%s resultado=%s duracion_ms=%d",
            mensaje.message_id,
            resultado,
            (time.perf_counter() - inicio) * 1000,
        )
        vaciar(request.app.state.telemetry)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/v1/documentos/polizas/enlace",
    response_model=EnlaceOut,
    tags=["Documentos"],
    responses={
        400: {"description": "Los datos de la póliza no son válidos."},
        503: {"description": "El almacén de documentos no responde."},
    },
)
async def enlace_de_la_poliza(datos: DatosPoliza, request: Request, service: ServiceDep):
    """Enlace temporal para ver el PDF de una póliza emitida. Lo llama CoreTransaccional.

    Si el PDF no existe todavía, se genera en esta llamada. Quien llama manda los mismos
    datos que viajan en ``PolizaEmitida``: la función no consulta a nadie.
    """
    try:
        enlace = await service.enlace_de_visualizacion(datos)
    except (AlmacenNoDisponible, PublicacionFallida) as exc:
        logger.warning("enlace no disponible poliza_id=%s motivo=%s", datos.poliza_id, exc)
        return _problema(503, "Documento no disponible", "Intenta de nuevo en un momento")
    finally:
        vaciar(request.app.state.telemetry)
    return EnlaceOut(url=enlace.url, expira_en=enlace.expira_en)


def _problema(codigo: int, titulo: str, detalle: str) -> Response:
    import json

    cuerpo = json.dumps(
        {"type": "about:blank", "title": titulo, "status": codigo, "detail": detalle}
    )
    return Response(cuerpo, status_code=codigo, media_type="application/problem+json")
