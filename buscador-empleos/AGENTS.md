# AGENTS.md — Buscador de empleos de Ingeniería en Informática (Chile)

## Propósito

Buscar ofertas de trabajo de informática/IT en Chile, accesibles con **hasta 1
año de experiencia**, para una persona titulada de Ingeniería en Informática.
El resultado es un Excel (`empleos.xlsx`) con ofertas deduplicadas, marcadas
como nuevas respecto de corridas anteriores, con links directos para postular
manualmente.

## Arquitectura

```
buscador.py            # Orquestador: config -> scrapers -> dedup -> ranking -> excel -> historial
config.json            # Toda la configuración editable (sin tocar código)
scrapers/
  base.py              # Modelo Oferta + TODA la lógica de filtrado/ranking compartida
  computrabajo.py      # Scraping HTML (BeautifulSoup) + detalle por oferta
  laborum.py           # API interna del frontend (POST JSON)
  trabajando.py        # API interna del frontend (GET JSON) + filtro nativo de region
  getonboard.py        # API publica JSON (getonbrd.com, portal 100% tech)
  chiletrabajos.py     # Scraping HTML de la categoria /trabajos/informatica + detalle
  jooble.py            # API oficial (requiere jooble_api_key; se omite si esta vacia)
  indeed.py            # Solo genera links pre-filtrados (NO se scrapea)
  linkedin.py          # Solo genera links pre-filtrados (NO se scrapea)
excel.py               # Genera empleos.xlsx (Ofertas + hojas por portal + Mis
                       # postulaciones + links + Plantilla; respaldo si esta bloqueado)
tests/                 # Suite pytest (filtros, fechas, ranking, historial, excel)
historial.json         # {clave: fecha} de ofertas vistas (purga automatica)
plantilla_email.txt    # Plantilla para enviar el CV (placeholders {nombre}, etc.)
ejecutar.bat           # Atajo de doble clic para Windows (con pausa)
ejecutar_diario.bat    # Corrida silenciosa con log (para la tarea programada)
programar_tarea.bat    # Crea la tarea diaria de Windows (ejecutar 1 vez)
```

Flujo de datos: cada scraper devuelve `list[Oferta]` ya filtrada →
`buscador.py` deduplica por `Oferta.clave_dedup()` (título+empresa) →
puntúa afinidad con `puntuar_afinidad()` según `stack` del config y ordena →
`excel.generar_excel()` escribe las hojas → se guarda el historial.

## Reglas del proyecto (obligatorias)

1. **Nunca scrapear Indeed**: está bloqueado (Cloudflare) y prohibido por sus
   ToS. Solo se generan links de búsqueda pre-filtrados.
2. **Rate limiting respetuoso**: mantener `pausa_segundos >= 2` entre requests
   y no correr el script más de 2-3 veces al día. No agregar paralelismo.
3. **Postulación siempre manual**: el usuario postula desde el link del Excel.
   No automatizar login, formularios ni envío de CV (evita baneos/captchas).
4. **Todo el filtrado vive en `scrapers/base.py`**: los scrapers solo extraen
   datos y delegan en las funciones `es_*`. No duplicar lógica de filtros.
5. **Errores de red no son fatales**: un portal caído imprime un aviso y el
   resto continúa. No usar `raise` en el flujo normal de scraping.
6. **Código y mensajes en español**, siguiendo el estilo existente.

## Filtrado (scrapers/base.py)

Orden de aplicación por oferta (todos deben pasar):

| Filtro | Función | Qué hace |
|---|---|---|
| Área IT | `es_puesto_it(titulo)` | Lista blanca IT obligatoria; lista negra de otras áreas/falsos positivos (químico, alimentos, mantención, flota, rutas, producción, PLC/HMI, logística, CCTV, eléctrico, civil, telecomunicaciones, negocios, contenidos, organizacional, innovación, "de productos", etc.); lista de rescate para casos como "Civil Informático" o "Mantención de Sistemas (Python/PHP)". Al final aplica `palabras_excluidas` del config. Ojo: "programa" (plan) no cuenta como programación. |
| Prácticas | `es_practica(titulo)` | Rechaza prácticas/pasantías/internships si `excluir_practicas: true`. Los programas **trainee NO se excluyen** (son empleos formales). |
| Senioridad | `es_senior(titulo)` | Rechaza senior, semi senior, lead, líder, principal, staff, arquitecto, gerente, jefe, manager y consultor senior si `excluir_senior: true`. |
| Ubicación | `en_region_o_remoto(...)` | Región configurada o remoto (si `incluir_remotos`). Las claves se derivan de `region` + alias de ciudades (`_claves_region`); NO hay nada hardcodeado a Santiago. |
| Experiencia | `es_accesible(texto)` | Solo Laborum/Trabajando/GetOnBoard/Chiletrabajos/Jooble: rechaza avisos que piden > 1 año (Computrabajo usa su filtro nativo). |
| Antigüedad | `dias_desde_texto(...)` | Rechaza ofertas más viejas que `dias_maximo_publicacion`. Incluye fechas en español ("16 de Octubre de 2026"). "Hace X horas/minutos" y "hoy" = 0 días (ofertas frescas). |

