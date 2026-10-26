"""Parser unificado de resultados HY-TEK Meet Manager (PDF -> modelo normalizado).

Soporta: español/inglés, curso largo/corto, columnas dobles (San Luis),
nombres truncados (Buenos Aires 2019), glifos de acentos rotos y capas de
texto incompletas (Rosario 2022).
"""
import re, subprocess, unicodedata, json, sqlite3, os, sys
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
UP = str(Path(os.environ.get("NM_RAW_DIR", ROOT / "data" / "raw"))) + "/"
OUT = Path(os.environ.get("NM_OUT_DIR", ROOT / "data" / "processed"))
SCHEMA = ROOT / "db" / "schema.sql"
MEETS = [
    # id, archivo, nombre, ciudad, fecha, columnas
    ("BA19",  "xxxx_BuenosAires_2_Resultados-del-M2O-Master-Open-Buenos-Aires-2019.pdf", "Master Open Buenos Aires 2019 (2ª ed.)", "Buenos Aires", "2019-11-16", 1),
    ("MDP19", "xxxx_MarDelPlata_1_Resultados-del-M2O-Master-Open-Mar-del-Plata.pdf", "Open Master Mar del Plata 2019", "Mar del Plata", "2019-08-31", 1),
    ("SL22",  "xxxx_SanLuis_4_Resultados-M2O-San-Luis.pdf", "M2O Master Open San Luis 2022", "San Luis", "2022-05-14", 2),
    ("MH22",  "xxxx_MonteHermoso_1_Resultados-M2O-Máster-Open-Serie-Monte-Hermoso.pdf", "M2O Master Open Monte Hermoso 2022", "Monte Hermoso", "2022-06-25", 1),
    ("MDP22", "xxxx_MarDelPlata_xpert_Resultados-Serie-Mar-del-Plata.pdf", "M2O Master Open Mar del Plata 2022", "Mar del Plata", "2022-09-24", 1),
    ("ROS22", "2022_Rosario_x_Resultados-Copa-Pool-Xpert-Rosario.pdf", "M2O Master Open Rosario 2022", "Rosario", "2022-12-09", 1),
    ("SM23",  "xxxx_SanMartin_x_Resultados-M2O-Máster-Open-Serie-SM.pdf", "Master Open San Martín 2023", "San Martín", "2023-06-10", 1),
]

# Nombres cuyo texto no está en la capa de texto del PDF de Rosario (se ven sólo en la imagen)
ROS_MISSING = {
    (21, "Municipalidad Almirante Brown"): "Maidana, Sofi",
    (20, "Club Atletico Las Palmas"): "Cordoba, Delfin",
    (38, "Club Atletico River Plate"): "Garrone, Josefin",
    (28, "Atletico Echague Club"): "Martin, Josefin",
    (28, "Club Atletico Adelia Maria"): "Schroter, Sofi",
    (33, "Noa Team Master"): "Clemente, Sofi",
    (46, "Asoc Litoral DE Natacion"): "Keller, Sofi",
}

def fix_glyphs(s):
    s = unicodedata.normalize("NFC", s.replace("ı́", "í"))
    s = s.replace("nñ", "ñ").replace("Nñ", "Ñ")
    s = re.sub(r"ñ (?=[a-z])", "ñ", s)
    s = re.sub(r"([áéíóú])[áé]", r"\1", s)
    acc = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}
    s = re.sub(r"([aeiou])[áé] ?(?=[a-z])", lambda m: acc[m.group(1)], s)
    return s

def strip_acc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def title_name(s):
    parts = re.split(r"(\s+|-)", s.strip())
    out = []
    for p in parts:
        if p.lower() in ("de", "del", "la", "da", "dei", "di") and out:
            out.append(p.lower())
        elif p.isupper() and len(p) > 2 or p.islower() and len(p) > 1:
            out.append(p.capitalize())
        else:
            out.append(p[:1].upper() + p[1:] if p else p)
    return "".join(out)

def tsec(t):
    if not t: return None
    t = t.replace(",", ".")
    m = re.match(r"^(?:(\d+):)?(\d{1,2}\.\d{2})", t)
    if not m: return None
    return round((int(m.group(1)) if m.group(1) else 0) * 60 + float(m.group(2)), 2)

STROKES = [
    (r"Estilo Libre|Freestyle|Libre(?= Relevo)", "Libre"),
    (r"Espalda|Backstroke", "Espalda"),
    (r"Pecho|Breaststroke", "Pecho"),
    (r"Mariposa|Butterfly", "Mariposa"),
    (r"\bCI\b|\bIM\b|Combinado|Medley", "Combinado"),
]

