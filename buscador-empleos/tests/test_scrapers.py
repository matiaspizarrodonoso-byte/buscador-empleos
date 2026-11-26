"""Tests de regresión para la extracción y robustez de los scrapers."""

import pytest

from scrapers import getonboard, laborum, trabajando
from scrapers import chiletrabajos
from scrapers.base import anios_exigencia


class _Respuesta:
    def __init__(self, texto="", error_json=False):
        self.status_code = 200
        self.text = texto
        self._error_json = error_json

    def json(self):
        if self._error_json:
            raise ValueError("La respuesta contiene HTML, no JSON")
        return {}


class _Sesion:
    def __init__(self, respuesta):
        self.headers = {}
        self.respuesta = respuesta

    def get(self, *args, **kwargs):
        return self.respuesta

    def post(self, *args, **kwargs):
        return self.respuesta


def test_getonboard_limpia_html_antes_de_detectar_experiencia():
    item = {
        "attributes": {
            "title": "Desarrollador Python",
            "description": "Se requieren 3 <strong>años</strong> de experiencia",
        },
        "links": {},
    }

    _, descripcion = getonboard._a_oferta(item, "python", {})

    assert "<strong>" not in descripcion
    assert "3 años de experiencia" in descripcion
    assert anios_exigencia(descripcion) == 3


def test_chiletrabajos_detalle_extrae_descripcion_sueldo_y_titulo():
    html = """
    <html><body>
      <h1>Desarrollador Python y SQL</h1>
      <div class="botones-desc">
        <span class="btn"><i class="fa fa-money"></i>$1.200.000</span>
      </div>
      <h3 class="title">Descripción del empleo</h3>
      <div><!--<p>Buscamos desarrollador con conocimientos de Python y SQL.
      Esta descripción completa supera los ochenta caracteres necesarios.</p>--></div>
    </body></html>
    """
    sesion = _Sesion(_Respuesta(html))

    descripcion, salario, titulo = chiletrabajos._detalle(
        sesion, "https://www.chiletrabajos.cl/oferta/1")

    assert titulo == "Desarrollador Python y SQL"
    assert salario == "$1.200.000"
    assert "conocimientos de Python y SQL" in descripcion
    assert "<p>" not in descripcion


def test_trabajando_detalle_extrae_solo_el_articulo():
    html = """
    <html><body>
      <aside>Filtros y sueldos de otras ofertas</aside>
      <article><h1>Desarrollador Python</h1><p>Trabajo remoto en Santiago.</p></article>
    </body></html>
    """
    sesion = _Sesion(_Respuesta(html))

    descripcion = trabajando._descripcion_detalle(
        sesion, "https://www.trabajando.cl/trabajo/1-desarrollador-python")

    assert "Trabajo remoto en Santiago." in descripcion
    assert "Filtros y sueldos" not in descripcion


@pytest.mark.parametrize("modulo", [laborum, trabajando, getonboard])
def test_api_http_200_no_json_no_interrumpe_la_corrida(modulo, monkeypatch, capsys):
    sesion = _Sesion(_Respuesta("<html>Desafío WAF</html>", error_json=True))
    monkeypatch.setattr(modulo, "crear_sesion", lambda: sesion)
    monkeypatch.setattr(modulo, "pausa", lambda segundos: None)
    if modulo is getonboard:
        monkeypatch.setattr(modulo, "_mapa_ciudades", lambda s: {1: "Santiago"})

    ofertas = modulo.buscar(
        ["python"], "R.Metropolitana", True, 1, 0, 30, {})

    assert ofertas == []
    assert "respuesta no-JSON con HTTP 200" in capsys.readouterr().out
