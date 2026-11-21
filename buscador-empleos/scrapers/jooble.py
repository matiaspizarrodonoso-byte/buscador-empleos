"""Scraper de Jooble via API oficial (gratuita, requiere key).

POST https://jooble.org/api/{key}
Body: {"keywords": termino, "location": "Chile", "page": n}

Jooble agrega ofertas de varios portales chilenos (incluye avisos que no
estan en los otros scrapers). La key gratuita se obtiene en
https://jooble.org/api/about y va en config.json ("jooble_api_key").
Si esta vacia, el portal se omite con un aviso (no es un error).
"""

from __future__ import annotations

import re

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

BASE = "https://jooble.org/api"
NOMBRE = "Jooble"


def _limpiar_html(texto: str) -> str:
    """Los campos de Jooble vienen con tags HTML y entidades (&nbsp;, <b>...)."""
    t = re.sub(r"<[^>]+>", " ", texto or "")
    t = t.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t).strip()


def buscar(terminos: list[str], region: str, incluir_remotos: bool,
           paginas: int, pausa_seg: float, dias_max: int | None = None,
           historial: dict[str, str] | None = None) -> list[Oferta]:
    key = (cargar_config().get("jooble_api_key") or "").strip()
    if not key:
        print(f"  [{NOMBRE}] sin jooble_api_key en config.json: se omite "
              f"(key gratuita en https://jooble.org/api/about)")
        return []
    s = crear_sesion()
    s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    salud = SaludPortal(NOMBRE)
    vistas: set[str] = set()
    resultado: list[Oferta] = []
    for termino in terminos:
        for pagina in range(1, paginas + 1):
            body = {"keywords": termino, "location": "Chile", "page": pagina}
            try:
                r = s.post(f"{BASE}/{key}", json=body, timeout=25)
            except Exception as e:
                print(f"  [{NOMBRE}] error ({termino}, pag {pagina}): {e}")
                continue
            if r.status_code != 200:
                print(f"  [{NOMBRE}] HTTP {r.status_code} ({termino}, pag {pagina})")
                break
            jobs = r.json().get("jobs") or []
            salud.registrar(len(jobs))
            if not jobs:
                break
            for j in jobs:
                titulo = _limpiar_html(j.get("title") or "")
                snippet = _limpiar_html(j.get("snippet") or "")
                oferta = Oferta(
                    titulo=titulo,
                    empresa=_limpiar_html(j.get("company") or "") or "No indicado",
                    ubicacion=_limpiar_html(j.get("location") or ""),
                    # Jooble no informa modalidad: se detecta en el texto
                    # (permite que las remotas de otras regiones pasen).
                    modalidad=detectar_modalidad(f"{titulo} {snippet}") or "No indicada",
                    salario=_limpiar_html(j.get("salary") or "") or "A convenir",
                    # "updated" viene ISO con hora: se trunca a YYYY-MM-DD
                    fecha_publicacion=(j.get("updated") or "")[:10],
                    experiencia="Detectada del texto del aviso",
                    portal=NOMBRE,
                    url=j.get("link") or "",
                    url_postulacion=j.get("link") or "",
                    buscado_con=termino,
                    texto_ranking=snippet,
                )
                clave = oferta.clave_dedup()
                if clave in vistas or not titulo:
                    continue
                vistas.add(clave)
                if not es_puesto_it(titulo) or es_practica(titulo) \
                        or es_senior(titulo):
                    continue
                if es_empresa_excluida(oferta.empresa):
                    continue
                if not pasa_sueldo_minimo(oferta.salario):
                    continue
                if not en_region_o_remoto(oferta.ubicacion, oferta.modalidad,
                                          region, incluir_remotos):
                    continue
                if snippet and not es_accesible(snippet):
                    continue
                if dias_max is not None:
                    d = dias_desde_texto(oferta.fecha_publicacion)
                    if d is not None and d > dias_max:
                        continue
                if historial is not None:
                    oferta.nueva = clave not in historial
                resultado.append(oferta)
            pausa(pausa_seg)
        pausa(pausa_seg)
    salud.revisar()
    return resultado
