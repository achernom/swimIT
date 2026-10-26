"""Exporta la base SQLite a los datasets que consume el tablero.

Genera data/processed/resultados.json, resultados.csv y competencias.json.
Uso: python ingest/export_dashboard.py
"""
import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"

QUERY = """
SELECT r.result_id rid, e.meet_id competencia, m.start_date fecha, e.gender sexo,
       e.age_group categoria_original, e.distance_m distancia, e.stroke estilo,
       e.course pileta, e.division division, e.is_special especial, r.place puesto,
       r.swimmer_id nadador_id, s.full_name nadador, s.birth_year anio_nac,
       t.name equipo, r.age edad, r.seed_s inscripcion_s, r.time_s tiempo_s,
       r.status estado, r.fina_pts puntos_fina
FROM result r
JOIN event e USING (event_id)
JOIN meet m USING (meet_id)
JOIN swimmer s USING (swimmer_id)
JOIN team t USING (team_id)
WHERE e.is_relay = 0
ORDER BY m.start_date, e.event_num, e.gender, e.age_group, COALESCE(r.place, 999)
"""


def fmt_time(t):
    if t is None:
        return None
    m = int(t // 60)
    s = t - 60 * m
    return f"{m}:{s:05.2f}" if m else f"{s:.2f}"


def main():
    con = sqlite3.connect(OUT / "natacion_master.sqlite")
    con.row_factory = sqlite3.Row
    rows = [dict(x) for x in con.execute(QUERY)]
    for r in rows:
        ag = r["categoria_original"]
        r["categoria"] = "18-24" if ag in ("18-24", "20-24") else ag
        r["prueba"] = f"{r['distancia']} {r['estilo']}"
        r["tiempo"] = fmt_time(r["tiempo_s"])
    with open(OUT / "resultados.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    with open(OUT / "resultados.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    meets = [dict(x) for x in con.execute(
        "SELECT meet_id competencia, name nombre, city ciudad, start_date fecha, course pileta "
        "FROM meet ORDER BY start_date")]
    with open(OUT / "competencias.json", "w", encoding="utf-8") as f:
        json.dump(meets, f, ensure_ascii=False)
    print(f"{len(rows)} resultados y {len(meets)} competencias exportados a {OUT}")


if __name__ == "__main__":
    main()
