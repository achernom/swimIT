# Natación Master Analytics

Prototipo de una plataforma para procesar resultados de competencias de natación master
(PDFs de HY-TEK Meet Manager) y analizarlos con visualizaciones por competencia, por nadador
y a lo largo del tiempo.

**Estado actual:** 7 competencias (2019–2023), 8.958 resultados individuales,
1.523 nadadores únicos (352 en 2 o más torneos) y 236 equipos.

## Estructura

```
data/raw/           PDFs originales de resultados
data/processed/     Base SQLite y datasets derivados (JSON / CSV)
db/schema.sql       Esquema relacional (SQLite, portable a PostgreSQL)
ingest/parse.py     Parser unificado PDF -> base normalizada
ingest/export_dashboard.py   Base -> datasets del tablero
dashboard/index.html         Tablero (D3); misma página que el tablero publicado en Claude
dashboard/dash-shim.js       Implementación mínima del API `dash` para correrlo fuera de Claude
dashboard/standalone.html    Versión local del tablero
docs/ARQUITECTURA.md         Stack y diseño propuestos para la plataforma completa
```

## Uso

Requisitos: Python 3.10+ y `poppler-utils` (`pdftotext`, `pdfinfo`).

```bash
make data    # re-procesa data/raw/*.pdf y regenera data/processed/
make serve   # abre http://localhost:8000/dashboard/standalone.html
```

Para agregar una competencia: copiar el PDF a `data/raw/`, sumar una entrada a la lista
`MEETS` en `ingest/parse.py` (id, archivo, nombre, ciudad, fecha, columnas por página) y correr `make data`.

## Tablero

- **Competencia:** indicadores, pirámide edad × sexo, distribución de tiempos por categoría,
  rendimiento vs. edad con marginales, boxplots por categoría (sexo o libres/federados),
  medallero por equipo, tamaño de equipo vs. nivel, tiempo final vs. inscripción, ranking.
- **Nadadores:** evolución de puntos FINA (con comparación), tiempos por prueba, percentil en su serie, historial.
- **Evolución global:** participación, curva de edad, nivel por categoría y competencia,
  equipos en el tiempo, fidelización.

## Método y limitaciones

- **Identidad:** los nadadores se unifican por apellido normalizado, primer nombre, sexo y año de
  nacimiento inferido (±1 año). Puede haber homónimos fusionados o grafías distintas sin unir
  (por ejemplo «Corbalan» / «Corvalan»).
- **Buenos Aires 2019** publica nombres truncados a 15 caracteres y equipos en siglas.
- **Rosario 2022** tiene nombres y equipos ausentes de la capa de texto; se completaron a partir de la imagen del PDF.
- **Puntos FINA:** `1000 × (T_base / T)³` con récords mundiales aproximados de 2022; referencia relativa, no oficial.
- Categorías 18-24 y 20-24 agrupadas como 18-24. Golden race y finales open 20-100 excluidas del análisis por categoría.
- Los relevos están en la base (`relay_result`) pero todavía no en el tablero.

## Datos personales

Los PDFs contienen nombres, edades y clubes de deportistas. Son resultados publicados por los
organizadores, pero conviene evaluar si el repositorio debe ser privado.
