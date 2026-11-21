"""Modelo de datos y utilidades compartidas por todos los scrapers."""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_CONFIG = RAIZ / "config.json"
ARCHIVO_HISTORIAL = RAIZ / "historial.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# ---- Filtrado por área de informática ----

# Lista blanca: palabras que identifican un puesto de informática/IT.
# Ojo: "program" NO vale sola: tambien coincide con "programa" (plan),
# ej. "Programa Vacaciones de Verano" o "Programa de Entrenamiento".
_CLAVES_IT = re.compile(
    r"desarroll|programador|programaci[oó]n|programmer|software|"
    r"inform[aá]tic|sistemas?\b|\bti\b|\bit\b|"
    r"full\s?stack|backend|frontend|web\b|java\b|python\b|php\b|devops|"
    r"analista de sistemas|soporte t[eé]cnic|datos\b|data\b|cloud|"
    r"help\s?desk|service\s?desk|qa\b|tester|cibersegur|\bbi\b|"
    r"salesforce|power (platform|bi)|javascript|typescript|"
    r"\.net\b|react\b|angular\b|node\.?js\b|aws\b|azure\b|sap\b",
    re.IGNORECASE,
)

# Lista negra: palabras de OTRAS áreas que descartan el puesto aunque
# mencione una palabra de la lista blanca (ej. "Programador de Mantención"
# no programa código; "Desarrollador de Negocios" es ventas).
_CLAVES_NO_IT = re.compile(
    r"qu[ií]mic|alimentos?|el[eé]ctr|mec[aá]nic|industrial|"
    r"miner[ií]a|minero|\bmina\b|agr[oó]nom|forestal|ambiental|"
    r"sanitari|construcci[oó]n|\bobras?\b|estructur|calibraci[oó]n|"
    r"telecomunicaciones|cctv|ventas?|comercial|negocios|marketing|"
    r"transporte|flota|\brutas?\b|mantenci[oó]n|mantenimiento|prevenci[oó]n|"
    r"bodega|contenidos|biolog|\bcivil\b|log[ií]stic|producci[oó]n|"
    r"\bplc\b|\bhmi\b|organizacional|innovaci[oó]n|de productos?\b",
    re.IGNORECASE,
)

# Palabras que RESCATAN el puesto aunque contenga una palabra de la lista
# negra (ej. "Civil Informático", "Mantención de Sistemas (Python/PHP)")
_CLAVES_RESCATE_IT = re.compile(
    r"software|computaci[oó]n|inform[aá]tic|python|java\b|php|"
    r"javascript|typescript|\.net\b|react|angular|node\.?js|"
    r"full\s?stack|backend|frontend|devops|cloud|aws\b|azure\b|"
    r"sap\b|salesforce|power (platform|bi)",
    re.IGNORECASE,
)

_CONFIG_CACHE: dict | None = None


