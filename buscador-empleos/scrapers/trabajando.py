"""Scraper de Trabajando.cl via API interna del frontend (Nuxt).

GET https://www.trabajando.cl/api/searchjob
Params clave: palabraClave, pagina (desde 1), cantidadResultados,
              aniosExpDesde, aniosExpHasta, orden=RANKING, tipoOrden=DESC,
              region (id nativo, ver _REGION_ID)
El filtro aniosExpHasta=1 restringe nativamente a <= 1 año de experiencia
y el parametro region filtra nativamente por region (los ids vienen de la
faceta "region" de la propia API), asi las paginas no se desperdician en
ofertas de otras zonas.

La API solo trae un teaser (~40 chars) de descripcion: con
descargar_descripciones se baja el detalle (texto completo en el
<article> de la pagina, Nuxt SSR) para es_accesible y el ranking.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import (
    Oferta,
    SaludPortal,
    cargar_config,
    crear_sesion,
    detectar_modalidad,
    dias_desde_texto,
    en_region_o_remoto,
    es_accesible,
    es_empresa_excluida,
    es_practica,
    es_puesto_it,
    es_senior,
    pausa,
    quitar_tildes,
    slugificar,
)

BASE = "https://www.trabajando.cl"
API = f"{BASE}/api/searchjob"


def _texto(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def _descripcion_detalle(s, url: str) -> str:
    """Descripcion completa de la pagina de la oferta (elemento <article>).

    La API solo trae un teaser (~40 chars) en descripcionOferta; el detalle
    es server-rendered (Nuxt SSR) y el texto completo queda en el
    <article> de la pagina. El sueldo NO se extrae: los montos $ de la
    pagina son rangos del sidebar de filtros, no el sueldo de la oferta.
    """
    try:
        r = s.get(url, timeout=20)
    except Exception:
        return ""
    if r.status_code != 200:
        return ""
    return _texto(BeautifulSoup(r.text, "html.parser").select_one("article"))

# Ids de region del filtro nativo (faceta "region" de la API, sondeada en
# vivo). Ojo: NO es la numeracion oficial de Chile (RM = 1).
_REGION_ID = {
    "metropolitana": 1, "tarapaca": 2, "antofagasta": 3, "atacama": 4,
    "coquimbo": 5, "valparaiso": 6, "ohiggins": 7, "maule": 8,
    "biobio": 9, "araucania": 10, "los lagos": 11, "aysen": 12,
    "magallanes": 13, "los rios": 472, "arica": 473, "nuble": 556,
}


def _id_region(region: str) -> int | None:
    """Id de region de Trabajando para la region configurada, o None."""
    r = quitar_tildes((region or "").lower())
    r = re.sub(r"^r\.?\s*", "", r).strip()
    for clave, id_region in _REGION_ID.items():
        if clave in r:
            return id_region
    return None


def _a_oferta(o: dict, termino: str) -> tuple[Oferta, str]:
    titulo = o.get("nombreCargo") or ""
    id_oferta = o.get("idOferta")
    url = f"{BASE}/trabajo/{id_oferta}-{slugificar(titulo)}" if id_oferta else ""
    oferta = Oferta(
        titulo=titulo,
        empresa=o.get("nombreEmpresa") or "No indicado",
        ubicacion=o.get("ubicacion") or "",
        modalidad=o.get("nombreJornada") or "No indicada",
        salario="A convenir",
        fecha_publicacion=o.get("publicadoHace") or o.get("fechaPublicacion") or "",
        experiencia="Filtro nativo del portal (hasta 1 año)",
        portal="Trabajando.cl",
        url=url,
        url_postulacion=url,
        buscado_con=termino,
    )
    oferta.texto_ranking = o.get("descripcionOferta") or ""
    return oferta, oferta.texto_ranking


def buscar(terminos: list[str], region: str, incluir_remotos: bool,
           paginas: int, pausa_seg: float, dias_max: int | None = None,
           historial: dict[str, str] | None = None) -> list[Oferta]:
    s = crear_sesion()
    s.headers.update({"Accept": "application/json, text/plain, */*", "Referer": f"{BASE}/"})
    salud = SaludPortal("Trabajando.cl")
    vistas: set[str] = set()
    resultado: list[Oferta] = []
    detalles_intentados = 0
    detalles_fallidos = 0
    descargar_desc = cargar_config().get("descargar_descripciones", True)
    id_region = _id_region(region)  # filtro nativo de region (faceta de la API)
    for termino in terminos:
        for pagina in range(1, paginas + 1):
            params = {
                "palabraClave": termino,
                "pagina": pagina,
                "cantidadResultados": 50,  # la API lo acepta (sondeado; antes 20)
                "aniosExpDesde": 0,
                "aniosExpHasta": 1,
                "orden": "RANKING",
                "tipoOrden": "DESC",
            }
            if id_region is not None:
                params["region"] = id_region
            try:
                r = s.get(API, params=params, timeout=25)
            except Exception as e:
                print(f"  [Trabajando] error ({termino}, pag {pagina}): {e}")
                continue
            if r.status_code != 200:
                print(f"  [Trabajando] HTTP {r.status_code} ({termino}, pag {pagina})")
                break
            try:
                data = r.json()
            except ValueError:
                # HTTP 200 con HTML (reto WAF, mantenimiento): sin este
                # guarda el JSONDecodeError tumbaba TODA la corrida.
                print(f"  [Trabajando] respuesta no-JSON con HTTP 200 "
                      f"({termino}, pag {pagina}): posible bloqueo o "
                      f"cambio de API")
                break
            ofertas = data.get("ofertas") or []
            salud.registrar(len(ofertas))
            if not ofertas:
                break
            for o in ofertas:
                oferta, descripcion = _a_oferta(o, termino)
                clave = oferta.clave_dedup()
                if clave in vistas or not oferta.titulo:
                    continue
                vistas.add(clave)
                if not es_puesto_it(oferta.titulo) or es_practica(oferta.titulo) \
                        or es_senior(oferta.titulo):
                    continue
                if es_empresa_excluida(oferta.empresa):
                    continue
                if not en_region_o_remoto(oferta.ubicacion, oferta.modalidad, region, incluir_remotos):
                    continue
                if descripcion and not es_accesible(descripcion):
                    continue
                if dias_max is not None:
                    # Misma fecha que se muestra en el Excel (publicadoHace)
                    d = dias_desde_texto(oferta.fecha_publicacion)
                    if d is not None and d > dias_max:
                        continue
                if historial is not None:
                    oferta.nueva = clave not in historial
                if descargar_desc:
                    # La API solo trae un teaser: descripcion completa del
                    # detalle (mejora es_accesible y el ranking por stack)
                    desc = _descripcion_detalle(s, oferta.url)
                    detalles_intentados += 1
                    if not desc:
                        detalles_fallidos += 1
                    pausa(pausa_seg)
                    if desc:
                        if not es_accesible(desc):
                            continue
                        oferta.texto_ranking = desc
                        if oferta.modalidad == "No indicada":
                            oferta.modalidad = detectar_modalidad(
                                f"{oferta.titulo} {desc}") or "No indicada"
                resultado.append(oferta)
            pausa(pausa_seg)
        pausa(pausa_seg)
    if detalles_intentados >= 5 and detalles_fallidos > detalles_intentados / 2:
        print(f"  [Trabajando] ALERTA: {detalles_fallidos} de "
              f"{detalles_intentados} paginas de detalle fallaron: el sitio "
              f"pudo cambiar su HTML (se perdieron las descripciones "
              f"completas).")
    salud.revisar()
    return resultado
