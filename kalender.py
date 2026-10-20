#!/usr/bin/env python3
"""Baut aus den öffentlichen Friedolin-Daten (FSU Jena) einen aufgeräumten
Kalender (kalender.ics) zum Abonnieren in Apple Kalender & Co.

- Termine, Zeiten und Räume kommen aus dem iCal-Export von Friedolin.
- Ausfälle ("fällt aus am") werden NICHT gelöscht, sondern als
  "❌ Fällt aus: …" mit Grund im Kalender angezeigt.
- Jeder Termin enthält einen Link zur Veranstaltungsseite in Friedolin.

Kurse werden in kurse.json gepflegt (Veranstaltungs-ID aus der Friedolin-URL,
Parameter publishid bzw. veranstid).

Nur Python-Standardbibliothek, kein Login nötig.
"""
import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://friedolin.uni-jena.de/qisserver/rds"
ICS_URL = (BASE + "?state=verpublish&status=transform&vmfile=no&veranstaltung.veranstid={id}"
           "&veransttermin.parallelid={gruppe}&moduleCall=iCalendarGruppe&publishConfFile=reports"
           "&publishSubDir=veranstaltung")
INFO_URL = (BASE + "?state=verpublish&status=init&vmfile=no&publishid={id}&moduleCall=webInfo"
            "&publishConfFile=webInfo&publishSubDir=veranstaltung")
TZ = "Europe/Berlin"
HERE = Path(__file__).resolve().parent
OUT = HERE / "kalender.ics"


# ---------------------------------------------------------------- Abruf
def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "uni-kalender/1.0 (privater Stundenplan-Sync)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                cs = r.headers.get_content_charset() or "utf-8"
            try:
                return raw.decode(cs)
            except (UnicodeDecodeError, LookupError):
                return raw.decode("latin-1")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"Abruf fehlgeschlagen: {url} ({last})")


def load(kind, kurs_id, gruppe, offline):
    if offline:
        return (Path(offline) / f"{kurs_id}.{kind}").read_text(encoding="utf-8")
    url = (ICS_URL if kind == "ics" else INFO_URL).format(id=kurs_id, gruppe=gruppe)
    return fetch(url)


# ---------------------------------------------------------------- Parsing
def text(fragment):
    """HTML-Schnipsel -> lesbarer Text mit Zeilenumbrüchen."""
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>", "\n", fragment or "")
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    lines = [re.sub(r"[ \t\r]+", " ", l).strip() for l in s.split("\n")]
    return "\n".join(l for l in lines if l).strip()


def parse_ics(raw):
    raw = raw.replace("\r\n", "\n").replace("\n ", "").replace("\n\t", "")
    events = []
    for block in re.findall(r"BEGIN:VEVENT\n(.*?)END:VEVENT", raw, re.S):
        ev = {}
        for line in block.split("\n"):
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            name = key.split(";", 1)[0].upper()
            ev[name] = val
        events.append(ev)
    return events


def parse_termine(page):
    """Liest die Termintabellen der Veranstaltungsseite: Lehrperson, Status,
    Bemerkung und 'fällt aus am' je Termin-ID."""
    result = {}
    for table in re.findall(r'<table[^>]*summary="[^"]*Veranstaltungstermine[^"]*"[^>]*>(.*?)</table>', page, re.S):
        header = [text(h).lower() for h in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)]
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            m = re.search(r"expand=(\d+)", row)
            if not cells or not m:
                continue

            def col(name):
                for i, h in enumerate(header):
                    if name in h and i < len(cells):
                        return cells[i]
                return ""

            ausfall = []
            raw_aus = text(col("fällt aus"))
            for dm in re.finditer(r"(\d{2})\.(\d{2})\.(\d{4}):?\s*(.*?)(?=\d{2}\.\d{2}\.\d{4}|$)", raw_aus, re.S):
                d, mth, y, why = dm.groups()
                ausfall.append((f"{y}{mth}{d}", why.strip(" ,;\n")))
            result[m.group(1)] = {
                "lehrperson": personen(text(col("lehrperson"))),
                "status": text(col("status")),
                "bemerkung": text(col("bemerkung")),
                "ausfall": ausfall,
            }
    return result


