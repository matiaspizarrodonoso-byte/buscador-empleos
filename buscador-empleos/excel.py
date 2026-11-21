"""Genera el archivo Excel con las ofertas, links de Indeed y plantilla de email."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from scrapers.base import RAIZ, Oferta, normalizar_clave

COLOR_HEADER = "1F4E79"
FONDO_NUEVA = "C6EFCE"
COLUMNAS = [
    "Nueva", "Título", "Empresa", "Ubicación", "Modalidad", "Salario",
    "Publicado", "Requisito experiencia", "Afinidad", "Portal", "Postulado",
    "Búsqueda", "Link postulación",
]
COLUMNAS_POSTULACIONES = [
    "Título", "Empresa", "Portal", "Estado", "Fecha", "Notas", "Link postulación",
]
# Estados que se consolidan en "Mis postulaciones" (Pendiente no aplica)
ESTADOS_SEGUIMIENTO = ("Enviado", "Respondieron", "Descartado")


def _s(v) -> str:
    """str seguro para celdas leidas con pandas (None/NaN -> "")."""
    return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)


def _marcas_previas(ruta: Path) -> dict[str, dict]:
    """Marcas de la columna Postulado del Excel anterior, con datos de la fila.

    {clave: {"estado", "titulo", "empresa", "portal", "link"}}. Alimenta la
    restauracion de marcas en "Ofertas" y la consolidacion de la hoja
    "Mis postulaciones". Si el Excel no existe o no se puede leer, devuelve {}.
    """
    marcas: dict[str, dict] = {}
    if not ruta.exists():
        return marcas
    try:
        df = pd.read_excel(ruta, sheet_name="Ofertas")
    except Exception:
        return marcas
    for _, fila in df.iterrows():
        estado = _s(fila.get("Postulado")).strip()
        if not estado:
            continue
        clave = normalizar_clave(_s(fila.get("Título")), _s(fila.get("Empresa")))
        marcas[clave] = {
            "estado": estado,
            "titulo": _s(fila.get("Título")),
            "empresa": _s(fila.get("Empresa")),
            "portal": _s(fila.get("Portal")),
            "link": _s(fila.get("Link postulación")),
        }
    return marcas


def _df_ofertas(ofertas: list[Oferta],
                estados_previos: dict[str, str] | None = None) -> pd.DataFrame:
    estados_previos = estados_previos or {}
    filas = []
    for o in ofertas:
        filas.append({
            "Nueva": "Sí" if o.nueva else "",
            "Título": o.titulo,
            "Empresa": o.empresa,
            "Ubicación": o.ubicacion or "No indicada",
            "Modalidad": o.modalidad or "No indicada",
            "Salario": o.salario or "A convenir",
            "Publicado": o.fecha_publicacion or "-",
            "Requisito experiencia": o.experiencia or "-",
            "Afinidad": f"{o.afinidad} ({o.puntaje})" if o.puntaje else "",
            "Portal": o.portal,
            "Postulado": estados_previos.get(normalizar_clave(o.titulo, o.empresa), ""),
            "Búsqueda": o.buscado_con,
            "Link postulación": o.url_postulacion or o.url,
        })
    return pd.DataFrame(filas, columns=COLUMNAS)


def _nombre_hoja_portal(portal: str) -> str:
    """Nombre de hoja valido en Excel (max 31 caracteres, sin caracteres raros)."""
    return portal.replace(".", " ").strip()[:31]


def _df_postulaciones(ruta: Path, marcas: dict[str, dict]) -> pd.DataFrame:
    """Hoja acumulativa "Mis postulaciones" (seguimiento real de la busqueda).

    Conserva las filas del Excel anterior (con su Fecha y Notas) y agrega o
    actualiza las ofertas marcadas como Enviado/Respondieron/Descartado.
    Asi el registro de a que empresas ya se postulo sobrevive aunque la
    oferta expire y desaparezca de los portales. Mientras la oferta siga
    activa, la marca de la hoja "Ofertas" manda sobre la columna Estado.
    """
    filas: dict[str, dict] = {}
    if ruta.exists():
        try:
            dfp = pd.read_excel(ruta, sheet_name="Mis postulaciones")
        except Exception:
            dfp = None
        if dfp is not None:
            for _, f in dfp.iterrows():
                clave = normalizar_clave(_s(f.get("Título")), _s(f.get("Empresa")))
                filas[clave] = {
                    "Título": _s(f.get("Título")),
                    "Empresa": _s(f.get("Empresa")),
                    "Portal": _s(f.get("Portal")),
                    "Estado": _s(f.get("Estado")),
                    "Fecha": _s(f.get("Fecha")),
                    "Notas": _s(f.get("Notas")),
                    "Link postulación": _s(f.get("Link postulación")),
                }
    hoy = datetime.now().strftime("%Y-%m-%d")
    for clave, m in marcas.items():
        if m["estado"] not in ESTADOS_SEGUIMIENTO:
            continue
        if clave in filas:
            filas[clave]["Estado"] = m["estado"]
            if m["link"]:
                filas[clave]["Link postulación"] = m["link"]
        else:
            filas[clave] = {
                "Título": m["titulo"], "Empresa": m["empresa"],
                "Portal": m["portal"], "Estado": m["estado"], "Fecha": hoy,
                "Notas": "", "Link postulación": m["link"],
            }
    df = pd.DataFrame(filas.values(), columns=COLUMNAS_POSTULACIONES)
    if not df.empty:
        df = df.sort_values("Fecha", ascending=False)
    return df


def generar_excel(ofertas: list[Oferta], links_indeed: list[dict],
                  links_linkedin: list[dict], config: dict) -> Path:
    salida = RAIZ / config.get("excel_salida", "empleos.xlsx")
    marcas = _marcas_previas(salida)
    df = _df_ofertas(ofertas, {k: m["estado"] for k, m in marcas.items()})
    df_post = _df_postulaciones(salida, marcas)
    try:
        _escribir(salida, df, df_post, links_indeed, links_linkedin, config)
    except PermissionError:
        # El archivo esta abierto en Excel (p.ej. por la apertura automatica
        # de la corrida anterior): no perder la corrida, guardar con otro nombre.
        salida = salida.with_name(f"{salida.stem}_respaldo{salida.suffix}")
        print(f"  [Excel] El archivo original esta abierto o bloqueado; "
              f"esta corrida se guardo como {salida.name}")
        _escribir(salida, df, df_post, links_indeed, links_linkedin, config)
    return salida


def _escribir(salida: Path, df: pd.DataFrame, df_post: pd.DataFrame,
              links_indeed: list[dict], links_linkedin: list[dict],
              config: dict) -> None:
    # Hoja maestra + una hoja por portal (para diferenciar la fuente)
    hojas_ofertas: dict[str, int] = {"Ofertas": len(df)}
    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Ofertas", index=False)
        if not df.empty:
            for portal, dfp in df.groupby("Portal"):
                hoja = _nombre_hoja_portal(portal)
                hojas_ofertas[hoja] = len(dfp)
                dfp.to_excel(writer, sheet_name=hoja, index=False)
        df_post.to_excel(writer, sheet_name="Mis postulaciones", index=False)
        pd.DataFrame(links_indeed).to_excel(
            writer, sheet_name="Indeed (links)", index=False)
        pd.DataFrame(links_linkedin).to_excel(
            writer, sheet_name="LinkedIn (links)", index=False)
        _hoja_plantilla(writer.book, config)

    _dar_formato(salida, hojas_ofertas)


def _hoja_plantilla(wb, config: dict) -> None:
    ws = wb.create_sheet("Plantilla email")
    plantilla = (RAIZ / "plantilla_email.txt").read_text(encoding="utf-8")
    reemplazos = {
        "{nombre}": config.get("nombre", ""),
        "{titulo_profesional}": config.get("titulo_profesional", ""),
        "{email}": config.get("email", ""),
        "{telefono}": config.get("telefono", ""),
        "{linkedin}": config.get("linkedin", ""),
        "{puesto}": "[PUESTO]",
        "{empresa}": "[EMPRESA]",
        "{portal}": "[PORTAL]",
    }
    texto = plantilla
    for k, v in reemplazos.items():
        texto = texto.replace(k, v)

    ws["A1"] = "PLANTILLA DE EMAIL PARA ENVIAR TU CV"
    ws["A1"].font = Font(bold=True, size=14, color=COLOR_HEADER)
    ws["A2"] = ("Copia este texto, reemplaza [PUESTO], [EMPRESA] y [PORTAL] "
                "con los datos de la oferta (columnas de la hoja 'Ofertas') "
                "y adjunta tu CV en PDF.")
    ws["A2"].font = Font(italic=True, size=10)
    fila = 4
    for linea in texto.splitlines():
        ws.cell(row=fila, column=1, value=linea if linea else None)
        fila += 1
    ws.column_dimensions["A"].width = 110


def _dar_formato(ruta: Path, hojas_ofertas: dict[str, int]) -> None:
    wb = load_workbook(ruta)
    encabezado_fill = PatternFill("solid", fgColor=COLOR_HEADER)

    # ---- Hojas de ofertas (maestra + una por portal) ----
    for nombre_hoja, n_ofertas in hojas_ofertas.items():
        ws = wb[nombre_hoja]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        for celda in ws[1]:
            celda.font = Font(bold=True, color="FFFFFF", size=11)
            celda.fill = encabezado_fill
            celda.alignment = Alignment(vertical="center", wrap_text=True)

        anchos = {"A": 7, "B": 45, "C": 22, "D": 28, "E": 18, "F": 16,
                  "G": 16, "H": 24, "I": 18, "J": 13, "K": 12, "L": 16, "M": 45}
        for col, ancho in anchos.items():
            ws.column_dimensions[col].width = ancho

        col_nueva = get_column_letter(COLUMNAS.index("Nueva") + 1)
        fill_nueva = PatternFill("solid", fgColor=FONDO_NUEVA)

        for fila in range(2, n_ofertas + 2):
            link = ws.cell(row=fila, column=COLUMNAS.index("Link postulación") + 1)
            if link.value:
                link.hyperlink = link.value
                link.font = Font(color="0563C1", underline="single")
            nueva = ws[f"{col_nueva}{fila}"]
            if nueva.value == "Sí":
                for celda in ws[fila]:
                    celda.fill = fill_nueva
            ws.row_dimensions[fila].height = 30
            ws.cell(row=fila, column=COLUMNAS.index("Título") + 1).alignment = Alignment(wrap_text=True, vertical="center")
            ws.cell(row=fila, column=COLUMNAS.index("Empresa") + 1).alignment = Alignment(wrap_text=True, vertical="center")

        # Dropdown "Postulado": Pendiente / Enviado / Respondieron
        dv = DataValidation(
            type="list",
            formula1='"Pendiente,Enviado,Respondieron,Descartado"',
            allow_blank=True,
        )
        ws.add_data_validation(dv)
        col_post = get_column_letter(COLUMNAS.index("Postulado") + 1)
        dv.add(f"{col_post}2:{col_post}{n_ofertas + 1}")
        # "Pendiente" solo en celdas vacias: no pisar estados restaurados
        for fila in range(2, n_ofertas + 2):
            celda = ws[f"{col_post}{fila}"]
            if not celda.value:
                celda.value = "Pendiente"

    # ---- Hoja acumulativa "Mis postulaciones" ----
    if "Mis postulaciones" in wb.sheetnames:
        ws = wb["Mis postulaciones"]
        ws.freeze_panes = "A2"
        for celda in ws[1]:
            celda.font = Font(bold=True, color="FFFFFF", size=11)
            celda.fill = encabezado_fill
        anchos = {"A": 45, "B": 22, "C": 14, "D": 14, "E": 12, "F": 30, "G": 45}
        for col, ancho in anchos.items():
            ws.column_dimensions[col].width = ancho
        col_link = COLUMNAS_POSTULACIONES.index("Link postulación") + 1
        for fila in range(2, ws.max_row + 1):
            celda = ws.cell(row=fila, column=col_link)
            if celda.value:
                celda.hyperlink = celda.value
                celda.font = Font(color="0563C1", underline="single")
        dv = DataValidation(
            type="list",
            formula1=f'"{",".join(ESTADOS_SEGUIMIENTO)}"',
            allow_blank=True,
        )
        ws.add_data_validation(dv)
        col_estado = get_column_letter(COLUMNAS_POSTULACIONES.index("Estado") + 1)
        dv.add(f"{col_estado}2:{col_estado}{max(ws.max_row, 2)}")

    # ---- Hojas de links pre-filtrados (Indeed / LinkedIn) ----
    for nombre_hoja in ("Indeed (links)", "LinkedIn (links)"):
        if nombre_hoja not in wb.sheetnames:
            continue
        wsi = wb[nombre_hoja]
        wsi.freeze_panes = "A2"
        for celda in wsi[1]:
            celda.font = Font(bold=True, color="FFFFFF", size=11)
            celda.fill = encabezado_fill
        wsi.column_dimensions["A"].width = 22
        wsi.column_dimensions["B"].width = 30
        wsi.column_dimensions["C"].width = 90
        for fila in range(2, wsi.max_row + 1):
            celda = wsi.cell(row=fila, column=3)
            if celda.value:
                celda.hyperlink = celda.value
                celda.font = Font(color="0563C1", underline="single")

    wb.save(ruta)
