"""Test de persistencia de la columna Postulado entre corridas.

Genera un Excel, marca "Enviado" en una oferta, regenera y verifica que
la marca sobrevive (y que el resto queda en "Pendiente").
"""

import pandas as pd
from openpyxl import load_workbook

import excel
from excel import COLUMNAS, generar_excel
from scrapers.base import Oferta


def _ofertas() -> list[Oferta]:
    return [
        Oferta(titulo="Desarrollador Python", empresa="Acme SpA",
               ubicacion="Santiago", modalidad="Remoto", portal="Laborum",
               url="https://ejemplo.cl/1", url_postulacion="https://ejemplo.cl/1"),
        Oferta(titulo="Analista de Datos", empresa="Beta Ltda",
               ubicacion="Santiago", modalidad="Híbrido", portal="GetOnBoard",
               url="https://ejemplo.cl/2", url_postulacion="https://ejemplo.cl/2"),
    ]


def test_postulado_persiste_entre_corridas(tmp_path, monkeypatch):
    monkeypatch.setattr(excel, "RAIZ", tmp_path)
    (tmp_path / "plantilla_email.txt").write_text("Hola {nombre}", encoding="utf-8")
    config = {"excel_salida": "empleos.xlsx", "nombre": "Test"}

    # 1ra corrida: se genera el Excel
    ruta = generar_excel(_ofertas(), [], [], config)

    # El usuario marca la primera oferta como "Enviado"
    wb = load_workbook(ruta)
    ws = wb["Ofertas"]
    col_post = COLUMNAS.index("Postulado") + 1
    ws.cell(row=2, column=col_post).value = "Enviado"
    wb.save(ruta)

    # 2da corrida: se regenera el Excel desde cero
    ruta2 = generar_excel(_ofertas(), [], [], config)
    df = pd.read_excel(ruta2, sheet_name="Ofertas")

    marca_acme = df.loc[df["Empresa"] == "Acme SpA", "Postulado"].iloc[0]
    marca_beta = df.loc[df["Empresa"] == "Beta Ltda", "Postulado"].iloc[0]
    assert marca_acme == "Enviado", "La marca del usuario se perdio al regenerar"
    assert marca_beta == "Pendiente", "Las celdas sin marca deben quedar Pendiente"


def _preparar(tmp_path, monkeypatch):
    monkeypatch.setattr(excel, "RAIZ", tmp_path)
    (tmp_path / "plantilla_email.txt").write_text("Hola {nombre}", encoding="utf-8")
    return {"excel_salida": "empleos.xlsx", "nombre": "Test"}


def _marcar(ruta, fila, estado):
    wb = load_workbook(ruta)
    ws = wb["Ofertas"]
    ws.cell(row=fila, column=COLUMNAS.index("Postulado") + 1).value = estado
    wb.save(ruta)


def test_mis_postulaciones_consolida_y_sobrevive(tmp_path, monkeypatch):
    """Una oferta marcada "Enviado" pasa a 'Mis postulaciones' y queda ahi
    aunque en la siguiente corrida ya no aparezca (expirada en el portal)."""
    config = _preparar(tmp_path, monkeypatch)

    # 1ra corrida: marcar la oferta de Acme como "Enviado"
    ruta = generar_excel(_ofertas(), [], [], config)
    _marcar(ruta, 2, "Enviado")

    # 2da corrida: la oferta de Acme ya NO viene (expirada en el portal)
    ruta2 = generar_excel([_ofertas()[1]], [], [], config)
    dfp = pd.read_excel(ruta2, sheet_name="Mis postulaciones")

    acme = dfp[dfp["Empresa"] == "Acme SpA"]
    assert len(acme) == 1, "La postulacion se perdio al expirar la oferta"
    assert acme.iloc[0]["Estado"] == "Enviado"
    assert acme.iloc[0]["Link postulación"] == "https://ejemplo.cl/1"
    assert acme.iloc[0]["Fecha"], "La fecha de consolidacion no debe estar vacia"


def test_mis_postulaciones_actualiza_estado_conserva_fecha(tmp_path, monkeypatch):
    """Si la oferta sigue activa y la marca cambia (Enviado -> Respondieron),
    el Estado se actualiza pero la Fecha original se conserva."""
    config = _preparar(tmp_path, monkeypatch)

    ruta = generar_excel(_ofertas(), [], [], config)
    _marcar(ruta, 2, "Enviado")
    ruta2 = generar_excel(_ofertas(), [], [], config)
    fecha_inicial = pd.read_excel(ruta2, sheet_name="Mis postulaciones")
    fecha_inicial = fecha_inicial.loc[fecha_inicial["Empresa"] == "Acme SpA",
                                      "Fecha"].iloc[0]

    # El usuario actualiza la marca a "Respondieron"
    _marcar(ruta2, 2, "Respondieron")
    ruta3 = generar_excel(_ofertas(), [], [], config)
    dfp = pd.read_excel(ruta3, sheet_name="Mis postulaciones")
    acme = dfp[dfp["Empresa"] == "Acme SpA"].iloc[0]
    assert acme["Estado"] == "Respondieron"
    assert acme["Fecha"] == fecha_inicial


def test_mis_postulaciones_ignora_pendientes(tmp_path, monkeypatch):
    config = _preparar(tmp_path, monkeypatch)
    ruta = generar_excel(_ofertas(), [], [], config)
    # Regenerar sin marcar nada: "Pendiente" no se consolida
    ruta2 = generar_excel(_ofertas(), [], [], config)
    dfp = pd.read_excel(ruta2, sheet_name="Mis postulaciones")
    assert dfp.empty


def test_excel_bloqueado_guarda_respaldo(tmp_path, monkeypatch):
    """Si empleos.xlsx esta abierto en Excel (PermissionError), la corrida
    no se pierde: se guarda como empleos_respaldo.xlsx."""
    config = _preparar(tmp_path, monkeypatch)
    escribir_real = excel._escribir

    def escribir_falla_si_original(salida, *args, **kwargs):
        if salida.name == "empleos.xlsx":
            raise PermissionError("archivo abierto en Excel")
        return escribir_real(salida, *args, **kwargs)

    monkeypatch.setattr(excel, "_escribir", escribir_falla_si_original)
    ruta = generar_excel(_ofertas(), [], [], config)
    assert ruta.name == "empleos_respaldo.xlsx"
    assert ruta.exists()
    df = pd.read_excel(ruta, sheet_name="Ofertas")
    assert len(df) == 2
