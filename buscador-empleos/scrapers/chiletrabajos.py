"""Scraper de Chiletrabajos (HTML server-rendered, sin JS).

Usa la categoría nativa de informática (el portal ya prefiltra por área):
  - Pagina 1: /trabajos/informatica
  - Pagina N: /trabajos/informatica/{offset}   (offset = 30*(N-1), 30 por pagina)

Cada tarjeta (div.job-item) trae: titulo y URL en h2.title a, empresa y
ciudad en el primer h3.meta, fecha "16 de Octubre de 2026" en el segundo
h3.meta y descripcion parcial en p.description.
"""

from __future__ import annotations

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
)

BASE = "https://www.chiletrabajos.cl"
NOMBRE = "Chiletrabajos"
POR_PAGINA = 30


def _texto(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def _detalle(s, url: str) -> tuple[str, str, str]:
    """(descripcion completa, salario, titulo completo) de la pagina de detalle.

    El listado solo trae ~200 caracteres truncados y los titulos largos
    terminan en "..."; el detalle trae el texto completo (Chiletrabajos lo
    envia dentro de un comentario HTML), el sueldo real en div.botones-desc
    (icono de billete) y el titulo completo en el h1.
    """
    try:
        r = s.get(url, timeout=20)
    except Exception:
        return "", "", ""
    if r.status_code != 200:
        return "", "", ""
    soup = BeautifulSoup(r.text, "html.parser")

    titulo = _texto(soup.select_one("h1"))

    salario = ""
    for span in soup.select("div.botones-desc span.btn"):
        icono = span.select_one("i")
        clases = icono.get("class", []) if icono else []
        if any("money" in c for c in clases):
            salario = span.get_text(strip=True)

    descripcion = ""
    h3 = next((h for h in soup.select("h3.title")
               if "descripci" in h.get_text().lower()), None)
    if h3:
        for div in h3.find_all_next("div"):
            clases = div.get("class", [])
            if any("botones-desc" in c for c in clases):
                continue
            # El texto puede estar dentro de un comentario HTML
            texto = BeautifulSoup(
                str(div).replace("<!--", "").replace("-->", ""), "html.parser"
            ).get_text(" ", strip=True)
            if len(texto) > 80:
                descripcion = texto
                break
    return descripcion, salario, titulo


def _parsear_pagina(html: str, termino: str) -> list[Oferta]:
    soup = BeautifulSoup(html, "html.parser")
    ofertas = []
    for tarjeta in soup.select("div.job-item"):
        a_titulo = tarjeta.select_one("h2.title a")
        if not a_titulo:
            continue
        titulo = _texto(a_titulo)
        url = a_titulo.get("href", "")

        # Primer h3.meta: "Empresa, <a>Ciudad</a>"
        metas = tarjeta.select("h3.meta")
        empresa, ubicacion, fecha = "", "", ""
        if metas:
            a_ciudad = metas[0].find("a")
            ubicacion = _texto(a_ciudad)
            texto_meta = _texto(metas[0])
            empresa = texto_meta[: texto_meta.rfind(",")] if "," in texto_meta else texto_meta
        if len(metas) > 1:
            fecha = _texto(metas[1])

        descripcion = _texto(tarjeta.select_one("p.description"))

        ofertas.append(Oferta(
            titulo=titulo,
            empresa=empresa or "No indicado",
            ubicacion=ubicacion,
            # El listado no informa modalidad: se detecta en titulo/descripcion
            # (permite que las remotas de otras regiones pasen el filtro).
            modalidad=detectar_modalidad(f"{titulo} {descripcion}") or "No indicada",
            salario="A convenir",
            fecha_publicacion=fecha,
            experiencia="Detectada del texto del aviso",
            portal=NOMBRE,
            url=url,
            url_postulacion=url,
            buscado_con=termino,
            texto_ranking=descripcion,
        ))
    return ofertas


def buscar(terminos: list[str], region: str, incluir_remotos: bool,
           paginas: int, pausa_seg: float, dias_max: int | None = None,
           historial: dict[str, str] | None = None) -> list[Oferta]:
    """La categoria /trabajos/informatica ya es el area: no se itera por termino."""
    del terminos  # se busca una sola vez por categoria, no por termino
    s = crear_sesion()
    salud = SaludPortal(NOMBRE)
    descargar_desc = cargar_config().get("descargar_descripciones", True)
    vistas: set[str] = set()
    resultado: list[Oferta] = []
    detalles_intentados = 0
    detalles_fallidos = 0
    termino = "categoría informática"
    for pagina in range(1, paginas + 1):
        offset = (pagina - 1) * POR_PAGINA
        url = f"{BASE}/trabajos/informatica" + (f"/{offset}" if offset else "")
        try:
            r = s.get(url, timeout=20)
        except Exception as e:
            print(f"  [{NOMBRE}] error en {url}: {e}")
            continue
        if r.status_code != 200:
            print(f"  [{NOMBRE}] HTTP {r.status_code} en {url}")
            break
        nuevas = _parsear_pagina(r.text, termino)
        salud.registrar(len(nuevas))
        if not nuevas:
            if pagina == 1:
                # 0 tarjetas en la pagina 1 (siempre hay ~30) = HTML cambio.
                # SaludPortal no alcanza a alertar (MIN_PAGINAS=3 y aqui se
                # corta en la primera), asi que el aviso va aparte.
                print(f"  [{NOMBRE}] ALERTA: 0 ofertas en la pagina 1 con "
                      f"HTTP 200: el sitio pudo cambiar su HTML y el "
                      f"scraper necesita revision.")
            break
        for o in nuevas:
            clave = o.clave_dedup()
            if clave in vistas or not o.titulo:
                continue
            vistas.add(clave)
            if not es_puesto_it(o.titulo) or es_practica(o.titulo) \
                    or es_senior(o.titulo):
                continue
            if es_empresa_excluida(o.empresa):
                continue
            if not en_region_o_remoto(o.ubicacion, o.modalidad, region, incluir_remotos):
                continue
            if o.texto_ranking and not es_accesible(o.texto_ranking):
                continue
            if dias_max is not None:
                d = dias_desde_texto(o.fecha_publicacion)
                if d is not None and d > dias_max:
                    continue
            if historial is not None:
                o.nueva = clave not in historial
            if descargar_desc:
                # Descripcion + sueldo + titulo completos (1 request/oferta)
                desc, salario, titulo_full = _detalle(s, o.url)
                detalles_intentados += 1
                if not (desc or salario or titulo_full):
                    detalles_fallidos += 1
                pausa(pausa_seg)
                if titulo_full:
                    # El listado trunca los titulos largos con "...": el
                    # titulo real puede cambiar los filtros y la clave.
                    o.titulo = titulo_full
                    if not es_puesto_it(o.titulo) or es_practica(o.titulo) \
                            or es_senior(o.titulo):
                        continue
                    clave = o.clave_dedup()
                    if historial is not None:
                        o.nueva = clave not in historial
                if desc:
                    if not es_accesible(desc):
                        continue
                    o.texto_ranking = desc
                    if o.modalidad == "No indicada":
                        o.modalidad = detectar_modalidad(
                            f"{o.titulo} {desc}") or "No indicada"
                if salario:
                    o.salario = salario
                    if not pasa_sueldo_minimo(o.salario):
                        continue
            resultado.append(o)
        # Parada temprana: si TODA la pagina supera el limite de antiguedad,
        # las siguientes seran aun mas viejas (orden cronologico).
        if dias_max is not None:
            ds = [d for o in nuevas
                  if (d := dias_desde_texto(o.fecha_publicacion)) is not None]
            if ds and all(d > dias_max for d in ds):
                break
        pausa(pausa_seg)
    if detalles_intentados >= 5 and detalles_fallidos > detalles_intentados / 2:
        print(f"  [{NOMBRE}] ALERTA: {detalles_fallidos} de "
              f"{detalles_intentados} paginas de detalle fallaron: el sitio "
              f"pudo cambiar su HTML (se perdieron descripciones, sueldos "
              f"y titulos completos).")
    salud.revisar()
    return resultado
