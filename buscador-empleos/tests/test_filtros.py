"""Tests de los filtros de scrapers/base.py.

Casos basados en titulos REALES observados en los portales (los portales
hacen busqueda difusa y devuelven muchos falsos positivos).

Correr:  pytest
"""

from datetime import datetime, timedelta

import pytest

from scrapers.base import (
    _MESES_ES,
    Oferta,
    detectar_modalidad,
    dias_desde_texto,
    en_region_o_remoto,
    es_accesible,
    es_practica,
    es_puesto_it,
    es_senior,
    puntuar_afinidad,
)

# (titulo, deberia_pasar_el_filtro_it)
CASOS_IT = [
    # Deben PASAR (IT real)
    ("Desarrollador Web Junior Full Stack React y Node.js", True),
    ("Ingeniero/a de Desarrollo de Software", True),
    ("Software Engineer Java, .NET, Node.js o similar", True),
    ("Ingeniero de Datos y BI / Ñuñoa", True),
    ("Analista de Datos / Experiencia Clientes", True),
    ("Soporte Técnico e Informático", True),
    ("Operador/a de Informática Ripley Los Andes", True),
    ("Técnico Analista Programador Computacional, Técnico en Informática", True),
    ("Ingeniero en Sistemas, Informático, Civil Informático, Computación", True),
    ("Ingeniero de Mantención de Sistemas (Python/PHP)", True),
    ("Programadora/or conocimiento en SAP y Power BI", True),
    ("Analista de Soporte TI Apoyo $700.000", True),
    ("Desarrollador/a Power Platform Jr - Casablanca", True),
    ("Desarrollador BI - Python, ETL y Power BI", True),
    ("Desarrollador GIS", True),
    ("Desarrollador de Inteligencia Artificial y Automatización", True),
    ("Desarrollador Junior (IA & Automatización de Procesos)", True),
    ("Consultor Senior SAP Basis", True),
    ("Arquitecto de Ciberseguridad", True),
    ("Data Observability Lead", True),
    ("Analista Informática Junior | Soporte y Tecnología", True),
    # Deben RECHAZARSE (otra área o falso positivo)
    ("Ingeniero Químico", False),
    ("Ingeniero en Alimentos", False),
    ("Programador/a de Mantención", False),
    ("Programador de Mantención Equipos Mina", False),
    ("Programador/a mantenimiento planta", False),
    ("Programador(a) de Flota", False),
    ("Programador Nacional de Rutas- Quilicura", False),
    ("Programador(a) de Producción", False),
    ("Programador PLC y HMI", False),
    ("Coordinador Programación Transporte / Quilicura", False),
    ("Asistente de Programación de Mantención Industrial", False),
    ("Desarrollador de Negocios", False),
    ("Diseñador/a Gráfico/a y Desarrollador/a de Contenidos", False),
    ("Operador Sistema CCTV Full Time", False),
    ("Programadora/or Ingeniero Eléctrico, Mecánico", False),
    ("Ingeniero de Concesiones - Telecomunicaciones", False),
    ("Técnico en calibración y electrónica", False),
    ("Ingeniero de Procesos", False),
    ("Ingeniero/a de Proyectos", False),
    ("Coordinador de Licencias Médicas", False),
    ("Encargado de Mantenimiento e Infraestructura", False),
    ("Enfermera(o) Atención 24 Horas | Programa Vacaciones de Verano", False),
    ("Programa de Entrenamiento Ejecutivos Banca Personas", False),
    ("Marketplace Program Lead", False),
    ("Ingeniero/a Desarrollo logística Productividad", False),
    ("Ingeniero Desarrollo Logístico_Planificación Operacional", False),
    ("Ingeniero de Innovación y Desarrollo", False),
    ("Ingeniero de Desarrollo de Productos Junior - Reemplazo Pre y Post Natal", False),
    ("Analista de Desarrollo organizacional", False),
]


@pytest.mark.parametrize("titulo,esperado", CASOS_IT)
def test_es_puesto_it(titulo, esperado):
    assert es_puesto_it(titulo) is esperado


CASOS_PRACTICA = [
    ("Practicante en Ing. Ingeniería Industrial, Computación, Informática", True),
    ("Práctica Profesional de Informática", True),
    ("Práctica de titulación Desarrollo Web", True),
    ("Pasantía en TI", True),
    ("Software Engineering Internship", True),
    # Los trainee son empleos formales: NO se excluyen
    ("Ingeniero/a Junior (Trainee) de Automatización", False),
    ("Desarrollador Junior", False),
]


@pytest.mark.parametrize("titulo,esperado", CASOS_PRACTICA)
def test_es_practica(titulo, esperado):
    assert es_practica(titulo) is esperado


