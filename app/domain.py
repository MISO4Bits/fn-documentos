"""Modelo de dominio: los datos de una póliza emitida y los errores de la generación.

La función no decide nada de negocio: recibe la póliza ya emitida por CoreTransaccional
(evento ``PolizaEmitida``) y la convierte en un documento.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

EVENTO_POLIZA_EMITIDA = "PolizaEmitida"
EVENTO_DOCUMENTO_GENERADO = "DocumentoPolizaGenerado"

CONTENT_TYPE_PDF = "application/pdf"


class MensajeInvalido(Exception):
    """El mensaje o la solicitud no tienen la forma esperada. Reintentar no lo arregla."""


class AlmacenNoDisponible(Exception):
    """No se pudo leer o escribir en el almacén de documentos. Conviene reintentar."""


class PublicacionFallida(Exception):
    """No se pudo publicar el evento. Conviene reintentar."""


class _Modelo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class Cobertura(_Modelo):
    codigo: str
    obligatoria: bool = False
    suma_asegurada: Decimal
    prima_neta: Decimal
    iva: Decimal
    prima_total: Decimal


class DatosCredito(_Modelo):
    entidad_acreedora: str = Field(min_length=1, max_length=120)
    valor_credito: Decimal | None = None
    plazo_restante_meses: int | None = None
    saldo_insoluto: Decimal | None = None


class Vigencia(_Modelo):
    desde: datetime
    hasta: datetime


class Asegurado(_Modelo):
    nombre: str = Field(min_length=1, max_length=200)
    tipo_documento: str = Field(min_length=1, max_length=10)
    numero_documento: str = Field(min_length=1, max_length=30)
    email: str | None = None


class DatosPoliza(_Modelo):
    """``datos`` del evento ``PolizaEmitida`` (contrato con CoreTransaccional)."""

    poliza_id: str = Field(min_length=1, max_length=64, pattern=r"^[0-9A-Za-z_-]+$")
    cliente_id: str | None = Field(default=None, max_length=64)
    numero: str = Field(min_length=1, max_length=40)
    emitida_en: datetime
    vigencia: Vigencia
    coberturas: list[Cobertura] = Field(min_length=1)
    prima_total_mensual: Decimal
    datos_credito: DatosCredito
    asegurado: Asegurado

    @property
    def tiene_hogar(self) -> bool:
        return any(c.codigo == "HOGAR" for c in self.coberturas)


class _Evento(_Modelo):
    tipo: str
    id: str | None = None
    datos: dict


@dataclass(frozen=True)
class Enlace:
    url: str
    expira_en: datetime


@dataclass(frozen=True)
class DomainEvent:
    tipo: str
    datos: dict
    id: str = field(default_factory=lambda: str(uuid4()))
    ocurrido_en: datetime = field(default_factory=lambda: datetime.now(UTC))


def decodificar(data_base64: str) -> bytes:
    try:
        return base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MensajeInvalido("El cuerpo del mensaje no es base64 válido") from exc


def parsear_datos(datos: dict) -> DatosPoliza:
    """Valida la póliza. El motivo no incluye valores: traen datos personales."""
    try:
        return DatosPoliza.model_validate(datos)
    except ValidationError as exc:
        campos = ", ".join(sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()}))
        raise MensajeInvalido(f"La póliza no es válida ({campos})") from None


def parsear_evento(contenido: bytes) -> DatosPoliza | None:
    """Convierte el cuerpo del mensaje en los datos de la póliza.

    Devuelve ``None`` si el evento es de otro tipo (no es para esta función).
    """
    try:
        evento = _Evento.model_validate(json.loads(contenido))
    except (ValueError, UnicodeDecodeError):
        raise MensajeInvalido("El evento no es válido (no es JSON o le faltan campos)") from None
    if evento.tipo != EVENTO_POLIZA_EMITIDA:
        return None
    return parsear_datos(evento.datos)


def clave_del_documento(poliza_id: str) -> str:
    """Dónde vive el PDF de una póliza en el bucket. Es determinista: el mismo ``polizaId``
    siempre da el mismo objeto, así que generar dos veces no duplica nada."""
    return f"polizas/{poliza_id}.pdf"
