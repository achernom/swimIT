# Arquitectura propuesta

Documento completo y editable: [Natación Master Analytics — Diseño del sistema](https://claude.ai/artifact/A8F6ybSXWVAqdffBaVVguU).

## Stack elegido

| Capa | Tecnología | Por qué |
| --- | --- | --- |
| Frontend | Next.js + TypeScript + Tailwind | SSR para enlaces públicos compartibles |
| Estado en cliente | TanStack Query + Zustand | Caché por consulta, filtros compartidos entre gráficos |
| Visualización | D3 (a medida) + Apache ECharts (estándar, canvas) | Control fino y rendimiento con miles de puntos |
| API | FastAPI + Pydantic v2 + SQLAlchemy 2 (async) | Mismo lenguaje que la ingesta; OpenAPI genera el cliente TS |
| Tareas | Celery o Arq sobre Redis | Ingesta de PDF, refresco de vistas, resolución de identidad |
| Base de datos | PostgreSQL 16 + pg_trgm + vistas materializadas | Fuente de verdad, búsqueda difusa, agregados rápidos |
| Archivos | S3 compatible (S3, R2, MinIO) | PDFs originales para trazabilidad y reprocesamiento |
| Auth | OIDC (Auth.js o Keycloak) + JWT | Login social, roles, row-level security |
| Infra | Docker; Fly.io/Render al inicio, Kubernetes si escala | Barato al empezar, portable |

## Modelo de datos (objetivo, multideporte)

`sport` → `discipline` (estilo, distancia, pileta) · `meet` → `event` (sexo, categoría, división) ·
`athlete` + `athlete_alias` · `team` + `team_alias` · `result` · `relay_result`/`relay_leg` ·
`base_time` (récords para puntos FINA, versionados) · `source_file` · `collection`/`collection_item`/`share`.

El prototipo de este repo implementa un subconjunto en SQLite (`db/schema.sql`):
`meet`, `team`, `swimmer`, `event`, `result`, `relay_result`.

## Pipeline de ingesta

1. Detección de formato (idioma, pileta, columnas por página, capa de texto).
2. Extracción con `pdftotext -layout`; recorte por mitades en páginas a dos columnas.
3. Normalización de glifos de acentos dañados.
4. Parseo de encabezados de evento y filas de resultado (NS, DQ, DNF, exhibición).
5. Validación y revisión humana de filas dudosas.
6. Resolución de identidad: apellido + primer nombre + sexo + año de nacimiento (±1); prefijo para nombres truncados.
7. Confirmación y refresco de agregados.

## Puntos FINA

`puntos = 1000 × (T_base / T)³`, con récords mundiales aproximados de 2022 por sexo y pileta.
Referencia relativa para comparar estilos y distancias, no puntos oficiales.
