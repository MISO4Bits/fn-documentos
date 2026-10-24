"""Generar el documento de una póliza y entregar el enlace."""

from __future__ import annotations

import pytest

from app.adapters.memoria import AlmacenEnMemoria, PublicadorEnMemoria
from app.domain import (
    AlmacenNoDisponible,
    PublicacionFallida,
    clave_del_documento,
    parsear_datos,
)
from app.services import DocumentosService
from tests.conftest import DATOS_POLIZA

CLAVE = clave_del_documento(DATOS_POLIZA["polizaId"])


@pytest.fixture
def datos():
    return parsear_datos(DATOS_POLIZA)


async def test_el_evento_genera_el_pdf_y_avisa(servicio, almacen, publicador, datos):
    creado = await servicio.generar_por_evento(datos, {})

    assert creado
    pdf, tipo = almacen.objetos[CLAVE]
    assert pdf.startswith(b"%PDF")
    assert tipo == "application/pdf"
    [evento] = publicador.publicados
    assert evento.tipo == "DocumentoPolizaGenerado"
    assert evento.datos == {
        "polizaId": DATOS_POLIZA["polizaId"],
        "clienteId": DATOS_POLIZA["clienteId"],
        "numero": "SOL-VH-2026-K7M2Q9",
        "bucket": "bucket-de-prueba",
        "objeto": f"polizas/{DATOS_POLIZA['polizaId']}.pdf",
        "nombreArchivo": "Poliza-SOL-VH-2026-K7M2Q9.pdf",
        "contentType": "application/pdf",
    }


async def test_una_reentrega_no_regenera_pero_vuelve_a_avisar(servicio, almacen, publicador, datos):
    await servicio.generar_por_evento(datos, {})
    original = almacen.objetos[CLAVE][0]

    creado = await servicio.generar_por_evento(datos, {})

    assert not creado
    assert almacen.objetos[CLAVE][0] == original
    assert len(publicador.publicados) == 2


async def test_si_el_aviso_falla_la_siguiente_entrega_lo_recupera(almacen, datos):
    publicador = PublicadorEnMemoria(falla=True)
    servicio = DocumentosService(almacen, publicador, bucket="b")

    with pytest.raises(PublicacionFallida):
        await servicio.generar_por_evento(datos, {})
    assert CLAVE in almacen.objetos  # el PDF sí quedó

    publicador.falla = False
    await servicio.generar_por_evento(datos, {})

    assert [e.tipo for e in publicador.publicados] == ["DocumentoPolizaGenerado"]


async def test_si_el_almacen_cae_no_se_avisa(publicador, datos):
    servicio = DocumentosService(AlmacenEnMemoria(cae=True), publicador, bucket="b")

    with pytest.raises(AlmacenNoDisponible):
        await servicio.generar_por_evento(datos, {})

    assert publicador.publicados == []


async def test_el_enlace_genera_el_pdf_si_falta_y_avisa(servicio, almacen, publicador, datos):
    enlace = await servicio.enlace_de_visualizacion(datos)

    assert CLAVE in almacen.objetos
    assert CLAVE in enlace.url
    assert "Poliza-SOL-VH-2026-K7M2Q9.pdf" in enlace.url
    assert [e.tipo for e in publicador.publicados] == ["DocumentoPolizaGenerado"]


async def test_el_enlace_de_un_documento_existente_no_avisa_otra_vez(
    servicio, almacen, publicador, datos
):
    await servicio.generar_por_evento(datos, {})
    publicador.publicados.clear()

    enlace = await servicio.enlace_de_visualizacion(datos)

    assert CLAVE in enlace.url
    assert publicador.publicados == []


async def test_el_enlace_vence_en_los_minutos_configurados(almacen, publicador, datos):
    servicio = DocumentosService(almacen, publicador, bucket="b", enlace_minutos=5)
    await servicio.enlace_de_visualizacion(datos)

    enlace = await servicio.enlace_de_visualizacion(datos)

    from datetime import UTC, datetime

    minutos = (enlace.expira_en - datetime.now(UTC)).total_seconds() / 60
    assert 4 < minutos <= 5


async def test_el_generador_se_puede_cambiar(almacen, publicador, datos):
    servicio = DocumentosService(
        almacen, publicador, bucket="b", generador=lambda _datos: b"%PDF-falso"
    )

    await servicio.generar_por_evento(datos, {})

    assert almacen.objetos[CLAVE][0] == b"%PDF-falso"
