"""Genera el PDF de la póliza.

Mismo branding que los correos de Solventa: logo, Plus Jakarta Sans y la paleta de la marca.
El diseño es de una sola página A4: encabezado, datos del asegurado, coberturas con su precio,
vigencia y pago, beneficiario oneroso y la cláusula para el banco.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from app.domain import DatosPoliza

ASSETS = Path(__file__).resolve().parent / "assets"

TEAL = HexColor("#006971")
INK = HexColor("#161D1D")
BODY = HexColor("#3F484A")
MUTED = HexColor("#6F797A")
LINE = HexColor("#DDE4E5")

REGULAR, MEDIO, SEMI, NEGRITA = "PJS-400", "PJS-500", "PJS-600", "PJS-700"

# Colombia no tiene horario de verano: un desfase fijo basta.
BOGOTA = timezone(timedelta(hours=-5))

_MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

_ETIQUETA_DOCUMENTO = {
    "CC": ("Cédula", "C.C."),
    "CE": ("Cédula de extranjería", "C.E."),
    "PA": ("Pasaporte", "Pasaporte"),
    "NIT": ("NIT", "NIT"),
}

# Medidas en puntos (A4 = 595 x 842). Los márgenes y las columnas siguen el diseño de la póliza.
MARGEN = 42
ANCHO, ALTO = A4
DERECHA = ANCHO - MARGEN
COLUMNA_VALOR = MARGEN + 200  # donde empiezan los valores de las filas "etiqueta / valor"
COLUMNA_ASEGURADO = DERECHA - 135  # borde derecho de "Valor asegurado"
PASO_FILA = 20.5


def formato_pesos(valor: Decimal | int | float) -> str:
    """``49100`` → ``$49.100``. Sin decimales: los precios de la póliza son pesos enteros."""
    entero = int(Decimal(str(valor)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return f"${entero:,}".replace(",", ".")


def en_bogota(fecha: datetime) -> datetime:
    return fecha.astimezone(BOGOTA)


def fecha_larga(fecha: datetime) -> str:
    """``22 de octubre de 2026``."""
    f = en_bogota(fecha)
    return f"{f.day} de {_MESES[f.month - 1]} de {f.year}"


def fecha_corta(fecha: datetime) -> str:
    """``22 oct 2026``."""
    f = en_bogota(fecha)
    return f"{f.day} {_MESES[f.month - 1][:3]} {f.year}"


def enmascarar_documento(tipo: str, numero: str) -> str:
    """``C.C. 1.032.xxx.789``: el documento no viaja completo en un PDF que se comparte."""
    prefijo = _ETIQUETA_DOCUMENTO.get(tipo, (tipo, tipo))[1]
    if numero.isdigit():
        grupos: list[str] = []
        resto = numero
        while resto:
            grupos.insert(0, resto[-3:])
            resto = resto[:-3]
        if len(grupos) >= 2:
            # El segundo grupo desde la derecha: 1.032.456.789 → 1.032.xxx.789
            grupos[-2] = "xxx"
        else:
            grupos = [numero[:1] + "xxx" if len(numero) > 1 else numero]
        return f"{prefijo} {'.'.join(grupos)}"
    if len(numero) <= 4:
        return f"{prefijo} {numero}"
    return f"{prefijo} {numero[:2]}{'x' * (len(numero) - 4)}{numero[-2:]}"


def etiqueta_documento(tipo: str) -> str:
    return _ETIQUETA_DOCUMENTO.get(tipo, (tipo, tipo))[0]


def titulo_del_documento(datos: DatosPoliza) -> str:
    return "Seguro de vida para tu crédito" + (" y Tu casa" if datos.tiene_hogar else "")


@lru_cache(maxsize=1)
def _registrar_fuentes() -> None:
    for nombre, peso in ((REGULAR, "400"), (MEDIO, "500"), (SEMI, "600"), (NEGRITA, "700")):
        archivo = ASSETS / "fonts" / f"plus-jakarta-sans-{peso}.ttf"
        pdfmetrics.registerFont(TTFont(nombre, str(archivo)))


def _texto(lienzo: Canvas, x: float, y: float, texto: str, fuente: str, tam: float, color) -> None:
    lienzo.setFillColor(color)
    lienzo.setFont(fuente, tam)
    lienzo.drawString(x, y, texto)


def _derecha(
    lienzo: Canvas, x: float, y: float, texto: str, fuente: str, tam: float, color
) -> None:
    lienzo.setFillColor(color)
    lienzo.setFont(fuente, tam)
    lienzo.drawRightString(x, y, texto)


def _rotulo(lienzo: Canvas, x: float, y: float, texto: str, *, derecha: bool = False) -> None:
    """Texto en mayúsculas con letras separadas, como los rótulos de sección del diseño."""
    # El espaciado entre letras queda en el estado gráfico: se aísla para que no ensanche el
    # resto del texto.
    lienzo.saveState()
    t = lienzo.beginText()
    t.setFont(SEMI, 8.2)
    t.setFillColor(MUTED)
    t.setCharSpace(0.35)
    if derecha:
        ancho = pdfmetrics.stringWidth(texto, SEMI, 8.2) + 0.35 * len(texto)
        x -= ancho
    t.setTextOrigin(x, y)
    t.textOut(texto)
    lienzo.drawText(t)
    lienzo.restoreState()


def _linea(lienzo: Canvas, y: float) -> None:
    lienzo.setStrokeColor(LINE)
    lienzo.setLineWidth(0.8)
    lienzo.line(MARGEN, y, DERECHA, y)


class _Hoja:
    """Lleva la posición vertical (desde arriba) mientras se va dibujando."""

    def __init__(self, lienzo: Canvas) -> None:
        self.lienzo = lienzo
        self.arriba = 0.0

    @property
    def y(self) -> float:
        return ALTO - self.arriba

    def bajar(self, puntos: float) -> None:
        self.arriba += puntos

    def seccion(self, titulo: str) -> None:
        _rotulo(self.lienzo, MARGEN, self.y, titulo)
        self.bajar(PASO_FILA + 1)

    def fila(self, etiqueta: str, valor: str) -> None:
        """Fila "etiqueta / valor"; un valor largo se parte en varias líneas."""
        _texto(self.lienzo, MARGEN, self.y, etiqueta, REGULAR, 10.8, MUTED)
        lineas = simpleSplit(valor, SEMI, 10.8, DERECHA - COLUMNA_VALOR) or [""]
        for i, linea in enumerate(lineas):
            _texto(self.lienzo, COLUMNA_VALOR, self.y, linea, SEMI, 10.8, INK)
            self.bajar(PASO_FILA if i == len(lineas) - 1 else 14)


def generar_pdf(datos: DatosPoliza) -> bytes:
    """El documento de la póliza, listo para guardar. Mismo dato, mismo PDF (sin fecha de
    creación variable): generar dos veces no cambia el archivo."""
    _registrar_fuentes()
    salida = io.BytesIO()
    lienzo = Canvas(salida, pagesize=A4, invariant=1)
    lienzo.setTitle(f"Póliza {datos.numero}")
    lienzo.setAuthor("Solventa")
    lienzo.setSubject("Póliza de seguro de vida")
    hoja = _Hoja(lienzo)

    # --- encabezado: logo a la izquierda y el rótulo a la derecha ---
    logo = ImageReader(str(ASSETS / "logo_solventa.png"))
    ancho_logo = 98.0
    alto_logo = ancho_logo * 320 / 1261
    lienzo.drawImage(
        logo, MARGEN, ALTO - 44 - alto_logo, width=ancho_logo, height=alto_logo, mask="auto"
    )
    _rotulo(lienzo, DERECHA, ALTO - 44 - alto_logo / 2 - 2, "PÓLIZA DE SEGURO", derecha=True)
    hoja.arriba = 44 + alto_logo + 40

    # --- título ---
    _texto(lienzo, MARGEN, hoja.y, titulo_del_documento(datos), NEGRITA, 19, INK)
    hoja.bajar(19)
    subtitulo = f"Póliza N.º {datos.numero} · Expedida el {fecha_larga(datos.emitida_en)}"
    _texto(lienzo, MARGEN, hoja.y, subtitulo, REGULAR, 11, MUTED)
    hoja.bajar(18)
    _linea(lienzo, hoja.y)
    hoja.bajar(28)

    # --- tomador y asegurado ---
    hoja.seccion("TOMADOR Y ASEGURADO")
    hoja.fila("Nombre", datos.asegurado.nombre)
    hoja.fila(
        etiqueta_documento(datos.asegurado.tipo_documento),
        enmascarar_documento(datos.asegurado.tipo_documento, datos.asegurado.numero_documento),
    )
    hoja.bajar(7)

    # --- coberturas ---
    hoja.seccion("COBERTURAS")
    _texto(lienzo, MARGEN, hoja.y, "Cobertura", REGULAR, 10.8, MUTED)
    _derecha(lienzo, COLUMNA_ASEGURADO, hoja.y, "Valor asegurado", REGULAR, 10.8, MUTED)
    _derecha(lienzo, DERECHA, hoja.y, "Prima mensual", REGULAR, 10.8, MUTED)
    hoja.bajar(PASO_FILA)
    iva_hogar = Decimal(0)
    for cobertura in datos.coberturas:
        nombre = "Tu casa" if cobertura.codigo == "HOGAR" else "Vida para tu crédito"
        _texto(lienzo, MARGEN, hoja.y, nombre, REGULAR, 10.8, INK)
        _derecha(
            lienzo,
            COLUMNA_ASEGURADO,
            hoja.y,
            formato_pesos(cobertura.suma_asegurada),
            REGULAR,
            10.8,
            INK,
        )
        _derecha(lienzo, DERECHA, hoja.y, formato_pesos(cobertura.prima_neta), REGULAR, 10.8, INK)
        hoja.bajar(PASO_FILA)
        if cobertura.codigo == "HOGAR":
            iva_hogar = cobertura.iva
    if iva_hogar > 0:
        _texto(lienzo, MARGEN, hoja.y, "IVA de Tu casa", REGULAR, 10.8, INK)
        _derecha(lienzo, DERECHA, hoja.y, formato_pesos(iva_hogar), REGULAR, 10.8, INK)
        hoja.bajar(PASO_FILA - 6)
    else:
        hoja.bajar(-6)
    _linea(lienzo, hoja.y)
    hoja.bajar(14)
    _texto(lienzo, MARGEN, hoja.y, "Total al mes", NEGRITA, 10.8, INK)
    _derecha(lienzo, DERECHA, hoja.y, formato_pesos(datos.prima_total_mensual), NEGRITA, 10.8, INK)
    hoja.bajar(30)

    # --- vigencia y pago ---
    hoja.seccion("VIGENCIA Y PAGO")
    hoja.fila(
        "Vigencia",
        f"{fecha_corta(datos.vigencia.desde)} al {fecha_corta(datos.vigencia.hasta)}",
    )
    hoja.fila("Renovación", "Automática, cada año")
    entidad = datos.datos_credito.entidad_acreedora
    # "S.A." ya trae su punto: no se duplica al cerrar la frase.
    cierre = "" if entidad.endswith(".") else "."
    hoja.fila("Forma de pago", f"Con la cuota de tu crédito. La cobra {entidad}{cierre}")
    hoja.bajar(8)

    # --- beneficiario oneroso ---
    hoja.seccion("BENEFICIARIO ONEROSO")
    hoja.fila("Entidad", entidad)
    hoja.fila("Hasta", "El saldo insoluto de la deuda")
    hoja.bajar(7)

    # --- cláusula para el banco ---
    hoja.seccion("CLÁUSULA PARA EL BANCO")
    clausula = (
        f"Esta póliza no se revoca ni se modifica sin avisar a {entidad} "
        "con 30 días de anticipación."
    )
    for linea in simpleSplit(clausula, REGULAR, 11.2, DERECHA - MARGEN):
        _texto(lienzo, MARGEN, hoja.y, linea, REGULAR, 11.2, INK)
        hoja.bajar(15)
    hoja.bajar(10)

    # --- pie ---
    _linea(lienzo, hoja.y)
    hoja.bajar(18)
    _texto(
        lienzo,
        MARGEN,
        hoja.y,
        "Documento generado por Solventa S.A. Las condiciones completas están en tu cuenta.",
        REGULAR,
        9,
        MUTED,
    )

    lienzo.showPage()
    lienzo.save()
    return salida.getvalue()
