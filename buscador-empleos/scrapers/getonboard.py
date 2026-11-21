"""Scraper de GetOnBoard via API pública (sin autenticación, portal 100% tech).

GET https://www.getonbrd.com/api/v0/search/jobs
Params: query, country_code=cl, lang=es, expand=["company","tags"], per_page, page

- links.public_url  -> link directo de la oferta (funciona sin sesión)
- published_at      -> fecha en timestamp unix
- remote_modality   -> "fully_remote" / "hybrid" / "no_remote"
- Las ciudades vienen como ids; se resuelven una vez via /api/v0/cities.
"""

from __future__ import annotations

from datetime import datetime

from .base import (
    Oferta,
    SaludPortal,
    crear_sesion,
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

BASE = "https://www.getonbrd.com"
API = f"{BASE}/api/v0/search/jobs"
API_CIUDADES = f"{BASE}/api/v0/cities"
NOMBRE = "GetOnBoard"

# Taxonomia nativa de seniority del portal (/api/v0/seniorities):
# 1 = Sin experiencia, 2 = Junior, 3 = Semi Senior, 4 = Senior, 5 = Expert.
# La API ignora el parametro "seniority" en la busqueda (sondeado en vivo),
# asi que se filtra en cliente con el campo estructurado del aviso, mas
# confiable que adivinar por el titulo.
_SENIORITY_OK = (1, 2)


def _mapa_ciudades(s) -> dict:
    """id -> nombre de ciudad (Chile). Un solo request por corrida."""
    try:
        r = s.get(API_CIUDADES, params={"per_page": 100}, timeout=20)
        if r.status_code != 200:
            return {}
        return {
            int(c["id"]): c["attributes"].get("name", "")
            for c in r.json().get("data", [])
            if c.get("attributes", {}).get("country") == "Chile"
        }
    except Exception:
        return {}


def _a_oferta(item: dict, termino: str, ciudades: dict) -> tuple[Oferta, str]:
    a = item.get("attributes") or {}
    titulo = a.get("title") or ""

    empresa = ""
    comp = a.get("company") or {}
    if isinstance(comp, dict):
        attrs = ((comp.get("data") or {}).get("attributes") or {})
        empresa = attrs.get("name") or ""

    url = ((item.get("links") or {}).get("public_url")) or ""

    # Modalidad: no_remote/hybrid/fully_remote/remote_local/remote_global...
    # Ojo: "remote_local" (remoto dentro de Chile) es ~1/3 de las ofertas;
    # sin este mapeo quedaba como "remote_local" y el filtro de ubicacion
    # descartaba esas ofertas remotas.
    remoto_mod = (a.get("remote_modality") or "").lower()
    modalidad = {
        "no_remote": "Presencial",
        "hybrid": "Híbrido",
    }.get(remoto_mod, "")
    if not modalidad:
        modalidad = "Remoto" if "remote" in remoto_mod else (remoto_mod or "No indicada")

    # Ubicación: ids de ciudad -> nombre (si el mapeo cargo)
    nombres = []
    for ref in ((a.get("location_cities") or {}).get("data") or []):
        nombre = ciudades.get(int(ref.get("id", 0)), "")
        if nombre:
            nombres.append(nombre)
    ubicacion = ", ".join(sorted(set(nombres))) or "Chile"

    # Fecha: published_at es timestamp unix
    fecha = ""
    ts = a.get("published_at")
    if ts:
        fecha = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")

    # Salario (0 = no informado). La API devuelve miles de CLP
    # (ej. 1800 = $1.800.000); se convierte a pesos si el valor es chico.
    min_s, max_s = a.get("min_salary"), a.get("max_salary")
    salario = ""
    if min_s and max_s:
        if min_s < 100_000:
            min_s, max_s = min_s * 1000, max_s * 1000
        salario = f"${min_s:,.0f} - ${max_s:,.0f}".replace(",", ".")

    # Descripción + tags: texto para filtro de experiencia y ranking por stack
    descripcion = a.get("description") or ""
    tags = []
    for tag in ((a.get("tags") or {}).get("data") or []):
        attrs = tag.get("attributes") or {}
        tags.append(attrs.get("name") or "")
        tags.append(attrs.get("keywords") or "")
    texto_ranking = f"{descripcion} {' '.join(tags)}"

    oferta = Oferta(
        titulo=titulo,
        empresa=empresa or "No indicado",
        ubicacion=ubicacion,
        modalidad=modalidad,
        salario=salario or "A convenir",
        fecha_publicacion=fecha,
        experiencia="Detectada del texto del aviso",
        portal=NOMBRE,
        url=url,
        url_postulacion=url,
        buscado_con=termino,
        texto_ranking=texto_ranking,
    )
    return oferta, descripcion


def buscar(terminos: list[str], region: str, incluir_remotos: bool,
           paginas: int, pausa_seg: float, dias_max: int | None = None,
           historial: dict[str, str] | None = None) -> list[Oferta]:
    s = crear_sesion()
    s.headers.update({"Accept": "application/json", "Referer": f"{BASE}/"})
    salud = SaludPortal(NOMBRE)
    ciudades = _mapa_ciudades(s)
    vistas: set[str] = set()
    resultado: list[Oferta] = []
    for termino in terminos:
        for pagina in range(1, paginas + 1):
            params = {
                "query": termino,
                "country_code": "cl",
                "lang": "es",
                "expand": '["company","tags"]',
                "per_page": 100,
                "page": pagina,
            }
            try:
                r = s.get(API, params=params, timeout=25)
            except Exception as e:
                print(f"  [{NOMBRE}] error ({termino}, pag {pagina}): {e}")
                continue
            if r.status_code != 200:
                print(f"  [{NOMBRE}] HTTP {r.status_code} ({termino}, pag {pagina})")
                break
            items = r.json().get("data") or []
            salud.registrar(len(items))
            if not items:
                break
            for item in items:
                oferta, descripcion = _a_oferta(item, termino, ciudades)
                clave = oferta.clave_dedup()
                if clave in vistas or not oferta.titulo:
                    continue
                vistas.add(clave)
                if not es_puesto_it(oferta.titulo) or es_practica(oferta.titulo) \
                        or es_senior(oferta.titulo):
                    continue
                # Senioridad estructurada del aviso (si la informa)
                sen = (((item.get("attributes") or {}).get("seniority") or {})
                       .get("data") or {}).get("id")
                try:
                    if sen is not None and int(sen) not in _SENIORITY_OK:
                        continue
                except (TypeError, ValueError):
                    pass
                if es_empresa_excluida(oferta.empresa):
                    continue
                if not pasa_sueldo_minimo(oferta.salario):
                    continue
                if not en_region_o_remoto(oferta.ubicacion, oferta.modalidad,
                                          region, incluir_remotos):
                    continue
                if descripcion and not es_accesible(descripcion):
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