Además:
- **Ranking por afinidad ponderado**: `puntuar_afinidad()` = nº de
  tecnologías del `stack` (config) en título + `texto_ranking`, +2 si el
  título es junior/trainee, +1 si informa sueldo, +1 si se publicó hace
  ≤ 2 días. La hoja "Ofertas" queda ordenada por puntaje descendente y la
  columna "Afinidad" muestra el detalle ("python, react, junior +2 (6)").
- **Salud de scrapers**: cada scraper usa `SaludPortal`; si un portal
  responde HTTP 200 pero da 0 ofertas en 3+ páginas, imprime una ALERTA
  (el sitio pudo cambiar su HTML/API).
- **Persistencia de Postulado**: `excel.generar_excel()` lee la hoja
  "Ofertas" del Excel anterior y restaura las marcas de la columna
  "Postulado" por clave `normalizar_clave(titulo, empresa)` antes de
  sobrescribir el archivo.
- **Hoja "Mis postulaciones" (acumulativa)**: las marcas Enviado/
  Respondieron/Descartado se consolidan ahí con fecha y link, y sobreviven
  aunque la oferta expire en los portales. Mientras la oferta siga activa,
  la marca de "Ofertas" manda sobre la columna Estado; Fecha y Notas se
  conservan entre corridas.
- **Excel bloqueado**: si `empleos.xlsx` está abierto en Excel
  (PermissionError), la corrida NO se pierde: se guarda como
  `empleos_respaldo.xlsx` con un aviso en consola.
- **Dedup tolerante**: `normalizar_clave()` ignora tildes, signos,
  marcadores de género ("(a)", "/a"), "full stack" vs "fullstack" y
  "jr" vs "junior": la misma oferta republicada con variantes no se
  duplica.
- **Historial con purga**: `historial.json` guarda {clave: fecha de última
  vista}; al cargar se descartan las entradas con más de
  `dias_purga_historial` días (ofertas republicadas vuelven a aparecer
  como nuevas; el archivo no crece sin límite). Acepta el formato antiguo
  (lista plana) y lo migra.
- **Lista negra de empresas**: `es_empresa_excluida()` descarta ofertas de
  las empresas de `empresas_excluidas` (config).
- **Sueldo mínimo**: `pasa_sueldo_minimo()` descarta ofertas con sueldo
  conocido bajo `sueldo_minimo` (config, 0 = desactivado; los sueldos no
  informados no se penalizan). Aplica en Computrabajo, GetOnBoard y
  Chiletrabajos.
- **Al terminar**: resumen de ofertas nuevas en consola y apertura
  automática del Excel (`abrir_excel_al_terminar`).

Casos de borde decididos con el usuario:
- **Se mantienen**: roles de datos/BI, soporte técnico, técnico/operador de
  informática, puestos trainee.
- **Se excluyen**: prácticas profesionales, puestos senior/alta jerarquía,
  telecomunicaciones (salvo rescate IT), "programador/desarrollador de
  mantención/flota/negocios/contenidos".

## Configuración (config.json)

- `terminos`: palabras de búsqueda (cada una genera requests en los 3 portales).
- `region` / `incluir_remotos`: filtro geográfico.
- `paginas_por_busqueda`: 1-5 recomendado (más páginas = más requests).
- `pausa_segundos`: mínimo 2, recomendado 3+.
- `dias_maximo_publicacion`: antigüedad máxima de las ofertas.
- `excluir_practicas`: true/false, gobierna `es_practica()`.
- `excluir_senior`: true/false, gobierna `es_senior()`.
- `descargar_descripciones`: true/false. Si está activo, Computrabajo y
  Chiletrabajos descargan el detalle de cada oferta final (descripción
  completa + sueldo). Más lento (~+1 request por oferta) pero mejora el
  filtro de experiencia y el ranking.
- `dias_purga_historial`: días que se recuerda una oferta vista (def. 60).
- `sueldo_minimo`: sueldo mínimo en CLP para aceptar ofertas con sueldo
  conocido (0 = desactivado).
- `abrir_excel_al_terminar`: true/false, abre empleos.xlsx al finalizar.
- `palabras_excluidas`: lista negra extra del usuario (substring, sin tildes),
  se aplica al final de `es_puesto_it()`.
- `empresas_excluidas`: lista negra de empresas (substring, sin tildes).
- `stack`: tecnologías del usuario; gobierna el ranking de afinidad y el
  orden de la hoja "Ofertas".