EV_RE = re.compile(r"^\s*[-\d]*\(?\s*(?:Evento|Event)\s+(\d+)\s+(Hombres|Mujeres|Mixto|Men|Women|Mixed)\s+(.+?)\)?\s*$")
TIME = r"(?:\d+:)?\d{1,2}[.,]\d{2}"
RES_RE = re.compile(
    r"^\s*(?P<place>\*?\d+|-{2,3})\s+(?P<name>.*?)\s*(?<!\d)(?P<age>\d{1,2})\s+(?P<team>.*?)\s*"
    r"(?P<seed>" + TIME + r"|NT)?\s+(?P<final>(?:DQ\s+)?X?(?:" + TIME + r"[A-Za-z]?|DQ)|X?NS|DQ|DNF|SCR|DFS)(?:\s+[qRJr])?\s*(?P<pts>\d+\s?(?:[.,]\s?\d+)?)?\s*$")
REL_RE = re.compile(
    r"^\s*(?P<place>\*?\d+|-{2,3})\s+(?P<team>.+?)\s+'?(?P<letter>[A-J])'?\s+(?P<seed>" + TIME + r"|NT)?\s*"
    r"(?P<final>(?:DQ\s+)?" + TIME + r"|NS|DQ|DNF|SCR)\s*(?P<pts>\d+(?:[.,]\d+)?)?\s*$")

def page_count(path):
    out = subprocess.run(["pdfinfo", path], capture_output=True, text=True).stdout
    return int(re.search(r"Pages:\s+(\d+)", out).group(1))

def get_lines(path, cols):
    if cols == 1:
        txt = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
        return txt.splitlines()
    lines = []
    for p in range(1, page_count(path) + 1):
        for x in (0, 306):
            txt = subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), "-x", str(x), "-y", "0",
                                  "-W", "306", "-H", "792", path, "-"], capture_output=True, text=True).stdout
            lines += txt.splitlines()
    return lines

def parse_event_header(rest):
    course = "LCM" if re.search(r"\b(CL|LC)\b", rest) else ("SCM" if re.search(r"\b(CC|SC)\b", rest) else "?")
    m = re.match(r"(\d+(?:-\d+)?|\d+ & (?:Menores|Mayores|Over|Under))\s+(\d+)\s", rest)
    if not m: return None
    agegrp, dist = m.group(1), int(m.group(2))
    relay = bool(re.search(r"Relevo|Relay", rest))
    stroke = None
    for pat, name in STROKES:
        if re.search(pat, rest):
            stroke = name; break
    if relay and stroke is None: stroke = "Libre"
    div = None
    if re.search(r"\bLIB(RES?)?\b|\bLibre$|Libre Relevo$", rest): div = "LIB"
    if re.search(r"\bFED(ERADOS?)?\b|Federado", rest): div = "FED"
    if re.search(r"Libre Libre", rest): div = "LIB"
    special = bool(re.search(r"GOLD", rest)) or agegrp == "20-100"
    return dict(agegrp=agegrp, dist=dist, course=course, stroke=stroke, relay=relay, div=div, special=special)

