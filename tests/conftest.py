from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient

from app.adapters.memoria import AlmacenEnMemoria, PublicadorEnMemoria
from app.api.app import create_app
from app.config import Settings
from app.services import DocumentosService

SPEC_PATH = Path(__file__).resolve().parents[1] / "openapi" / "openapi.yaml"

DATOS_POLIZA = {
    "polizaId": "7c0f2a52-3b6f-4a0e-9e7e-2f6c9d1a8b11",
    "clienteId": "7b1d3c2e-0f4a-4b8e-9c55-2a1e6d9f0b34",
    "numero": "SOL-VH-2026-K7M2Q9",
    "emitidaEn": "2026-10-22T15:00:00Z",
    "vigencia": {"desde": "2026-10-22T15:00:00Z", "hasta": "2027-10-22T15:00:00Z"},
    "coberturas": [
        {
            "codigo": "VIDA",
            "obligatoria": True,
            "sumaAsegurada": 320000000,
            "primaNeta": 49100,
            "iva": 0,
            "primaTotal": 49100,
        },
        {
            "codigo": "HOGAR",
            "obligatoria": False,
            "sumaAsegurada": 240000000,
            "primaNeta": 23760,
            "iva": 4514,
            "primaTotal": 28274,
        },
    ],
    "primaTotalMensual": 77374,
    "moneda": "COP",
    "datosCredito": {
        "entidadAcreedora": "Bancolombia S.A.",
        "valorCredito": 350000000,
        "plazoRestanteMeses": 240,
        "saldoInsoluto": 320000000,
    },
    "asegurado": {
        "nombre": "Sofía Restrepo Uribe",
        "tipoDocumento": "CC",
        "numeroDocumento": "1017654456",
        "email": "sofia@example.com",
    },
}

EVENTO_POLIZA_EMITIDA = {
    "tipo": "PolizaEmitida",
    "id": "evento-1",
    "ocurridoEn": "2026-10-22T15:00:00Z",
    "datos": DATOS_POLIZA,
}


def sobre_push(evento: dict | bytes | str, *, atributos: dict | None = None) -> dict:
    """Sobre que Pub/Sub entrega a una suscripción push."""
    if isinstance(evento, dict):
        evento = json.dumps(evento)
    if isinstance(evento, str):
        evento = evento.encode()
    return {
        "message": {
            "data": base64.b64encode(evento).decode(),
            "attributes": atributos or {"tipo": "PolizaEmitida"},
            "messageId": "mensaje-1",
        },
        "subscription": "projects/p/subscriptions/s",
    }


@pytest.fixture(scope="session")
def openapi_spec() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def almacen() -> AlmacenEnMemoria:
    return AlmacenEnMemoria()


@pytest.fixture
def publicador() -> PublicadorEnMemoria:
    return PublicadorEnMemoria()


@pytest.fixture
def servicio(almacen, publicador) -> DocumentosService:
    return DocumentosService(almacen, publicador, bucket="bucket-de-prueba", enlace_minutos=15)


@pytest.fixture
def app(servicio):
    application = create_app(Settings())
    application.state.service = servicio
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