CASOS_SENIOR = [
    # Deben EXCLUIRSE (senioridad alta, no accesible con <= 1 año)
    ("Desarrollador Senior", True),
    ("Desarrollador/a Full Stack Senior", True),
    ("Ingeniero de Software Semi Senior", True),
    ("Technical Lead Senior", True),
    ("Líder Técnico Full Stack", True),
    ("Arquitecto de Ciberseguridad", True),
    ("Arquitecto Desarrollador", True),
    ("Data Observability Lead", True),
    ("Gerente de Proyectos TI", True),
    ("Jefe de Área Informática", True),
    ("Consultor Senior SAP Basis", True),
    ("Staff Engineer", True),
    ("Principal Software Engineer", True),
    ("Desarrollador SR Python", True),
    ("Technical Account Manager (Validación de Software)", True),
    # Deben PASAR (junior o sin senioridad)
    ("Desarrollador Junior", False),
    ("Desarrollador Full Stack", False),
    ("Analista de Soporte TI", False),
    ("Ingeniero de Software", False),
    ("Programador PHP", False),
]


@pytest.mark.parametrize("titulo,esperado", CASOS_SENIOR)
def test_es_senior(titulo, esperado):
    assert es_senior(titulo) is esperado


_HOY = datetime.now()
_MESES = {n: m.capitalize() for m, n in _MESES_ES.items()}


def _fecha_es(dias_atras: int) -> str:
    """Fecha en formato Chiletrabajos: '16 de Octubre de 2026'."""
    f = _HOY - timedelta(days=dias_atras)
    return f"{f.day} de {_MESES[f.month]} de {f.year}"


CASOS_FECHAS = [
    # Chiletrabajos: fecha absoluta en español
    (_fecha_es(8), 8),
    (_fecha_es(23), 23),
    # fecha futura -> dias negativos sirven
    ((_HOY + timedelta(days=10)).strftime("%Y-%m-%d"), None),
    # Relativas (Computrabajo)
    ("Hace 3 días", 3),
    ("Hace 2 semanas", 14),
    ("Desde ayer", 1),
    ("Hace 1 mes", 30),
    # Horas/minutos = publicada hoy: antes caian en el "else" de meses
    # (n*30) y el filtro de antiguedad descartaba las ofertas mas frescas
    ("Hace 2 horas", 0),
    ("Hace 45 minutos", 0),
    ("Publicada hoy", 0),
    # ISO (GetOnBoard genera YYYY-MM-DD)
    ((_HOY - timedelta(days=4)).strftime("%Y-%m-%d"), 4),
]


@pytest.mark.parametrize("texto,esperado", CASOS_FECHAS)
def test_dias_desde_texto(texto, esperado):
    resultado = dias_desde_texto(texto)
    if esperado is None:
        assert resultado is not None and resultado < 0
    else:
        assert resultado == pytest.approx(esperado, abs=1)


CASOS_EXPERIENCIA = [
    ("Buscamos desarrollador con 5 años de experiencia", False),
    ("Se requiere experiencia de 3 años", False),
    ("Sin experiencia, primer empleo bienvenido", True),
    ("Desarrollador junior recién titulado", True),
    ("", True),  # sin mencion de años -> accesible
]


@pytest.mark.parametrize("texto,esperado", CASOS_EXPERIENCIA)
def test_es_accesible(texto, esperado):
    assert es_accesible(texto) is esperado


# ---- Region derivada del config (antes "santiago" estaba hardcodeado) ----

def test_region_metropolitana():
    assert en_region_o_remoto("Santiago", "", "R.Metropolitana", False) is True
    assert en_region_o_remoto("Huechuraba, Región Metropolitana", "",
                              "R.Metropolitana", False) is True
    assert en_region_o_remoto("Viña del Mar, Valparaíso", "",
                              "R.Metropolitana", False) is False


def test_region_no_rm_santiago_ya_no_pasa():
    # Bug corregido: "santiago" pasaba siempre aunque la region fuera otra
    assert en_region_o_remoto("Santiago", "", "Valparaíso", False) is False
    assert en_region_o_remoto("Viña del Mar", "", "Valparaíso", False) is True
    assert en_region_o_remoto("Concepción", "", "Biobío", False) is True


def test_region_remoto_sigue_pasando():
    assert en_region_o_remoto("Temuco", "Remoto", "R.Metropolitana", True) is True
    assert en_region_o_remoto("Temuco", "Remoto", "R.Metropolitana", False) is False


# ---- Modalidad detectada del texto ----

CASOS_MODALIDAD = [
    ("Desarrollador 100% remoto", "Remoto"),
    ("teletrabajo desde cualquier ciudad", "Remoto"),
    ("Home office con reuniones semanales", "Remoto"),
    ("Trabajo híbrido en Santiago", "Híbrido"),
    ("Presencial en oficina", ""),
    ("", ""),
]


@pytest.mark.parametrize("texto,esperado", CASOS_MODALIDAD)
def test_detectar_modalidad(texto, esperado):
    assert detectar_modalidad(texto) == esperado


def test_puntuar_afinidad():
    stack = ["python", "react", "sql"]
    oferta = Oferta(titulo="Desarrollador Python", texto_ranking="usamos react y docker")
    puntaje, afinidad = puntuar_afinidad(oferta, stack)
    assert puntaje == 2
    assert "python" in afinidad and "react" in afinidad and "sql" not in afinidad


def test_puntuar_afinidad_sin_coincidencias():
    oferta = Oferta(titulo="Analista de Datos", texto_ranking="excel y tableau")
    puntaje, afinidad = puntuar_afinidad(oferta, ["python", "react"])
    assert puntaje == 0 and afinidad == ""