- `jooble_api_key`: key gratuita de la API de Jooble (jooble.org/api/about).
  Vacía = el portal se omite con aviso.
- `nombre`, `email`, etc.: datos para la hoja "Plantilla email".

Notas por portal:
- **GetOnBoard** (`getonbrd.com`, ojo: NO getonboard.com): API pública sin
  auth. `expand=["company","tags"]` trae empresa y tags (para el ranking).
  Las ciudades vienen como ids; se mapean una vez con `/api/v0/cities`.
  `links.public_url` funciona sin sesión. Sueldos vienen en miles de CLP.
  `per_page=100` (menos requests). La senioridad se filtra en cliente con el
  campo estructurado `seniority.data.id` (1=sin experiencia, 2=junior; la
  API ignora el parámetro `seniority` en la búsqueda, sondeado en vivo).
  `remote_modality`: "remote_local" (remoto dentro de Chile, ~1/3 de las
  ofertas) y cualquier valor con "remote" se mapea a "Remoto" — sin esto el
  filtro de ubicación descartaba las remotas.
- **Chiletrabajos**: NO itera por término; usa la categoría nativa
  `/trabajos/informatica` con paginación por offset de 30. Si
  `descargar_descripciones` está activo, descarga el detalle por oferta
  (descripción completa dentro de un comentario HTML + sueldo real de
  `div.botones-desc`). El listado no informa modalidad: se detecta con
  `detectar_modalidad()` en título/descripción (permite que las remotas de
  otras regiones pasen el filtro de ubicación). Parada temprana: si toda
  una página supera `dias_maximo_publicacion`, se deja de paginar.
- **Computrabajo**: el listado NO trae descripción. Si
  `descargar_descripciones` está activo, descarga el detalle por oferta
  (`div[div-link="oferta"]`) para aplicar `es_accesible` como segundo filtro
  de experiencia y alimentar el ranking por stack. Parada temprana igual
  que Chiletrabajos.
- **Trabajando.cl**: además del filtro nativo de experiencia
  (`aniosExpHasta=1`), filtra nativamente por región con el parámetro
  `region` (ids de la faceta "region" de la API, mapeados en `_REGION_ID`;
  ojo: NO es la numeración oficial, RM = 1). Así las páginas no se
  desperdician en ofertas de otras zonas.
- **Jooble**: API oficial (`POST https://jooble.org/api/{key}`), agrega
  ofertas de varios portales chilenos. Requiere `jooble_api_key` en
  config.json (gratuita en jooble.org/api/about); si está vacía se omite
  con un aviso (no es error). Los campos vienen con HTML; se limpian.
  Modalidad detectada con `detectar_modalidad()`.
- **Laborum** (explorado, sin cambios): su API no expone sueldo ni años de
  experiencia estructurados en el listado; el filtrado por texto sigue
  siendo la vía.

## Flujos de trabajo

**Ejecutar**: `python buscador.py` (o doble clic en `ejecutar.bat`).
**Reiniciar historial**: `python buscador.py --reiniciar` (vuelve a marcar
todas las ofertas como nuevas).
**Corrida diaria automática**: ejecutar `programar_tarea.bat` UNA vez
(crea la tarea de Windows a las 09:00 usando `ejecutar_diario.bat`, que
deja su salida en `log.txt`).
**Agregar una palabra a la lista negra**: editar `palabras_excluidas` en
`config.json` (no tocar código).
**Agregar un término de búsqueda**: editar `terminos` en `config.json`.

**Agregar un scraper nuevo**:
1. Crear `scrapers/nuevo.py` con `buscar(terminos, region, incluir_remotos,
   paginas, pausa_seg, dias_max, historial) -> list[Oferta]`.
2. Reusar `crear_sesion()`, `pausa()` y TODOS los filtros de `base.py`.
3. Importarlo en `buscador.py` y sumarlo a la cadena de ofertas.
4. Actualizar este archivo y el README.

## Pruebas

Suite con pytest en `tests/` (120+ casos): `test_filtros.py` (área IT,
prácticas, senioridad, fechas en español —incluidas "Hace X horas" = 0
días—, región derivada del config, `detectar_modalidad`, experiencia,
ranking), `test_mejoras.py` (dedup, empresas, sueldo mínimo, ranking,
historial) y `test_excel.py` (persistencia de Postulado, hoja "Mis
postulaciones", respaldo ante Excel bloqueado). Correr con `pytest` tras
cualquier cambio en los filtros de `base.py`.

Para validar un scraper: correr `python buscador.py` y revisar `empleos.xlsx`.
Los links de Computrabajo deben ser del tipo
`cl.computrabajo.com/ofertas-de-trabajo/...` (los links `candidato...apply`
dan 404 sin sesión de navegador; no usarlos).