def _config() -> dict:
    """config.json cacheado (evita releer el archivo por cada oferta)."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = cargar_config() if ARCHIVO_CONFIG.exists() else {}
    return _CONFIG_CACHE


def es_puesto_it(texto: str) -> bool:
    """True si el título corresponde al área de informática/IT.

    Orden: lista blanca obligatoria -> rescate anula lista negra ->
    lista negra propia -> palabras_excluidas del config.json.
    """
    t = quitar_tildes((texto or "").lower())
    if not _CLAVES_IT.search(t):
        return False
    if _CLAVES_RESCATE_IT.search(t):
        return True
    if _CLAVES_NO_IT.search(t):
        return False
    for palabra in _config().get("palabras_excluidas", []):
        if quitar_tildes(str(palabra).lower()) in t:
            return False
    return True


# ---- Exclusión de prácticas profesionales ----

_CLAVES_PRACTICA = re.compile(r"practic|pasant|internship", re.IGNORECASE)


def es_practica(texto: str) -> bool:
    """True si el título es una práctica/pasantía y el usuario pidió excluirlas."""
    if not _config().get("excluir_practicas", True):
        return False
    return bool(_CLAVES_PRACTICA.search(quitar_tildes(texto or "")))


def es_empresa_excluida(empresa: str) -> bool:
    """True si la empresa está en 'empresas_excluidas' del config.json."""
    e = quitar_tildes((empresa or "").lower())
    for x in _config().get("empresas_excluidas", []):
        x = quitar_tildes(str(x).strip().lower())
        if x and x in e:
            return True
    return False


def pasa_sueldo_minimo(salario: str) -> bool:
    """True si el sueldo es desconocido o su mínimo >= 'sueldo_minimo' del config.

    Parsea el primer monto del texto ("$1.300.000 - $2.200.000" -> 1300000).
    Los sueldos no informados ("A convenir", "Negociable") no se penalizan.
    """
    minimo = _config().get("sueldo_minimo", 0)
    if not minimo:
        return True
    m = re.search(r"(\d[\d.]*)", salario or "")
    if not m:
        return True
    try:
        valor = int(m.group(1).replace(".", ""))
    except ValueError:
        return True
    return valor >= int(minimo)


# ---- Exclusión de puestos senior / alta jerarquía ----

_CLAVES_SENIOR = re.compile(
    r"senior|semi\s?senior|\bsr\b|\bssr\b|\blead\b|\blider\b|lider\b|"
    r"principal|staff\b|arquitect|gerent|\bjefe|manager|consultor senior",
    re.IGNORECASE,
)


def es_senior(texto: str) -> bool:
    """True si el título indica alta senioridad y el usuario pidió excluirla."""
    if not _config().get("excluir_senior", True):
        return False
    return bool(_CLAVES_SENIOR.search(quitar_tildes(texto or "")))


def cargar_config() -> dict:
    with open(ARCHIVO_CONFIG, encoding="utf-8-sig") as f:
        return json.load(f)


def crear_sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "es-CL,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s


def pausa(segundos: float) -> None:
    time.sleep(segundos)


def quitar_tildes(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def slugificar(texto: str) -> str:
    t = quitar_tildes((texto or "").lower())
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t


@dataclass
class Oferta:
    titulo: str = ""
    empresa: str = ""
    ubicacion: str = ""
    modalidad: str = ""
    salario: str = ""
    fecha_publicacion: str = ""
    experiencia: str = ""
    portal: str = ""
    url: str = ""
    url_postulacion: str = ""
    buscado_con: str = ""
    nueva: bool = True
    # Texto extra para el ranking por stack (descripcion/tags del aviso)
    texto_ranking: str = ""
    # Se calculan en buscador.py despues de deduplicar
    puntaje: int = 0
    afinidad: str = ""

    def clave_dedup(self) -> str:
        return normalizar_clave(self.titulo, self.empresa)


def normalizar_clave(titulo: str, empresa: str) -> str:
    """Clave unica de oferta: titulo|empresa normalizados.

    Tolerante a variantes comunes: tildes, signos, marcadores de genero
    ("(a)", "/a"), "full stack" vs "fullstack", "jr" vs "junior".
    La usan Oferta.clave_dedup() y excel.py (persistencia de la columna
    Postulado entre corridas); deben mantenerse identicas.
    """
    t = quitar_tildes((titulo or "").lower())
    t = re.sub(r"\((a|o)\)|\s?/(a|o)\b", " ", t)  # "(a)", "(o)", "/a", "/o"
    t = t.replace("full stack", "fullstack")
    t = re.sub(r"\bjr\b", "junior", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    e = re.sub(r"[^a-z0-9]+", " ", quitar_tildes((empresa or "").lower()))
    e = re.sub(r"\s+", " ", e).strip()
    return f"{t}|{e}"


def puntuar_afinidad(oferta: Oferta, stack: list[str]) -> tuple[int, str]:
    """Puntaje de afinidad: coincidencias con el stack + extras ponderados.

    +2 si el titulo es junior/trainee, +1 si informa sueldo,
    +1 si se publico hace <= 2 dias.
    Devuelve (puntaje, detalle legible para la columna Afinidad).
    """
    texto = quitar_tildes(f"{oferta.titulo} {oferta.texto_ranking}".lower())
    coincidencias = []
    for tec in stack:
        t = quitar_tildes(str(tec).strip().lower())
        if t and re.search(rf"\b{re.escape(t)}\b", texto):
            coincidencias.append(t)
    puntaje = len(coincidencias)
    extras = []
    titulo = quitar_tildes((oferta.titulo or "").lower())
    if re.search(r"junior|\bjr\b|trainee", titulo):
        puntaje += 2
        extras.append("junior +2")
    if oferta.salario and oferta.salario not in ("A convenir", "Negociable"):
        puntaje += 1
        extras.append("sueldo +1")
    dias = dias_desde_texto(oferta.fecha_publicacion)
    if dias is not None and dias <= 2:
        puntaje += 1
        extras.append("reciente +1")
    return puntaje, ", ".join(coincidencias + extras)


class SaludPortal:
    """Detecta scrapers 'rotos': el portal responde HTTP 200 pero nunca da ofertas.

    Uso: registrar cada pagina exitosa con registrar(); al final llamar revisar(),
    que avisa si hubo suficientes paginas OK y cero ofertas (el sitio pudo
    cambiar su HTML/API).
    """

    MIN_PAGINAS = 3

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.paginas_ok = 0
        self.ofertas = 0

    def registrar(self, ofertas_en_pagina: int) -> None:
        self.paginas_ok += 1
        self.ofertas += ofertas_en_pagina

    def revisar(self) -> None:
        if self.paginas_ok >= self.MIN_PAGINAS and self.ofertas == 0:
            print(f"  [{self.nombre}] ALERTA: 0 ofertas en {self.paginas_ok} "
                  f"paginas con HTTP 200: el sitio pudo cambiar su HTML/API "
                  f"y el scraper necesita revision.")


# ---- Filtrado de experiencia (respaldo basado en texto) ----

_PATRONES_ANIOS = [
    (r"(?:m[aá]s de)\s*(\d{1,2})\s*(?:a[ñn]os?)", "min"),
    (r"(\d{1,2})\s*\+?\s*(?:a[ñn]os?)\s*de\s*experiencia", "min"),
    (r"experiencia(?:\s*(?:de|demostrada|previa|m[ií]nima))?\s*:?\s*(?:de\s*)?(\d{1,2})\s*(?:a[ñn]os?)", "min"),
]

# Ojo: "practicante"/"práctica" NO van aquí a propósito; las prácticas
# se excluyen con es_practica(), no se promueven como puestos accesibles.
_SENALES_JUNIOR = [
    "sin experiencia", "no requiere experiencia", "sin experiencia previa",
    "junior", r"jr\b", "trainee",
    "reci[eé]n titulado", "recien titulado", "primer empleo",
    "estudiante", "sin experiencia requerida",
]


def anios_exigencia(texto: str) -> int | None:
    """Años de experiencia que exige el aviso, o None si no los menciona."""
    if not texto:
        return None
    t = texto.lower()
    for patron, _tipo in _PATRONES_ANIOS:
        m = re.search(patron, t)
        if m:
            return int(m.group(1))
    return None


def es_accesible(texto: str, limite: int = 1) -> bool:
    """True si el aviso parece accesible con 'limite' años de experiencia o menos."""
    if texto:
        t = texto.lower()
        for senal in _SENALES_JUNIOR:
            if re.search(senal, t):
                return True
    anios = anios_exigencia(texto)
    if anios is None:
        return True
    return anios <= limite


# ---- Ubicación y modalidad ----

# Alias de ciudades por region: los portales suelen poner la ciudad ("Viña
# del Mar") sin nombrar la region. La clave se busca como substring de la
# region configurada (sin tildes), ej. "ohiggins" calza con
# "Libertador Bernardo O'Higgins".
_ALIAS_REGION = {
    "metropolitana": ("metropolitan", "santiago"),
    "valparaiso": ("vina del mar", "quilpue", "villa alemana", "san antonio", "quillota"),
    "biobio": ("concepcion", "talcahuano", "chillan", "los angeles"),
    "ohiggins": ("rancagua", "machali", "san fernando"),
    "maule": ("talca", "curico", "linares"),
    "araucania": ("temuco", "padre las casas", "villarrica"),
    "los lagos": ("puerto montt", "osorno", "puerto varas", "castro"),
    "los rios": ("valdivia", "la union"),
    "coquimbo": ("la serena", "ovalle"),
    "antofagasta": ("calama",),
    "tarapaca": ("iquique", "alto hospicio"),
    "arica": ("parinacota",),
    "nuble": ("chillan",),
    "atacama": ("copiapo", "vallenar"),
    "aysen": ("coyhaique",),
    "magallanes": ("punta arenas",),
}


def _claves_region(region: str) -> tuple[str, ...]:
    """Palabras clave (sin tildes, minúsculas) que identifican la region.

    Incluye el nombre de la region ("metropolitana") mas los alias de sus
    ciudades ("santiago"). Antes "santiago" estaba hardcodeado y pasaba
    siempre, aunque el usuario configurara otra region.
    """
    r = quitar_tildes((region or "").lower())
    r = re.sub(r"^r\.?\s*", "", r).strip()  # "R.Metropolitana" -> "metropolitana"
    claves = [r] if r else []
    for clave_region, alias in _ALIAS_REGION.items():
        if clave_region in r:
            claves.extend(alias)
    return tuple(dict.fromkeys(claves))


def en_region_o_remoto(ubicacion: str, modalidad: str, region: str, incluir_remotos: bool) -> bool:
    u = quitar_tildes((ubicacion or "").lower())
    m = quitar_tildes((modalidad or "").lower())
    en_region = any(c in u for c in _claves_region(region))
    es_remoto = any(c in m for c in ("remoto", "teletrabajo", "home office")) or "remoto" in u
    return en_region or (incluir_remotos and es_remoto)


def detectar_modalidad(texto: str) -> str:
    """Modalidad detectada en un texto: "Remoto" / "Híbrido" / "" (no indicada).

    La usan portales que no informan la modalidad estructurada
    (Chiletrabajos, Jooble): detectarla en el titulo/descripcion permite que
    las ofertas remotas de otras regiones pasen el filtro de ubicacion.
    """
    t = quitar_tildes((texto or "").lower())
    if any(p in t for p in ("remoto", "teletrabajo", "home office", "remote")):
        return "Remoto"
    if "hibrid" in t:
        return "Híbrido"
    return ""


# ---- Fechas relativas (ej. "Hace 2 horas", "Desde ayer") ----

def dias_desde_texto(texto: str) -> int | None:
    if not texto:
        return None
    t = quitar_tildes(texto.lower())
    m = re.search(r"hace\s+(\d+)\s+(minuto|hora|dia|semana|mes)", t)
    if m:
        n, unidad = int(m.group(1)), m.group(2)
        # Minutos/horas = publicada hoy (0 dias). Ojo: antes caian en el
        # "else" de meses (n*30) y el filtro de antiguedad descartaba las
        # ofertas mas frescas.
        if unidad.startswith(("minuto", "hora")):
            return 0
        return n if unidad.startswith("dia") else (n * 7 if unidad.startswith("semana") else n * 30)
    if "ayer" in t:
        return 1
    if "hoy" in t:
        return 0
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", (texto or "").strip())
    if m:
        try:
            f = datetime.strptime(texto.strip()[:10], "%d-%m-%Y")
            return (datetime.now() - f).days
        except ValueError:
            return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (texto or "").strip())
    if m:
        try:
            f = datetime.strptime(texto.strip()[:10], "%Y-%m-%d")
            return (datetime.now() - f).days
        except ValueError:
            return None
    # Fecha en espanol: "16 de Octubre de 2026" (Chiletrabajos)
    m = re.match(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", t.strip())
    if m and m.group(2) in _MESES_ES:
        try:
            f = datetime(int(m.group(3)), _MESES_ES[m.group(2)], int(m.group(1)))
            return (datetime.now() - f).days
        except ValueError:
            return None
    return None


_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}


# ---- Historial de ofertas ya vistas (con fecha de ultima vista) ----

def cargar_historial() -> dict[str, str]:
    """{clave: fecha YYYY-MM-DD} de ofertas vistas, purgando las antiguas.

    Acepta el formato antiguo (lista plana de claves) y lo migra con la
    fecha de hoy. Las entradas con mas de 'dias_purga_historial' dias se
    descartan: una oferta republicada vuelve a marcarse como nueva y el
    archivo no crece sin limite.
    """
    if not ARCHIVO_HISTORIAL.exists():
        return {}
    try:
        with open(ARCHIVO_HISTORIAL, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(data, list):  # formato antiguo -> migrar
        hoy = datetime.now().strftime("%Y-%m-%d")
        data = {clave: hoy for clave in data}
    limite = datetime.now() - timedelta(
        days=int(_config().get("dias_purga_historial", 60)))
    historial = {}
    for clave, fecha in (data or {}).items():
        try:
            vista = datetime.strptime(fecha, "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if vista >= limite:
            historial[clave] = fecha
    return historial


def guardar_historial(historial: dict[str, str]) -> None:
    with open(ARCHIVO_HISTORIAL, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(historial.items())), f, ensure_ascii=False, indent=0)
