"""Lectura de los eventos, configuración y fábrica de adaptadores."""

from __future__ import annotations

import json

import pytest

from app.adapters.factory import (
    BUCKET_EN_MEMORIA,
    build_almacen,
    build_publicador,
    nombre_del_bucket,
)
from app.adapters.memoria import AlmacenEnMemoria, PublicadorQueRegistra
from app.config import Settings
from app.domain import (
    DomainEvent,
    MensajeInvalido,
    clave_del_documento,
    decodificar,
    parsear_datos,
    parsear_evento,
)
from tests.conftest import DATOS_POLIZA, EVENTO_POLIZA_EMITIDA


def test_el_evento_de_core_se_lee_completo():
    datos = parsear_evento(json.dumps(EVENTO_POLIZA_EMITIDA).encode())

    assert datos.poliza_id == DATOS_POLIZA["polizaId"]
    assert datos.asegurado.nombre == "Sofía Restrepo Uribe"
    assert [c.codigo for c in datos.coberturas] == ["VIDA", "HOGAR"]
    assert datos.tiene_hogar
    assert str(datos.prima_total_mensual) == "77374"


def test_un_evento_de_otro_tipo_no_es_para_esta_funcion():
    assert parsear_evento(json.dumps({"tipo": "EnviarCorreo", "datos": {}}).encode()) is None


@pytest.mark.parametrize("contenido", [b"no es json", b"\xff\xfe", b"[]", b'{"datos": {}}'])
def test_un_evento_ilegible_es_un_mensaje_invalido(contenido):
    with pytest.raises(MensajeInvalido):
        parsear_evento(contenido)


def test_los_campos_faltantes_se_nombran_sin_mostrar_valores():
    datos = {**DATOS_POLIZA, "asegurado": {"nombre": "Ana Secreta"}}

    with pytest.raises(MensajeInvalido) as error:
        parsear_datos(datos)

    assert "asegurado.tipoDocumento" in str(error.value)
    assert "Ana Secreta" not in str(error.value)


@pytest.mark.parametrize("poliza_id", ["../secreto", "a/b", "con espacio", ""])
def test_el_id_de_la_poliza_no_puede_salirse_de_la_carpeta_del_bucket(poliza_id):
    with pytest.raises(MensajeInvalido):
        parsear_datos({**DATOS_POLIZA, "polizaId": poliza_id})


def test_el_documento_siempre_vive_en_la_misma_ruta():
    assert clave_del_documento("abc") == "polizas/abc.pdf"


def test_base64_invalido():
    with pytest.raises(MensajeInvalido):
        decodificar("###")


def test_la_fabrica_arma_los_adaptadores_locales():
    ajustes = Settings()

    assert isinstance(build_almacen(ajustes), AlmacenEnMemoria)
    assert isinstance(build_publicador(ajustes), PublicadorQueRegistra)
    assert nombre_del_bucket(ajustes) == BUCKET_EN_MEMORIA
    assert nombre_del_bucket(Settings(almacen_bucket="solventa-polizas")) == "solventa-polizas"


@pytest.mark.parametrize(
    ("campo", "valor"), [("almacen_backend", "otro"), ("publicador_backend", "otro")]
)
def test_la_fabrica_rechaza_backends_desconocidos(campo, valor):
    ajustes = Settings(**{campo: valor})

    with pytest.raises(ValueError):
        build_almacen(ajustes)
        build_publicador(ajustes)


def test_el_publicador_local_no_registra_datos(caplog):
    import asyncio

    caplog.set_level("INFO")

    asyncio.run(
        PublicadorQueRegistra().publicar(DomainEvent("DocumentoPolizaGenerado", {"x": "secreto"}))
    )

    assert "DocumentoPolizaGenerado" in caplog.text
    assert "secreto" not in caplog.text
