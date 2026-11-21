"""Tests de las mejoras: dedup tolerante, empresas excluidas, sueldo
minimo, ranking ponderado e historial con fecha/purga."""

import json
from datetime import datetime, timedelta

import pytest

import scrapers.base as base
from scrapers.base import (
    Oferta,
    cargar_historial,
    es_empresa_excluida,
    normalizar_clave,
    pasa_sueldo_minimo,
    puntuar_afinidad,
)


# ---- Dedup tolerante ----

CASOS_MISMA_CLAVE = [
    ("Desarrollador/a Full Stack", "Acme SpA", "Desarrollador Fullstack", "acme spa"),
    ("Programador Jr - Web", "Beta", "Programador Junior - Web", "BETA"),
    ("Ingeniero(a) de Software", "X", "Ingeniero de Software", "x"),
    ("Analista de Sistemas", "Empresa Tecnológica", "Analista de sistemas", "empresa tecnologica"),
]


@pytest.mark.parametrize("t1, e1, t2, e2", CASOS_MISMA_CLAVE)
def test_dedup_tolerante_misma_oferta(t1, e1, t2, e2):
    assert normalizar_clave(t1, e1) == normalizar_clave(t2, e2)


def test_dedup_no_fusiona_roles_distintos():
    a = normalizar_clave("Desarrollador Python", "Acme")
    b = normalizar_clave("Desarrollador Java", "Acme")
    assert a != b


# ---- Empresas excluidas ----

def test_es_empresa_excluida(monkeypatch):
    monkeypatch.setattr(base, "_CONFIG_CACHE",
                        {"empresas_excluidas": ["Consultora Spam", "Acme"]})
    assert es_empresa_excluida("Consultora Spam Ltda") is True
    assert es_empresa_excluida("ACME SpA") is True
    assert es_empresa_excluida("Empresa Buena") is False


def test_es_empresa_excluida_lista_vacia(monkeypatch):
    monkeypatch.setattr(base, "_CONFIG_CACHE", {"empresas_excluidas": []})
    assert es_empresa_excluida("Cualquiera") is False


# ---- Sueldo minimo ----

def test_sueldo_minimo(monkeypatch):
    monkeypatch.setattr(base, "_CONFIG_CACHE", {"sueldo_minimo": 700_000})
    assert pasa_sueldo_minimo("$1.300.000 - $2.200.000") is True
    assert pasa_sueldo_minimo("1.000.000") is True
    assert pasa_sueldo_minimo("$450.000 liquido") is False
    # No informados no se penalizan
    assert pasa_sueldo_minimo("A convenir") is True
    assert pasa_sueldo_minimo("") is True


def test_sueldo_minimo_desactivado(monkeypatch):
    monkeypatch.setattr(base, "_CONFIG_CACHE", {"sueldo_minimo": 0})
    assert pasa_sueldo_minimo("$100.000") is True


# ---- Ranking ponderado ----

def test_puntuar_afinidad_ponderado():
    oferta = Oferta(
        titulo="Desarrollador Junior Python",
        texto_ranking="usamos react",
        salario="$1.300.000 - $2.000.000",
        fecha_publicacion=datetime.now().strftime("%Y-%m-%d"),
    )
    puntaje, afinidad = puntuar_afinidad(oferta, ["python", "react"])
    # 2 stack + 2 junior + 1 sueldo + 1 reciente = 6
    assert puntaje == 6
    assert "junior +2" in afinidad
    assert "sueldo +1" in afinidad
    assert "reciente +1" in afinidad


def test_puntuar_afinidad_sin_extras():
    oferta = Oferta(titulo="Desarrollador Python", salario="A convenir",
                    fecha_publicacion="")
    puntaje, afinidad = puntuar_afinidad(oferta, ["python", "react"])
    assert puntaje == 1 and "python" in afinidad and "sueldo" not in afinidad


# ---- Historial con fecha y purga ----

def _escribir_historial(tmp_path, monkeypatch, data):
    archivo = tmp_path / "historial.json"
    archivo.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(base, "ARCHIVO_HISTORIAL", archivo)
    monkeypatch.setattr(base, "_CONFIG_CACHE", {"dias_purga_historial": 60})
    return archivo


def test_historial_purga_antiguas(tmp_path, monkeypatch):
    reciente = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    vieja = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    _escribir_historial(tmp_path, monkeypatch,
                        {"clave_reciente": reciente, "clave_vieja": vieja})
    historial = cargar_historial()
    assert "clave_reciente" in historial
    assert "clave_vieja" not in historial


def test_historial_migra_formato_antiguo(tmp_path, monkeypatch):
    _escribir_historial(tmp_path, monkeypatch, ["clave1", "clave2"])
    historial = cargar_historial()
    assert set(historial.keys()) == {"clave1", "clave2"}
