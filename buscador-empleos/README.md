# Buscador de empleos de Ingeniería en Informática (Chile)

Busca ofertas de trabajo de informática/IT con **requisito de hasta 1 año de
experiencia** en Computrabajo, Laborum, Trabajando.cl, **GetOnBoard**,
**Chiletrabajos** y **Jooble** (opcional, con key gratuita), y genera un
Excel (`empleos.xlsx`) con:

- **Hoja "Ofertas"**: título, empresa, ubicación, modalidad, salario, fecha,
  **columna "Afinidad"** (tecnologías de tu `stack` + bonus junior/sueldo/
  reciente, ordenada por afinidad descendente), link directo de postulación,
  columna "Postulado" (dropdown, **tus marcas se conservan entre corridas**)
  y columna "Nueva" (verde) para las ofertas que no habías visto.
- **Hoja "Mis postulaciones"** (acumulativa): lo que marques como
  "Enviado"/"Respondieron"/"Descartado" se consolida aquí con fecha y link,
  y **sobrevive aunque la oferta expire** en los portales. Tu seguimiento
  real de postulaciones.
- **Una hoja por portal**: Computrabajo, Laborum, Trabajando cl, GetOnBoard,
  Chiletrabajos y Jooble, para revisar cada fuente por separado.
- **Hojas "Indeed (links)" y "LinkedIn (links)"**: búsquedas pre-filtradas
  (nivel entrada, última semana, sin prácticas). Ambos portales bloquean el
  scraping automático, así que se abren en tu navegador con un clic.
- **Hoja "Plantilla email"**: texto listo para copiar/pegar al enviar tu CV.

Si `empleos.xlsx` está abierto en Excel al correr el script, la corrida no
se pierde: se guarda como `empleos_respaldo.xlsx` con un aviso.

## Requisitos

- Python 3.10+ instalado
- Dependencias: `pip install -r requirements.txt`

## Uso

```
python buscador.py              # búsqueda normal (marca ofertas nuevas)
python buscador.py --reiniciar  # olvida el historial de ofertas vistas
```

O doble clic en `ejecutar.bat`.

**Corrida diaria automática**: ejecuta `programar_tarea.bat` UNA vez. Crea
una tarea programada de Windows que corre el buscador todos los días a las
09:00 (salida en `log.txt`). Para eliminarla:
`schtasks /delete /tn "Buscador de Empleos" /f`

## Configuración (config.json)

| Campo | Descripción |
|---|---|
| `region` | Región para ofertas presenciales (ej. "R.Metropolitana") |
| `incluir_remotos` | Incluir ofertas remotas de cualquier lugar |
| `terminos` | Palabras de búsqueda (editables) |
| `paginas_por_busqueda` | Cuántas páginas revisar por término (1-5) |
| `pausa_segundos` | Pausa entre requests (se recomienda 3+) |
| `dias_maximo_publicacion` | Descartar ofertas más viejas que N días |
| `excluir_practicas` | Excluir prácticas profesionales/pasantías |
| `excluir_senior` | Excluir senior, lead, arquitecto, gerente, etc. |
| `descargar_descripciones` | Descargar el detalle de cada oferta en Computrabajo, Trabajando.cl y Chiletrabajos (descripción completa; en Chiletrabajos también sueldo real y título completo, cuyo listado trunca los títulos largos). Mejora los filtros, el dedup y el ranking; hace la corrida más lenta |
| `dias_purga_historial` | Días que se recuerda una oferta vista (def. 60); ofertas republicadas después vuelven a marcarse como nuevas |
| `sueldo_minimo` | Sueldo mínimo en CLP para ofertas con sueldo conocido (0 = desactivado) |
| `abrir_excel_al_terminar` | Abrir empleos.xlsx automáticamente al terminar |
| `palabras_excluidas` | Lista negra extra de títulos (sin tocar código) |
| `empresas_excluidas` | Lista negra de empresas (sin tocar código) |
| `stack` | Tus tecnologías: ordena las ofertas por afinidad |
| `jooble_api_key` | Key gratuita de la API de Jooble (jooble.org/api/about); vacía = portal omitido |
| `excel_salida` | Nombre del archivo Excel generado |
| `nombre`, `email`, ... | Tus datos para la plantilla de email |

## Tests

```
pytest
```

Corre los tests de filtros, scrapers, historial y Excel en `tests/`.
Correlos siempre que modifiques los filtros o la extracción de los portales.

## Notas

- **Computrabajo**: usa los filtros nativos "Sin Experiencia" e "1 año". El
  link de postulación es el de la oferta (los enlaces directos de "apply" del
  portal dan 404 sin sesión de navegador).
- **Laborum**: analiza el texto del aviso y descarta los que piden más de 1 año.
- **Trabajando.cl**: usa el filtro nativo "años de experiencia: hasta 1" y
  además filtra nativamente por tu región (así no se desperdician páginas
  en ofertas de otras zonas).
- **GetOnBoard**: API pública (getonbrd.com), portal 100% tech; trae sueldos
  y tags (se usan para el ranking por afinidad). La senioridad se filtra con
  el campo estructurado del aviso (solo "sin experiencia" y "junior"), más
  confiable que el título.
- **Chiletrabajos**: usa su categoría nativa `/trabajos/informatica`.
- **Jooble**: API oficial gratuita (agrega ofertas de varios portales);
  requiere `jooble_api_key` en config.json.
- **Parada temprana**: en Computrabajo y Chiletrabajos, si toda una página
  supera `dias_maximo_publicacion`, se deja de paginar (ahorra requests).
- **Indeed**: prohibido scrapear y bloqueado con Cloudflare, por eso solo se
  generan links pre-filtrados (con prácticas excluidas) para abrir en el navegador.
- **Salud de scrapers**: si un portal responde OK pero da 0 ofertas, el
  script avisa en consola (el sitio pudo cambiar su HTML/API).
- **Filtrado por área**: solo pasan puestos de informática/IT. Se rechazan
  prácticas profesionales y puestos de otras áreas (química, alimentos,
  mantención, eléctrica, telecomunicaciones, ventas, etc.), aunque el portal
  los muestre en la búsqueda. Ajustable con `excluir_practicas` y
  `palabras_excluidas` en `config.json`.
- El envío del CV se hace manualmente desde el link de cada oferta (evita
  baneos y captchas); usa la plantilla de email de la hoja correspondiente.
- No uses el script más de 2-3 veces al día para no ser bloqueado.
- Para agentes de IA: ver `AGENTS.md`.
