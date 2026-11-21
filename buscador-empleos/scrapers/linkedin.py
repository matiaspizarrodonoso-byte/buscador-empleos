"""LinkedIn bloquea el scraping automatico (login + anti-bot).

En su lugar se generan links de busqueda PRE-FILTRADOS (nivel entrada,
ultima semana, Santiago o remotos, sin practicas) para abrir en el
navegador y postular con un clic. Van a la hoja "LinkedIn (links)".

Params de LinkedIn:
  f_E=2         -> nivel de entrada (entry level)
  f_TPR=r604800 -> publicados en la ultima semana
  f_WT=2        -> remoto
  NOT practica  -> excluye practicas profesionales (busqueda booleana)
"""

from __future__ import annotations

from urllib.parse import quote_plus

BASE = "https://www.linkedin.com/jobs/search/"


def generar_links(terminos: list[str]) -> list[dict]:
    links = []
    for termino in terminos:
        q = quote_plus(f"{termino.strip()} NOT practica NOT practicante")
        # Presencial/hibrido en Santiago, nivel entrada
        links.append({
            "termino": termino,
            "tipo": "Santiago (nivel entrada)",
            "url": f"{BASE}?keywords={q}&location=Santiago%2C%20Chile"
                   f"&f_E=2&f_TPR=r604800",
        })
        # Remoto en todo Chile, nivel entrada
        links.append({
            "termino": termino,
            "tipo": "Remoto Chile (nivel entrada)",
            "url": f"{BASE}?keywords={q}&location=Chile"
                   f"&f_E=2&f_TPR=r604800&f_WT=2",
        })
    return links