def parse_meet(mid, fname, cols):
    lines = get_lines(UP + fname, cols)
    events, results, relays = {}, [], []
    cur = None
    has_lib_tag = any(re.search(r"\b(LIB|LIBRES|Libre Libre)\b", l) for l in lines if EV_RE.match(l))
    gmap = {"Hombres": "M", "Men": "M", "Mujeres": "F", "Women": "F", "Mixto": "X", "Mixed": "X"}
    for raw in lines:
        line = fix_glyphs(raw)
        line = re.sub(r"^(\d+|\*\d+|---)(?=\s+(?:\*?\d+|---)\s+\S)", "", line)  # dígito residual (Rosario)
        m = EV_RE.match(line)
        if m:
            h = parse_event_header(m.group(3))
            if not h: cur = None; continue
            g = gmap[m.group(2)]
            key = (int(m.group(1)), g, h["agegrp"])
            h.update(num=int(m.group(1)), gender=g)
            cur = h
            continue
        if cur is None: continue
        if re.match(r"^\s*(Masters|Nombre|Name|Equipo|Team\s|=)", line) or re.search(r"Tiempo de Finales|Finals Time|Sembrar", line): continue
        if cur["relay"]:
            r = REL_RE.match(line)
            if r and not re.match(r"^\s*\d\)", line):
                team = r.group("team").strip() or ("Delfines Natacion" if mid == "ROS22" else "?")
                relays.append(dict(meet=mid, num=cur["num"], gender=cur["gender"], agegrp=cur["agegrp"], dist=cur["dist"],
                                   stroke=cur["stroke"], course=cur["course"], team=team, letter=r.group("letter"),
                                   place=None if r.group("place").startswith("-") else int(r.group("place").lstrip("*")),
                                   time=tsec(r.group("final")) if not r.group("final").startswith("DQ") else None,
                                   status="OK" if tsec(r.group("final")) and not r.group("final").startswith("DQ") else r.group("final").split()[0]))
            continue
        r = RES_RE.match(line)
        if not r: continue
        name = re.sub(r"\s+", " ", r.group("name")).strip()
        team = re.sub(r"\s+", " ", r.group("team")).strip()
        age = int(r.group("age"))
        if age < 18: continue
        if mid == "ROS22":
            if not team: team = "Delfines Natacion"
            if not name: name = ROS_MISSING.get((age, team), "")
        if not name: continue
        div = cur["div"]
        if mid == "SL22":
            sm = re.search(r"\s([LF])$", name)
            if sm:
                div = "LIB" if sm.group(1) == "L" else "FED"; name = name[:-2]
        if div is None: div = "FED" if has_lib_tag else "OPEN"
        fin = r.group("final")
        status = "OK"
        if fin.startswith("X"):
            status = "EXH"; fin = fin[1:]
        if fin.startswith("DQ"): status = "DQ"
        elif fin in ("NS", "DNF", "SCR", "DFS"): status = fin
        t = tsec(fin) if status in ("OK", "EXH") else None
        if status == "EXH" and t is None: status = "NS"
        if status == "OK" and t is None: continue
        pl = r.group("place")
        results.append(dict(meet=mid, num=cur["num"], gender=cur["gender"], agegrp=cur["agegrp"], dist=cur["dist"],
                            stroke=cur["stroke"], course=cur["course"], div=div, special=cur["special"],
                            place=None if pl.startswith("-") else int(pl.lstrip("*")),
                            name=name, age=age, team=team, seed=tsec(r.group("seed")) if r.group("seed") else None,
                            time=t, status=status, pts=float(r.group("pts").replace(" ", "").replace(",", ".")) if r.group("pts") else None,
                            truncated=(mid == "BA19")))
    if mid == "SL22":
        votes = defaultdict(Counter)
        for r in results:
            if r["div"] != "OPEN": votes[(r["num"], r["gender"])][r["div"]] += 1
        for r in results:
            v = votes.get((r["num"], r["gender"]))
            if r["div"] == "OPEN" and v: r["div"] = v.most_common(1)[0][0]
    return results, relays

# ---------- Normalización de equipos ----------
TEAM_ALIAS = {
    "municipalidad alte. brown": "Municipalidad Almirante Brown",
    "municipalidad almirante brown": "Municipalidad Almirante Brown",
    "asoc litoral de natacion": "Asoc. Litoral de Natación", "aso del litoral de natacion": "Asoc. Litoral de Natación",
    "alnmv": "Asoc. Litoral de Natación",
    "club atletico river plate": "Club Atlético River Plate", "carp": "Club Atlético River Plate",
    "club atletico san miguel": "Club Atlético San Miguel",
    "delfines natacion": "Delfines Natación", "dn": "Delfines Natación",
    "noa team master": "Noa Team Master", "noa team": "Noa Team Master",
    "libertador natacion master": "Libertador Natación Master", "lnm": "Libertador Natación Master",
    "club atletico adelia maria": "Club Atlético Adelia María", "adm": "Club Atlético Adelia María",
    "argentino marcos juarez": "Club Argentino Marcos Juárez", "club argentino marcos juarez": "Club Argentino Marcos Juárez",
    "olimpo bahia blanca": "Olimpo Bahía Blanca", "predadores junin": "Predadores de Junín", "predadores de junin": "Predadores de Junín",
    "club nautico zarate": "Club Náutico Zárate",
    "libertador": "Libertador Natación Master", "municipio lomas de zamora": "Municipio de Lomas de Zamora",
    "municipio de lomas de zamora": "Municipio de Lomas de Zamora",
    "soc y fom union y progreso tan": "Soc. y Fom. Unión y Progreso (Tandil)", "sfupt": "Soc. y Fom. Unión y Progreso (Tandil)",
    "sport club flores": "Sport Club Flores", "scflo": "Sport Club Flores",
    "club atletico all boys la pamp": "Club Atlético All Boys (La Pampa)", "newell's old boys": "Newell's Old Boys",
    "club atletico las palmas": "Club Atlético Las Palmas", "nado": "Nado", "vicente lopez": "Vicente López", "heed physique": "Heed Physique",
}

