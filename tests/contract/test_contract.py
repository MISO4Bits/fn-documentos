"""La implementación cumple ``openapi/openapi.yaml`` y entiende el evento que publica Core."""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator

from app.domain import parsear_evento
from tests.conftest import sobre_push

_METODOS = {"get", "post", "put", "patch", "delete"}


def _validar(spec: dict, esquema: str, instancia) -> None:
    schema = {"$ref": f"#/components/schemas/{esquema}", "components": spec["components"]}
    errores = sorted(Draft202012Validator(schema).iter_errors(instancia), key=str)
    assert not errores, f"{esquema}: {[e.message for e in errores]}"


def test_las_operaciones_del_contrato_son_las_de_la_aplicacion(app, openapi_spec):
    contrato = {
        (m.upper(), ruta)
        for ruta, item in openapi_spec["paths"].items()
        for m in item
        if m.lower() in _METODOS
    }
    codigo = {
        (m.upper(), ruta)
        for ruta, item in app.openapi()["paths"].items()
        for m in item
        if m.lower() in _METODOS
    }
    assert contrato == codigo


def test_el_ejemplo_del_evento_cumple_su_esquema_y_la_funcion_lo_entiende(openapi_spec):
    ejemplo = openapi_spec["components"]["schemas"]["EventoPolizaEmitida"]["examples"][0]

    _validar(openapi_spec, "EventoPolizaEmitida", ejemplo)
    datos = parsear_evento(json.dumps(ejemplo).encode())
    assert datos is not None
    assert datos.numero == ejemplo["datos"]["numero"]


def test_el_sobre_de_pubsub_cumple_el_esquema(openapi_spec):
    ejemplo = openapi_spec["components"]["schemas"]["EventoPolizaEmitida"]["examples"][0]

    _validar(openapi_spec, "SobrePush", sobre_push(ejemplo))


async def test_las_respuestas_cumplen_el_contrato(client, openapi_spec, publicador):
    ejemplo = openapi_spec["components"]["schemas"]["EventoPolizaEmitida"]["examples"][0]

    push = await client.post("/", json=sobre_push(ejemplo))
    enlace = await client.post("/v1/documentos/polizas/enlace", json=ejemplo["datos"])
    invalido = await client.post("/v1/documentos/polizas/enlace", json={})

    assert str(push.status_code) in openapi_spec["paths"]["/"]["post"]["responses"]
    assert enlace.status_code == 200
    _validar(openapi_spec, "Enlace", enlace.json())
    assert invalido.status_code == 400
    _validar(openapi_spec, "Problema", invalido.json())
    # El evento que se publica cumple el contrato que Core consume.
    for evento in publicador.publicados:
        _validar(
            openapi_spec,
            "DocumentoPolizaGenerado",
            {"tipo": evento.tipo, "id": evento.id, "datos": evento.datos},
        )
    assert publicador.publicados
