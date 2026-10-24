"""El PDF de la póliza: formato de los datos y contenido del documento."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pymupdf
import pytest

from app.domain import parsear_datos
from app.pdf import (
    enmascarar_documento,
    etiqueta_documento,
    fecha_corta,
    fecha_larga,
    formato_pesos,
    generar_pdf,
    titulo_del_documento,
)
from tests.conftest import DATOS_POLIZA


def _datos(**cambios):
    return parsear_datos({**DATOS_POLIZA, **cambios})


def _texto(pdf: bytes) -> str:
    documento = pymupdf.open(stream=pdf, filetype="pdf")
    return "\n".join(pagina.get_text() for pagina in documento)


# --- formato ---


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (49100, "$49.100"),
        (Decimal("77374"), "$77.374"),
        (320000000, "$320.000.000"),
        (0, "$0"),
        (Decimal("1234.5"), "$1.235"),
        (999, "$999"),
    ],
)
def test_los_pesos_llevan_punto_de_miles_y_sin_decimales(valor, esperado):
    assert formato_pesos(valor) == esperado


def test_las_fechas_se_muestran_en_la_hora_de_colombia():
    # 02:00 UTC del 23 es todavía el 22 en Bogotá.
    fecha = datetime(2026, 10, 23, 2, 0, tzinfo=UTC)

    assert fecha_larga(fecha) == "22 de octubre de 2026"
    assert fecha_corta(fecha) == "22 oct 2026"


@pytest.mark.parametrize(
    ("tipo", "numero", "esperado"),
    [
        ("CC", "1017654456", "C.C. 1.017.xxx.456"),
        ("CC", "1032456789", "C.C. 1.032.xxx.789"),
        ("CC", "52123456", "C.C. 52.xxx.456"),
        ("CC", "1234567", "C.C. 1.xxx.567"),
        ("CC", "123", "C.C. 1xxx"),
        ("CE", "987654", "C.E. xxx.654"),
        ("PA", "AB123456", "Pasaporte ABxxxx56"),
        ("PA", "AB12", "Pasaporte AB12"),
        ("OTRO", "1017654456", "OTRO 1.017.xxx.456"),
    ],
)
def test_el_documento_no_sale_completo(tipo, numero, esperado):
    assert enmascarar_documento(tipo, numero) == esperado


def test_la_etiqueta_del_documento_segun_su_tipo():
    assert etiqueta_documento("CC") == "Cédula"
    assert etiqueta_documento("PA") == "Pasaporte"
    assert etiqueta_documento("XX") == "XX"


def test_el_titulo_menciona_la_casa_solo_si_hay_cobertura_de_hogar():
    con_hogar = _datos()
    solo_vida = _datos(coberturas=DATOS_POLIZA["coberturas"][:1])

    assert titulo_del_documento(con_hogar) == "Seguro de vida para tu crédito y Tu casa"
    assert titulo_del_documento(solo_vida) == "Seguro de vida para tu crédito"


# --- el documento ---


def test_el_pdf_es_de_una_sola_pagina_a4():
    pdf = generar_pdf(_datos())

    documento = pymupdf.open(stream=pdf, filetype="pdf")
    assert pdf.startswith(b"%PDF")
    assert documento.page_count == 1
    assert (round(documento[0].rect.width), round(documento[0].rect.height)) == (595, 842)
    assert documento.metadata["title"] == "Póliza SOL-VH-2026-K7M2Q9"
    assert documento.metadata["author"] == "Solventa"


def test_el_pdf_trae_todos_los_datos_de_la_poliza():
    texto = _texto(generar_pdf(_datos()))

    for esperado in (
        "PÓLIZA DE SEGURO",
        "Seguro de vida para tu crédito y Tu casa",
        "Póliza N.º SOL-VH-2026-K7M2Q9",
        "Expedida el 22 de octubre de 2026",
        "Sofía Restrepo Uribe",
        "C.C. 1.017.xxx.456",
        "Vida para tu crédito",
        "$320.000.000",
        "$49.100",
        "Tu casa",
        "$240.000.000",
        "$23.760",
        "IVA de Tu casa",
        "$4.514",
        "Total al mes",
        "$77.374",
        "22 oct 2026 al 22 oct 2027",
        "Con la cuota de tu crédito. La cobra Bancolombia S.A.",
        "BENEFICIARIO ONEROSO",
        "El saldo insoluto de la deuda",
        "no se revoca ni se modifica sin avisar a Bancolombia S.A. con 30 días de anticipación",
        "Documento generado por Solventa S.A.",
    ):
        assert esperado in texto, esperado


def test_el_pdf_no_contiene_el_documento_completo_ni_el_correo():
    texto = _texto(generar_pdf(_datos()))

    assert "1017654456" not in texto
    assert "1.017.654.456" not in texto
    assert "sofia@example.com" not in texto


def test_sin_hogar_no_hay_fila_de_casa_ni_de_iva():
    solo_vida = _datos(coberturas=DATOS_POLIZA["coberturas"][:1], primaTotalMensual=49100)

    texto = _texto(generar_pdf(solo_vida))

    assert "Seguro de vida para tu crédito\n" in texto
    assert "Tu casa" not in texto
    assert "IVA" not in texto
    assert "$49.100" in texto


def test_una_entidad_sin_punto_final_cierra_la_frase_con_punto():
    datos = _datos(datosCredito={"entidadAcreedora": "Davivienda"})

    texto = _texto(generar_pdf(datos))

    assert "La cobra Davivienda." in texto
    assert "Davivienda.." not in texto


def test_un_nombre_muy_largo_no_rompe_el_documento():
    datos = _datos(
        asegurado={**DATOS_POLIZA["asegurado"], "nombre": "María de los Ángeles " * 8},
        datosCredito={"entidadAcreedora": "Banco Caja Social " * 4},
    )

    pdf = generar_pdf(datos)

    assert pymupdf.open(stream=pdf, filetype="pdf").page_count == 1


def test_el_mismo_dato_produce_el_mismo_pdf():
    assert generar_pdf(_datos()) == generar_pdf(_datos())


def test_las_fuentes_de_la_marca_van_incrustadas():
    documento = pymupdf.open(stream=generar_pdf(_datos()), filetype="pdf")

    fuentes = {f[3] for f in documento[0].get_fonts()}

    assert any("PlusJakartaSans" in nombre.replace("-", "").replace(" ", "") for nombre in fuentes)
