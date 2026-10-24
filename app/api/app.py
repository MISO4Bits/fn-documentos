from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response

from app.adapters.factory import build_almacen, build_publicador, nombre_del_bucket
from app.api.routes import router
from app.config import Settings, get_settings
from app.logging_utils import SinRuidoDeHealthCheck
from app.services import DocumentosService
from app.telemetry import setup_telemetry, shutdown_telemetry

SPEC_PATH = Path(__file__).resolve().parents[2] / "openapi" / "openapi.yaml"
logger = logging.getLogger("fn_documentos.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("uvicorn.access").addFilter(SinRuidoDeHealthCheck())

    telemetry = setup_telemetry(settings)
    service = DocumentosService(
        build_almacen(settings),
        build_publicador(settings),
        bucket=nombre_del_bucket(settings),
        enlace_minutos=settings.enlace_minutos,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        shutdown_telemetry(telemetry)

    app = FastAPI(title="fn-documentos", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.service = service
    app.state.telemetry = telemetry

    @app.exception_handler(RequestValidationError)
    async def _solicitud_invalida(request: Request, exc: RequestValidationError) -> Response:
        if request.url.path == "/":
            # Un sobre que no es de Pub/Sub no se arregla reintentando: se confirma y se anota.
            logger.error("solicitud descartada: no es un sobre de Pub/Sub")
            return Response(status_code=204)
        campos = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
        cuerpo = json.dumps(
            {
                "type": "about:blank",
                "title": "Solicitud inválida",
                "status": 400,
                "detail": "La solicitud no cumple el esquema",
                "errores": [{"campo": c} for c in campos],
            }
        )
        return Response(cuerpo, status_code=400, media_type="application/problem+json")

    app.include_router(router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "service": settings.service_name}

    if SPEC_PATH.exists():

        @app.get("/openapi.yaml", include_in_schema=False)
        async def openapi_yaml() -> FileResponse:
            return FileResponse(SPEC_PATH, media_type="application/yaml")

    return app
