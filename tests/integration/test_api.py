"""La API completa: la suscripción push y el enlace que pide Core."""

from __future__ import annotations

import pytest

from app.domain import clave_del_documento
from tests.conftest import DATOS_POLIZA, EVENTO_POLIZA_EMITIDA, sobre_push

CLAVE = clave_del_documento(DATOS_POLIZA["polizaId"])


async def test_una_poliza_emitida_genera_el_pdf_y_se_confirma(client, almacen, publicador):
    respuesta = await client.post("/", json=sobre_push(EVENTO_POLIZA_EMITIDA))

    assert respuesta.status_code == 204
    assert almacen.objetos[CLAVE][0].startswith(b"%PDF")
    assert [e.tipo for e in publicador.publicados] == ["DocumentoPolizaGenerado"]


async def test_un_evento_de_otro_tipo_se_ignora(client, almacen, publicador):
    otro = {"tipo": "EnviarCorreo", "datos": {"destinatario": "x@y.co"}}

    respuesta = await client.post("/", json=sobre_push(otro, atributos={"tipo": "EnviarCorreo"}))

    assert respuesta.status_code == 204
    assert almacen.objetos == {}
    assert publicador.publicados == []


@pytest.mark.parametrize(
    "contenido",
    [
        "esto no es json",
        {"tipo": "PolizaEmitida", "datos": {"polizaId": "x"}},  # faltan campos
        {"sin": "tipo"},
    ],
)
async def test_un_mensaje_sin_arreglo_se_descarta_con_204(client, almacen, contenido):
    respuesta = await client.post("/", json=sobre_push(contenido))

    assert respuesta.status_code == 204
    assert almacen.objetos == {}


async def test_un_base64_invalido_se_descarta(client):
    sobre = sobre_push(EVENTO_POLIZA_EMITIDA)
    sobre["message"]["data"] = "***no-es-base64***"

    assert (await client.post("/", json=sobre)).status_code == 204


async def test_algo_que_no_es_un_sobre_de_pubsub_se_descarta(client):
    assert (await client.post("/", json={"hola": "mundo"})).status_code == 204


async def test_si_el_almacen_cae_se_devuelve_503_para_que_pubsub_reentregue(
    client, almacen, publicador
):
    almacen.cae = True

    respuesta = await client.post("/", json=sobre_push(EVENTO_POLIZA_EMITIDA))

    assert respuesta.status_code == 503
    assert publicador.publicados == []


async def test_si_pubsub_falla_se_devuelve_503(client, publicador):
    publicador.falla = True

    assert (await client.post("/", json=sobre_push(EVENTO_POLIZA_EMITIDA))).status_code == 503


async def test_el_enlace_responde_con_la_url_y_su_vencimiento(client, almacen):
    respuesta = await client.post("/v1/documentos/polizas/enlace", json=DATOS_POLIZA)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "LISTO"
    assert CLAVE in cuerpo["url"]
    assert cuerpo["expiraEn"]
    assert CLAVE in almacen.objetos


async def test_datos_invalidos_en_el_enlace_son_400_con_el_campo(client):
    incompleto = {**DATOS_POLIZA}
    del incompleto["asegurado"]

    respuesta = await client.post("/v1/documentos/polizas/enlace", json=incompleto)

    assert respuesta.status_code == 400
    assert respuesta.headers["content-type"].startswith("application/problem+json")
    assert {"campo": "asegurado"} in respuesta.json()["errores"]


async def test_si_el_almacen_cae_el_enlace_es_503(client, almacen):
    almacen.cae = True

    respuesta = await client.post("/v1/documentos/polizas/enlace", json=DATOS_POLIZA)

    assert respuesta.status_code == 503
    assert respuesta.headers["content-type"].startswith("application/problem+json")


async def test_health_y_contrato(client):
    assert (await client.get("/health")).json() == {"status": "ok", "service": "fn-documentos"}
    assert (await client.get("/openapi.yaml")).status_code == 200
