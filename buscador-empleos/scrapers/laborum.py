"""Scraper de Laborum Chile via API interna del frontend (grupo Jobint).

POST https://www.laborum.cl/api/avisos/searchNormalizado?pageSize=20&page={n}
Headers: x-site-id: BMCL
Body: {"filtros": [], "busquedaExtendida": false, "query": "<termino>",
       "tipoDetalle": "full", "withHome": false, "internacional": false}
"""

from __future__ import annotations

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
    pausa,
    slugificar,
)

BASE = "https://www.laborum.cl"
API = f"{BASE}/api/avisos/searchNormalizado"


def _a_oferta(aviso: dict, termino: str) -> Oferta:
    titulo = aviso.get("titulo") or ""
    id_aviso = aviso.get("id")
    detalle = aviso.get("detalle") or ""
    slug = slugificar(titulo)
    url = f"{BASE}/empleos/{slug}-{id_aviso}.html" if id_aviso else ""
    oferta = Oferta(
        titulo=titulo,
        empresa=aviso.get("empresa") or "No indicado",
        ubicacion=aviso.get("localizacion") or "",
        modalidad=aviso.get("modalidadTrabajo") or "No indicada",
        salario="A convenir",
        fecha_publicacion=aviso.get("fechaPublicacion") or "",
        experiencia="Detectada del texto del aviso",
        portal="Laborum",
        url=url,
        url_postulacion=url,
        buscado_con=termino,
    )
    oferta.texto_ranking = detalle
    return oferta, detalle


def buscar(terminos: list[str], region: str, incluir_remotos: bool,
           paginas: int, pausa_seg: float, dias_max: int | None = None,
           historial: dict[str, str] | None = None) -> list[Oferta]:
    s = crear_sesion()
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": BASE,
        "Referer": f"{BASE}/",
        "x-site-id": "BMCL",
    })
    salud = SaludPortal("Laborum")
    vistas: set[str] = set()
    resultado: list[Oferta] = []
    for termino in terminos:
        for pagina in range(0, paginas):
            body = {
                "filtros": [],
                "busquedaExtendida": False,
                "query": termino,
                "tipoDetalle": "full",
                "withHome": False,
                "internacional": False,
            }
            try:
                r = s.post(f"{API}?pageSize=20&page={pagina}", json=body, timeout=25)
            except Exception as e:
                print(f"  [Laborum] error ({termino}, pag {pagina}): {e}")
                continue
            if r.status_code != 200:
                print(f"  [Laborum] HTTP {r.status_code} ({termino}, pag {pagina})")
                break
            data = r.json()
            avisos = data.get("content") or []
            salud.registrar(len(avisos))
            if not avisos:
                break
            for aviso in avisos:
                oferta, detalle = _a_oferta(aviso, termino)
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
                if not es_accesible(detalle):
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