def personen(s):
    namen = []
    for teil in s.split("\n"):
        teil = re.sub(r"\(.*?\)", "", teil).strip()
        if not teil:
            continue
        p = [x.strip() for x in teil.split(",")]
        namen.append(f"{p[1]} {p[0]}" if len(p) >= 2 and p[1] else p[0])
    return ", ".join(namen)


# ---------------------------------------------------------------- Ausgabe
def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    out, cur, limit = [], b"", 75
    for ch in line:
        c = ch.encode("utf-8")
        if len(cur) + len(c) > limit:
            out.append(cur)
            cur, limit = b"", 74
        cur += c
    out.append(cur)
    return "\r\n ".join(x.decode("utf-8") for x in out)


def ort(s):
    return re.sub(r"\s+-\s+", ", ", s.strip())


def build(config, offline=None):
    vevents = []
    for kurs in config["kurse"]:
        kid = str(kurs["id"])
        gruppe = kurs.get("gruppe", 0)
        ics = load("ics", kid, gruppe, offline)
        if "BEGIN:VCALENDAR" not in ics:
            raise RuntimeError(f"Kurs {kid}: Antwort ist kein Kalender")
        info = load("html", kid, gruppe, offline)
        termine = parse_termine(info)
        link = INFO_URL.format(id=kid)
        events = parse_ics(ics)
        if not events:
            print(f"Hinweis: Kurs {kid} hat (noch) keine Termine", file=sys.stderr)

        # Doppelt eingetragene Termine (gleiche Zeit, gleicher Rhythmus) nur einmal
        # übernehmen – bevorzugt den Eintrag mit Raumangabe.
        events.sort(key=lambda e: not e.get("LOCATION", "").strip())
        gesehen = set()

        for ev in events:
            schluessel = (ev.get("DTSTART", ""), ev.get("DTEND", ""), ev.get("RRULE", ""))
            if schluessel in gesehen:
                print(f"Hinweis: doppelter Termin in Kurs {kid} übersprungen ({ev.get('UID', '')})", file=sys.stderr)
                continue
            gesehen.add(schluessel)
            uid = ev.get("UID", "")
            tid = uid[len(kid):] if uid.startswith(kid) else uid
            t = termine.get(tid, {})
            cfg = kurs.get("termine", {}).get(tid, {})
            summary = html.unescape(ev.get("SUMMARY", "")).replace("\\,", ",")
            nr = (re.match(r"\s*(\d+)\s*-", summary) or [None, ""])[1]
            titel = cfg.get("titel") or kurs.get("titel") or re.sub(r"^\s*\d+\s*-\s*", "", summary)

            location = ort(ev.get("LOCATION", "").replace("\\,", ","))
            if not location:
                location = cfg.get("ort") or t.get("bemerkung", "").split("\n")[0]

            bemerkung = t.get("bemerkung") or text(ev.get("DESCRIPTION", "").replace("\\n", "\n"))
            kopf = " · ".join(x for x in [ev.get("CATEGORIES", "").replace("\\,", ","), f"Nr. {nr}" if nr else ""] if x)
            beschr = [x for x in [kopf, t.get("lehrperson", ""), bemerkung] if x]

            ganz_aus = "fällt aus" in t.get("status", "").lower()
            if ganz_aus:
                titel = "❌ Fällt aus: " + titel
                beschr.insert(0, "⚠️ Laut Friedolin fällt diese Veranstaltung aus.")
            beschr += ["", "Mehr Infos in Friedolin:", link]

            start, end = ev.get("DTSTART", ""), ev.get("DTEND", "")
            start_t = start[8:] if len(start) >= 15 else "T000000"
            end_t = end[8:] if len(end) >= 15 else start_t
            ausfall = {d: why for d, why in t.get("ausfall", [])}
            exdates = [x for x in ev.get("EXDATE", "").split(",") if x.strip()]
            exdates = [x for x in exdates if x[:8] not in ausfall]

            ausfall_hier = {}
            if "RRULE" not in ev and start[:8] in ausfall:
                titel = "❌ Fällt aus: " + titel
                beschr.insert(0, "⚠️ Fällt aus" + (f": {ausfall[start[:8]]}" if ausfall[start[:8]] else ""))
            else:
                ausfall_hier = ausfall

            lines = ["BEGIN:VEVENT", f"UID:{uid}@friedolin.uni-jena.de", "DTSTAMP:{STAMP}",
                     f"DTSTART;TZID={TZ}:{start}", f"DTEND;TZID={TZ}:{end}"]
            if "RRULE" in ev:
                rr = ";".join(p for p in ev["RRULE"].split(";") if p and p != "INTERVAL=1")
                lines.append(f"RRULE:{rr}")
            if exdates:
                lines.append(f"EXDATE;TZID={TZ}:{','.join(exdates)}")
            lines += [f"SUMMARY:{esc(titel)}", f"LOCATION:{esc(location)}",
                      f"DESCRIPTION:{esc(chr(10).join(beschr))}", f"URL:{link}", "END:VEVENT"]
            vevents.append(lines)

            for d, why in sorted(ausfall_hier.items()):
                info_txt = ["⚠️ Dieser Termin fällt laut Friedolin aus."]
                if why:
                    info_txt.append(f"Grund/Hinweis: {why}")
                info_txt += ["", "Mehr Infos in Friedolin:", link]
                vevents.append([
                    "BEGIN:VEVENT", f"UID:{uid}@friedolin.uni-jena.de", "DTSTAMP:{STAMP}",
                    f"RECURRENCE-ID;TZID={TZ}:{d}{start_t}",
                    f"DTSTART;TZID={TZ}:{d}{start_t}", f"DTEND;TZID={TZ}:{d}{end_t}",
                    f"SUMMARY:{esc('❌ Fällt aus: ' + titel)}", f"LOCATION:{esc(location)}",
                    f"DESCRIPTION:{esc(chr(10).join(info_txt))}", f"URL:{link}",
                    "TRANSP:TRANSPARENT", "END:VEVENT"])

    if not vevents:
        raise RuntimeError("Keine Termine gefunden – Kalender wird nicht überschrieben")

    head = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//uni-kalender//Friedolin Sync//DE",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
            f"X-WR-CALNAME:{esc(config.get('kalendername', 'Uni'))}", f"X-WR-TIMEZONE:{TZ}",
            "REFRESH-INTERVAL;VALUE=DURATION:PT2H", "X-PUBLISHED-TTL:PT2H",
            "BEGIN:VTIMEZONE", f"TZID:{TZ}",
            "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
            "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3", "END:DAYLIGHT",
            "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET",
            "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10", "END:STANDARD",
            "END:VTIMEZONE"]
    body = head + [l for ev in vevents for l in ev] + ["END:VCALENDAR"]
    return "\r\n".join(fold(l) for l in body) + "\r\n"


def main():
    offline = sys.argv[sys.argv.index("--offline") + 1] if "--offline" in sys.argv else None
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else OUT
    config = json.loads((HERE / "kurse.json").read_text(encoding="utf-8"))
    neu = build(config, offline)

    alt = out.open(encoding="utf-8", newline="").read() if out.exists() else ""
    strip = lambda s: re.sub(r"DTSTAMP:\S+", "", s)  # noqa: E731
    if alt and strip(alt) == strip(neu):
        print("Keine Änderungen.")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.write_text(neu.replace("{STAMP}", stamp), encoding="utf-8", newline="")
    print(f"Kalender aktualisiert: {out.name} ({neu.count('BEGIN:VEVENT')} Einträge)")


if __name__ == "__main__":
    main()
