"""Adaptador de producción: los PDF viven en un bucket privado de Cloud Storage.

Los enlaces de visualización se firman con la identidad de la propia función (firma por la API
de IAM, sin llaves en archivos): la cuenta de servicio necesita ``serviceAccountTokenCreator``
sobre sí misma. Fuera del alcance de las pruebas locales (requiere credenciales y un bucket
reales): se excluye de la medición de cobertura.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import google.auth
from google.api_core.exceptions import GoogleAPICallError, PreconditionFailed
from google.auth.transport.requests import Request
from google.cloud import storage

from app.domain import AlmacenNoDisponible, Enlace

logger = logging.getLogger("fn_documentos.adapters.gcs")


class AlmacenGcs:  # pragma: no cover
    def __init__(self, bucket: str, firmante_email: str | None = None) -> None:
        self._cliente = storage.Client()
        self._bucket = self._cliente.bucket(bucket)
        self._firmante = firmante_email

    async def existe(self, clave: str) -> bool:
        try:
            return await asyncio.to_thread(self._bucket.blob(clave).exists)
        except GoogleAPICallError as exc:
            raise AlmacenNoDisponible(str(exc)) from exc

    async def guardar_si_no_existe(self, clave: str, datos: bytes, content_type: str) -> bool:
        blob = self._bucket.blob(clave)

        def _subir() -> bool:
            try:
                # if_generation_match=0: solo crea si el objeto no existe. Dos generaciones
                # simultáneas no se pisan y solo una "gana" (y avisa).
                blob.upload_from_string(datos, content_type=content_type, if_generation_match=0)
            except PreconditionFailed:
                return False
            return True

        try:
            return await asyncio.to_thread(_subir)
        except GoogleAPICallError as exc:
            raise AlmacenNoDisponible(str(exc)) from exc

    async def enlace_firmado(self, clave: str, nombre_archivo: str, minutos: int) -> Enlace:
        blob = self._bucket.blob(clave)

        def _firmar() -> str:
            credenciales, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credenciales.refresh(Request())
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=minutos),
                method="GET",
                # inline: el visor del navegador o del celular lo abre en vez de descargarlo.
                response_disposition=f"inline; filename*=UTF-8''{quote(nombre_archivo)}",
                response_type="application/pdf",
                service_account_email=self._firmante or credenciales.service_account_email,
                access_token=credenciales.token,
            )

        try:
            url = await asyncio.to_thread(_firmar)
        except Exception as exc:
            logger.exception("no se pudo firmar el enlace")
            raise AlmacenNoDisponible("no se pudo firmar el enlace") from exc
        return Enlace(url, datetime.now(UTC) + timedelta(minutes=minutos))
