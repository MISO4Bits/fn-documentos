"""Adaptador de producción: publica ``DocumentoPolizaGenerado`` en el tópico compartido de
Google Cloud Pub/Sub (ver iac-gcp-dev/modules/pubsub). El tipo del evento va como atributo del
mensaje (``tipo``), igual que en Core y en los demás servicios.

Fuera del alcance de las pruebas locales (requiere credenciales e infraestructura GCP): se
excluye de la medición de cobertura.
"""

from __future__ import annotations

import asyncio
import json
import logging

from google.cloud import pubsub_v1
from opentelemetry import propagate

from app.domain import DomainEvent, PublicacionFallida

logger = logging.getLogger("fn_documentos.adapters.pubsub")


class PublicadorPubSub:  # pragma: no cover
    def __init__(self, project_id: str, topic: str) -> None:
        self._publicador = pubsub_v1.PublisherClient()
        self._topic_path = self._publicador.topic_path(project_id, topic)

    async def publicar(self, evento: DomainEvent) -> None:
        cuerpo = json.dumps(
            {
                "tipo": evento.tipo,
                "id": evento.id,
                "ocurridoEn": evento.ocurrido_en.isoformat(),
                "datos": evento.datos,
            }
        ).encode("utf-8")
        atributos = {"tipo": evento.tipo}
        propagate.inject(atributos)
        futuro = self._publicador.publish(self._topic_path, cuerpo, **atributos)
        # La función corre en Cloud Run: la CPU se reduce al responder, así que se espera el
        # acuse antes de confirmar el mensaje que se está procesando.
        try:
            message_id = await asyncio.to_thread(futuro.result, timeout=10)
        except Exception as exc:
            logger.exception("no se pudo publicar el evento tipo=%s id=%s", evento.tipo, evento.id)
            raise PublicacionFallida(str(exc)) from exc
        logger.info(
            "evento_publicado: tipo=%s id=%s message_id=%s", evento.tipo, evento.id, message_id
        )