def norm_team(t):
    k = strip_acc(t).lower().strip()
    k = re.sub(r"\s+", " ", k)
    if k in TEAM_ALIAS: return TEAM_ALIAS[k]
    if not t: return "Sin equipo"
    if t.isupper() and len(t) <= 6 or re.fullmatch(r"[A-Z0-9]{2,6}", t): return t
    return title_name(t)

# ---------- Resolución de identidad de nadadores ----------
def name_parts(name):
    n = strip_acc(name).lower()
    n = re.sub(r"[^a-z, ]", "", n)
    if "," in n:
        last, first = n.split(",", 1)
    else:
        last, first = n, ""
    first_tokens = [t for t in first.split() if len(t) > 1]
    return re.sub(r"\s+", " ", last).strip(), (first_tokens[0] if first_tokens else "")

def main():
    meets_meta = {m[0]: m for m in MEETS}
    all_res, all_rel = [], []
    for mid, f, *_ in MEETS:
        cols = meets_meta[mid][5]
        res, rel = parse_meet(mid, f, cols)
        print(mid, "resultados:", len(res), "relevos:", len(rel))
        all_res += res; all_rel += rel

    swimmers = []          # dict(id, gender, last, first, by, names Counter, truncated)
    index = defaultdict(list)
    def find(gender, last, first, by, trunc):
        cands = []
        for s in swimmers:
            if s["gender"] != gender or abs(s["by"] - by) > 1: continue
            if trunc:
                lok = s["last"].startswith(last) or last.startswith(s["last"]) if len(last) >= 5 else s["last"] == last
                fok = (not first) or s["first"].startswith(first) or first.startswith(s["first"])
            else:
                lok = s["last"] == last or (s["trunc_only"] and last.startswith(s["last"]) and len(s["last"]) >= 5)
                fok = s["first"] == first or (s["trunc_only"] and (not s["first"] or first.startswith(s["first"])))
            if lok and fok: cands.append(s)
        return cands[0] if len(cands) >= 1 else None

    year = {m[0]: int(m[4][:4]) for m in MEETS}
    order = sorted(range(len(all_res)), key=lambda i: all_res[i]["truncated"])
    for i in order:
        r = all_res[i]
        last, first = name_parts(r["name"])
        by = year[r["meet"]] - r["age"]
        s = find(r["gender"], last, first, by, r["truncated"])
        if s is None:
            s = dict(id=len(swimmers) + 1, gender=r["gender"], last=last, first=first, by=by, names=Counter(), trunc_only=r["truncated"], bys=[])
            swimmers.append(s)
        elif not r["truncated"] and s["trunc_only"]:
            s.update(last=last, first=first, trunc_only=False)
        s["names"][r["name"]] += 1; s["bys"].append(by)
        r["swimmer_id"] = s["id"]

    def display(s):
        cands = [n for n in s["names"] if not s["trunc_only"]] or list(s["names"])
        # preferir variantes no truncadas (con coma) y más largas, sin iniciales sueltas al final
        best = max(cands, key=lambda n: ("," in n, not any(r["truncated"] and r["name"] == n for r in []), len(re.sub(r"\s[A-Za-z]$", "", n)), s["names"][n]))
        best = re.sub(r"\s[A-Za-z]$", "", best)
        if "," in best:
            l, f = best.split(",", 1); return title_name(l.strip()) + ", " + title_name(f.strip())
        return title_name(best) + "…"
    for s in swimmers:
        s["display"] = display(s)
        s["by"] = Counter(s["bys"]).most_common(1)[0][0]

    # ---------- FINA points aprox (base: récords mundiales ~2022) ----------
    WR = {
        ("LCM", "M"): {(50, "Libre"): 20.91, (100, "Libre"): 46.86, (200, "Libre"): 102.00, (400, "Libre"): 220.07,
                      (50, "Espalda"): 23.71, (100, "Espalda"): 51.60, (50, "Pecho"): 25.95, (100, "Pecho"): 56.88,
                      (50, "Mariposa"): 22.27, (100, "Mariposa"): 49.45, (200, "Combinado"): 114.00},
        ("LCM", "F"): {(50, "Libre"): 23.67, (100, "Libre"): 51.71, (200, "Libre"): 112.98, (400, "Libre"): 236.40,
                      (50, "Espalda"): 26.98, (100, "Espalda"): 57.45, (50, "Pecho"): 29.30, (100, "Pecho"): 64.13,
                      (50, "Mariposa"): 24.43, (100, "Mariposa"): 55.48, (200, "Combinado"): 126.12},
        ("SCM", "M"): {(50, "Libre"): 20.16, (100, "Libre"): 44.84, (200, "Libre"): 99.37, (400, "Libre"): 212.25,
                      (50, "Espalda"): 22.22, (100, "Espalda"): 48.33, (50, "Pecho"): 25.25, (100, "Pecho"): 55.28,
                      (50, "Mariposa"): 21.75, (100, "Mariposa"): 47.78, (100, "Combinado"): 49.28, (200, "Combinado"): 109.63},
        ("SCM", "F"): {(50, "Libre"): 22.93, (100, "Libre"): 50.25, (200, "Libre"): 110.31, (400, "Libre"): 231.30,
                      (50, "Espalda"): 25.60, (100, "Espalda"): 54.89, (50, "Pecho"): 28.37, (100, "Pecho"): 62.36,
                      (50, "Mariposa"): 24.38, (100, "Mariposa"): 54.05, (100, "Combinado"): 56.51, (200, "Combinado"): 121.86},
    }
    for r in all_res:
        base = WR.get((r["course"], r["gender"]), {}).get((r["dist"], r["stroke"]))
        r["fina"] = int(round(1000 * (base / r["time"]) ** 3)) if base and r["time"] else None
        r["team_n"] = norm_team(r["team"])
    for r in all_rel:
        r["team_n"] = norm_team(r["team"])

    # ---------- Escritura SQLite ----------
    OUT.mkdir(parents=True, exist_ok=True)
    dbp = str(OUT / "natacion_master.sqlite")
    if os.path.exists(dbp): os.remove(dbp)
    con = sqlite3.connect(dbp); c = con.cursor()
    c.executescript(open(SCHEMA, encoding="utf-8").read())
    for mid, f, name, city, date, _ in MEETS:
        crs = Counter(r["course"] for r in all_res if r["meet"] == mid).most_common(1)[0][0]
        c.execute("INSERT INTO meet VALUES (?,?,?,?,?,?)", (mid, name, city, date, crs, f))
    teams = sorted({r["team_n"] for r in all_res} | {r["team_n"] for r in all_rel})
    tid = {t: i + 1 for i, t in enumerate(teams)}
    c.executemany("INSERT INTO team VALUES (?,?)", [(tid[t], t) for t in teams])
    c.executemany("INSERT INTO swimmer VALUES (?,?,?,?)", [(s["id"], s["display"], s["gender"], s["by"]) for s in swimmers])
    evid = {}
    for r in all_res + all_rel:
        k = (r["meet"], r["num"], r["gender"], r["agegrp"], r.get("div", "REL"))
        if k not in evid:
            evid[k] = len(evid) + 1
            c.execute("INSERT INTO event VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (evid[k], r["meet"], r["num"], r["gender"], r["agegrp"], r["dist"], r["stroke"], r["course"],
                       r.get("div", "REL"), int("letter" in r), int(r.get("special", False))))
        r["event_id"] = evid[k]
    c.executemany("INSERT INTO result (event_id, swimmer_id, team_id, age, place, seed_s, time_s, status, points, fina_pts, raw_name) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  [(r["event_id"], r["swimmer_id"], tid[r["team_n"]], r["age"], r["place"], r["seed"], r["time"], r["status"], r["pts"], r["fina"], r["name"]) for r in all_res])
    c.executemany("INSERT INTO relay_result (event_id, team_id, letter, place, time_s, status) VALUES (?,?,?,?,?,?)",
                  [(r["event_id"], tid[r["team_n"]], r["letter"], r["place"], r["time"], r["status"]) for r in all_rel])
    con.commit()
    json.dump(dict(results=all_res, relays=all_rel, swimmers=[{k: v for k, v in s.items() if k not in ("names", "bys")} for s in swimmers]),
              open(OUT / "raw.json", "w", encoding="utf-8"), ensure_ascii=False, default=str)
    print("nadadores:", len(swimmers), "equipos:", len(teams), "eventos:", len(evid))

if __name__ == "__main__":
    main()
