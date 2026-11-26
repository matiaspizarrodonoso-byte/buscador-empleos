"""Scraper de Computrabajo Chile (HTML server-rendered, sin JS).

URLs de búsqueda con filtro de experiencia nativo:
  - Sin experiencia: /trabajo-de-{termino}-sin-experiencia?p={n}
  - 1 año:            /trabajo-de-{termino}?iex=4&p={n}
"""

from __future__ import annotations

from urllib.parse import urljoin

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
    pasa_sueldo_minimo,
    pausa,
    slugificar,
)

BASE = "https://cl.computrabajo.com"


def _texto(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def _descripcion_detalle(s, url: str) -> str:
    """Descripcion completa de la pagina de la oferta (div[div-link=oferta]).

    El listado NO trae descripcion; se descarga el detalle solo para las
    ofertas que ya pasaron los filtros (1 request por oferta final).
    """
    try:
        r = s.get(url, timeout=20)
    except Exception:
        return ""
    if r.status_code != 200:
        return ""
    soup = BeautifulSoup(r.text, "html.parser")
    div = soup.select_one('div[div-link="oferta"]')
    return _texto(div)


def _parsear_pagina(html: str, termino: str) -> list[Oferta]:
    soup = BeautifulSoup(html, "html.parser")
    ofertas = []
    for art in soup.select("article.box_offer"):
        a_titulo = art.select_one("h2 a.js-o-link")
        if not a_titulo:
            continue
        titulo = _texto(a_titulo)

        a_empresa = art.select_one("a[offer-grid-article-company-url]")
        empresa = _texto(a_empresa) or "No indicado"

        # La ubicacion esta en p.fs16 SIN clase dFlex (el p.dFlex es la empresa
        # y su calificacion, que tambien usa span.mr10)
        spans_ubi = art.select("p.fs16:not(.dFlex) span.mr10")
        ubicacion = _texto(spans_ubi[0]) if spans_ubi else ""

        salario = ""
        modalidad = ""
        for span in art.select("div.fs13 span.dIB"):
            icono = span.select_one("span.icon")
            clase = icono.get("class", []) if icono else []
            if any("i_salary" in c for c in clase):
                salario = _texto(span)
            elif any("i_home_office" in c for c in clase):
                modalidad = _texto(span)

        p_fecha = art.select_one("p.fs13.fc_aux")
        fecha = _texto(p_fecha)

        # El fragmento #lc=... es solo rastreo interno; se elimina.
        # Se usa el link de la OFERTA como link de postulación: el enlace
        # "data-href-offer-apply" (candidato.cl.computrabajo.com/...apply)
        # devuelve 404 al abrirlo sin sesión de navegador.
        href = a_titulo.get("href", "")
        url = urljoin(BASE, href.split("#")[0])

        ofertas.append(Oferta(
            titulo=titulo,
            empresa=empresa,
            ubicacion=ubicacion,
            modalidad=modalidad or "No indicada",
            salario=salario or "A convenir",
            fecha_publicacion=fecha,
            experiencia="Filtro nativo del portal (sin exp. / 1 año)",
            portal="Computrabajo",
            url=url,
            url_postulacion=url,
            buscado_con=termino,
        ))
    return ofertas


def buscar(terminos: list[str], region: str, incluir_remotos: bool,
           paginas: int, pausa_seg: float, dias_max: int | None = None,
           historial: dict[str, str] | None = None) -> list[Oferta]:
    s = crear_sesion()
    salud = SaludPortal("Computrabajo")
    descargar_desc = cargar_config().get("descargar_descripciones", True)
    vistas: set[str] = set()
    resultado: list[Oferta] = []
    detalles_intentados = 0
    detalles_fallidos = 0
    for termino in terminos:
        slug = slugificar(termino)
        # Dos variantes: sin experiencia (slug) y con 1 año (parametro iex=4)
        plantillas = [
            f"{BASE}/trabajo-de-{slug}-sin-experiencia",
            f"{BASE}/trabajo-de-{slug}?iex=4",
        ]
        for plantilla in plantillas:
            for pagina in range(1, paginas + 1):
                url = f"{plantilla}&p={pagina}" if "?" in plantilla else f"{plantilla}?p={pagina}"
                try:
                    r = s.get(url, timeout=20)
                except Exception as e:
                    print(f"  [Computrabajo] error en {url}: {e}")
                    continue
                if r.status_code != 200:
                    print(f"  [Computrabajo] HTTP {r.status_code} en {url}")
                    break
                nuevas = _parsear_pagina(r.text, termino)
                salud.registrar(len(nuevas))
                if not nuevas:
                    break
                for o in nuevas:
                    clave = o.clave_dedup()
                    if clave in vistas:
                        continue
                    vistas.add(clave)
                    # Los filtros de titulo van aca (no en el parseo) para
                    # que el corte de pagina y SaludPortal midan las
                    # tarjetas reales del portal.
                    if not es_puesto_it(o.titulo) or es_practica(o.titulo) \
                            or es_senior(o.titulo):
                        continue
                    if es_empresa_excluida(o.empresa):
                        continue
                    if not en_region_o_remoto(o.ubicacion, o.modalidad, region, incluir_remotos):
                        continue
                    if not pasa_sueldo_minimo(o.salario):
                        continue
                    if dias_max is not None:
                        d = dias_desde_texto(o.fecha_publicacion)
                        if d is not None and d > dias_max:
                            continue
                    if historial is not None:
                        o.nueva = clave not in historial
                    if descargar_desc:
                        # 2do filtro de experiencia con la descripcion completa
                        # y texto para el ranking por stack
                        desc = _descripcion_detalle(s, o.url)
                        detalles_intentados += 1
                        if not desc:
                            detalles_fallidos += 1
                        pausa(pausa_seg)
                        if desc:
                            if not es_accesible(desc):
                                continue
                            o.texto_ranking = desc
                            if o.modalidad == "No indicada":
                                o.modalidad = detectar_modalidad(
                                    f"{o.titulo} {desc}") or "No indicada"
                    resultado.append(o)
                # Parada temprana: si TODA la pagina supera el limite de
                # antiguedad, las siguientes seran aun mas viejas.
                if dias_max is not None:
                    ds = [d for o in nuevas
                          if (d := dias_desde_texto(o.fecha_publicacion)) is not None]
                    if ds and all(d > dias_max for d in ds):
                        break
                pausa(pausa_seg)
            pausa(pausa_seg)
    if detalles_intentados >= 5 and detalles_fallidos > detalles_intentados / 2:
        print(f"  [Computrabajo] ALERTA: {detalles_fallidos} de "
              f"{detalles_intentados} paginas de detalle fallaron: el sitio "
              f"pudo cambiar su HTML (se perdio el 2do filtro de "
              f"experiencia y la descripcion para el ranking).")
    salud.revisar()
    return resultado
