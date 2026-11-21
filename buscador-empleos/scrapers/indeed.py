"""Indeed Chile bloquea el scraping automatico (Cloudflare + ToS).

En su lugar se generan links de busqueda PRE-FILTRADOS (nivel entrada,
menos de 7 dias, en Santiago o remotos) para abrir en el navegador
y postular con un clic. Van a la hoja "Indeed" del Excel.
"""

from __future__ import annotations

BASE = "https://cl.indeed.com/jobs"

# sc=0kf%3Aexplvl(ENTRY_LEVEL) = filtro "Nivel de entrada" de Indeed
# fromage=7 = publicados en los ultimos 7 dias


def generar_links(terminos: list[str]) -> list[dict]:
    links = []
    # -practica -practicante excluye las practicas profesionales de los
    # resultados (el usuario busca empleos formales, no practicas).
    excl = "+-practica+-practicante"
    for termino in terminos:
        q = termino.strip().replace(" ", "+")
        # Presencial/hibrido en Santiago, nivel entrada
        links.append({
            "termino": termino,
            "tipo": "Santiago (presencial/híbrido)",
            "url": f"{BASE}?q={q}{excl}&l=Santiago&sc=0kf%3Aexplvl(ENTRY_LEVEL)&fromage=7",
        })
        # Remoto o cualquier comuna de Chile: busqueda de todo el pais con "remoto"
        links.append({
            "termino": termino,
            "tipo": "Remoto (todo Chile)",
            "url": f"{BASE}?q={q}+remoto{excl}&sc=0kf%3Aexplvl(ENTRY_LEVEL)&fromage=7",
        })
    return links
