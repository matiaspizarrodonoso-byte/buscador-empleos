"""Buscador de empleos de informÃ¡tica (<= 1 aÃ±o de experiencia) en Chile.

Portales:
  - Computrabajo (scraping HTML con filtro de experiencia nativo)
  - Laborum (API del frontend, analisis del texto del aviso)
  - Trabajando.cl (API del frontend con filtros nativos de experiencia y region)
  - GetOnBoard (API publica, portal 100% tech)
  - Chiletrabajos (categoria nativa de informatica)
  - Jooble (API oficial, requiere key gratuita en config.json)
  - Indeed (links pre-filtrados; el scraping esta bloqueado)

Uso:
  python buscador.py               -> busqueda normal (marca las ofertas nuevas)
  python buscador.py --reiniciar   -> borra el historial de ofertas vistas

Resultado: empleos.xlsx con hoja "Ofertas" (ordenada por afinidad con tu
stack), una hoja por portal, "Mis postulaciones", "Indeed (links)",
"LinkedIn (links)" y "Plantilla email".
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from excel import generar_excel
from scrapers.base import (
    cargar_config,
    cargar_historial,
    guardar_historial,
    puntuar_afinidad,
)
from scrapers.chiletrabajos import buscar as buscar_chiletrabajos
from scrapers.computrabajo import buscar as buscar_computrabajo
from scrapers.getonboard import buscar as buscar_getonboard
from scrapers.indeed import generar_links as links_indeed
from scrapers.jooble import buscar as buscar_jooble
from scrapers.laborum import buscar as buscar_laborum
from scrapers.linkedin import generar_links as links_linkedin
from scrapers.trabajando import buscar as buscar_trabajando


def main() -> None:
    # Consola de Windows en UTF-8 (evita "sÂ¡", "ao" y tildes rotos)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    reiniciar = "--reiniciar" in sys.argv

    cfg = cargar_config()
    terminos = cfg["terminos"]
    region = cfg.get("region", "R.Metropolitana")
    remotos = cfg.get("incluir_remotos", True)
    paginas = cfg.get("paginas_por_busqueda", 2)
    pausa_seg = cfg.get("pausa_segundos", 3)
    dias_max = cfg.get("dias_maximo_publicacion")
    stack = cfg.get("stack", [])

    historial: dict[str, str] = {}
    if not reiniciar:
        historial = cargar_historial()
        if historial:
            print(f"Historial: {len(historial)} ofertas ya vistas "
                  f"(purga: {cfg.get('dias_purga_historial', 60)} dias).\n")

    print(f"Buscando '{', '.join(terminos)}'")
    print(f"Region: {region} | Remotos: {'sÃ­' if remotos else 'no'} | "
          f"Filtro de experiencia: hasta 1 aÃ±o\n")

    ofertas = []
    print("[1/7] Computrabajo ...")
    ofertas += buscar_computrabajo(
        terminos, region, remotos, paginas, pausa_seg, dias_max, historial)
    print(f"      -> {len(ofertas)} ofertas acumuladas")

    base_idx = len(ofertas)
    print("[2/7] Laborum ...")
    ofertas += buscar_laborum(
        terminos, region, remotos, paginas, pausa_seg, dias_max, historial)
    print(f"      -> {len(ofertas) - base_idx} ofertas")

    base_idx = len(ofertas)
    print("[3/7] Trabajando.cl ...")
    ofertas += buscar_trabajando(
        terminos, region, remotos, paginas, pausa_seg, dias_max, historial)
    print(f"      -> {len(ofertas) - base_idx} ofertas")

    base_idx = len(ofertas)
    print("[4/7] GetOnBoard ...")
    ofertas += buscar_getonboard(
        terminos, region, remotos, paginas, pausa_seg, dias_max, historial)
    print(f"      -> {len(ofertas) - base_idx} ofertas")

    base_idx = len(ofertas)
    print("[5/7] Chiletrabajos ...")
    ofertas += buscar_chiletrabajos(
        terminos, region, remotos, paginas, pausa_seg, dias_max, historial)
    print(f"      -> {len(ofertas) - base_idx} ofertas")

    base_idx = len(ofertas)
    print("[6/7] Jooble ...")
    ofertas += buscar_jooble(
        terminos, region, remotos, paginas, pausa_seg, dias_max, historial)
    print(f"      -> {len(ofertas) - base_idx} ofertas")

    # Deduplicar entre portales (mismo titulo + empresa)
    vistas: set[str] = set()
    unicas = []
    for o in ofertas:
        clave = o.clave_dedup()
        if clave not in vistas:
            vistas.add(clave)
            unicas.append(o)
    ofertas = unicas

    # Ranking por afinidad con el stack del usuario (mejores primero)
    for o in ofertas:
        o.puntaje, o.afinidad = puntuar_afinidad(o, stack)
    ofertas.sort(key=lambda o: o.puntaje, reverse=True)

    print("[7/7] Generando Excel ...")
    links = links_indeed(terminos)
    links_li = links_linkedin(terminos)
    ruta = generar_excel(ofertas, links, links_li, cfg)

    # Actualizar fecha de ultima vista y guardar (ya purgado al cargar)
    hoy = datetime.now().strftime("%Y-%m-%d")
    for clave in vistas:
        historial[clave] = hoy
    guardar_historial(historial)

    nuevas_ofertas = [o for o in ofertas if o.nueva]
    print(f"\nListo: {ruta.name}")
    print(f"   {len(ofertas)} ofertas totales ({len(nuevas_ofertas)} nuevas)")
    if nuevas_ofertas:
        for o in nuevas_ofertas[:10]:
            print(f"     - {o.titulo} | {o.empresa} ({o.portal})")
        if len(nuevas_ofertas) > 10:
            print(f"     ... y {len(nuevas_ofertas) - 10} mas")
    print(f"   {len(links)} links de Indeed y {len(links_li)} de LinkedIn "
          f"en sus hojas del Excel")
    print(f"   Plantilla de email lista en la hoja 'Plantilla email'")

    # Abrir el Excel automaticamente al terminar
    if cfg.get("abrir_excel_al_terminar", True) and sys.platform == "win32":
        try:
            os.startfile(ruta)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
