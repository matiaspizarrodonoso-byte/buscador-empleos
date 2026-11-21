# Buscador de empleos IT junior (Chile)

Script en Python que busca ofertas de informática para perfiles con hasta 1 año
de experiencia y las consolida en un Excel (`empleos.xlsx`) ordenado por
afinidad con tu stack: deduplicación entre portales, ofertas nuevas destacadas
y seguimiento de postulaciones.

## Portales

Computrabajo, Laborum, Trabajando.cl, GetOnBoard, Chiletrabajos y Jooble.
Indeed y LinkedIn se incluyen como links pre-filtrados (no permiten scraping).

## Uso

```
pip install -r requirements.txt
python buscador.py
```

El código y la documentación completa están en la carpeta
[`buscador-empleos/`](buscador-empleos/).
