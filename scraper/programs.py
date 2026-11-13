"""
Seasonal / annual recruitment programs (MagangHub, Magenta, CPNS, bank programs, ...).

Manual info lives in programs.json. Where the official site can be read, a small checker below
adds a live status and the current openings. Runs as part of scrape.py, or on its own (about a minute):

    python scraper/programs.py      # updates only site/data/programs.js
"""
import html
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from scrape import UNSPECIFIED, cache, classify, clean, get, log, province_of, session, update_section

PROGRAMS_FILE = Path(__file__).resolve().parent / "programs.json"
CHECK_MAX_AGE_HOURS = 24   # each official site is checked at most once a day
IT_MAJORS = re.compile(r"informatika|komputer|computer|sistem informasi|teknologi informasi|perangkat lunak|software|"
                       r"\bdata\b|\bti\b|\bit\b", re.I)
MONTHS = {m: i + 1 for i, names in enumerate([
    ("jan", "januari", "january"), ("feb", "februari", "february"), ("mar", "maret", "march"), ("apr", "april"),
    ("may", "mei"), ("jun", "juni", "june"), ("jul", "juli", "july"), ("aug", "agu", "agustus", "august"),
    ("sep", "september"), ("oct", "okt", "oktober", "october"), ("nov", "november"), ("dec", "des", "desember", "december"),
]) for m in names}


def visible(page):
    page = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", " ", page or "", flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def human_date(text):
    """'12 November 2026' / '31 Desember 2026' / 'Dec 2026, 31' -> 'YYYY-MM-DD' or None."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if m:
        d, mon, y = m.groups()
    else:
        m = re.search(r"([A-Za-z]+)\s+(\d{4}),?\s+(\d{1,2})", text)
        if not m:
            return None
        mon, y, d = m.groups()
    month = MONTHS.get(mon.lower())
    try:
        return date(int(y), month, int(d)).isoformat() if month else None
    except ValueError:
        return None


def item(title, company="", location="", url="", deadline=None, applicants=None, note=""):
    title = clean(title)
    prov = province_of(location) if location else None
    return {"title": title, "company": clean(company), "location": clean(location),
            "province": prov if prov != UNSPECIFIED else None, "url": url, "deadline": deadline,
            "applicants": applicants, "note": clean(note), "it": bool(classify(title))}


# ---------------------------------------------------------------------------
# Checkers: each returns {"headline": str, "status": "open"/"closed"/None, "items": [...], "total": int|None}
# status None means "the site doesn't say" -> the manual dates in programs.json decide.
# ---------------------------------------------------------------------------
def check_maganghub(today):
    base = "https://maganghub.kemnaker.go.id"
    r = get(base + "/")
    m = re.search(r"Memuat\.\.\.\s*(.*?)\s*1500630", visible(r.text)) if r is not None and r.ok else None
    headline = m.group(1) if m else ""
    card_rx = re.compile(r'<a class="group block h-full" href="(/magang-nasional/lowongan/[^"]+)">(.*?)</a>', re.S)
    found = {}
    for kw in ["programmer", "developer", "software", "web", "data", "aplikasi", "sistem informasi", "IT"]:
        for page in range(1, 7):
            r = get(base + "/magang-nasional/lowongan", params={"keyword": kw, "page": page})
            cards = card_rx.findall(r.text) if r is not None and r.ok else []
            for href, body in cards:
                title = visible((re.search(r"<h3[^>]*>(.*?)</h3>", body, re.S) or [None, ""])[1])
                ps = [visible(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)]
                spans = [visible(s) for s in re.findall(r'<span class="flex items-center gap-1\.5">(.*?)</span>', body, re.S)]
                company, majors = (ps + ["", ""])[:2]
                location = spans[0] if spans else ""
                if not classify(title) or (majors and not IT_MAJORS.search(majors)):
                    continue
                prov = province_of(location)
                if prov in (None, UNSPECIFIED):
                    continue
                found[href] = item(title, company, location, base + html.unescape(href), note="Majors: " + majors if majors else "")
            if len(cards) < 18:
                break
    return {"headline": headline, "status": None, "items": list(found.values()), "total": None,
            "items_label": "IT positions on Java listed on MagangHub (latest batch)"}


def check_magenta(today):
    base = "https://magentaku.id"
    r = session.get(base + "/lowongan/magang", timeout=30)
    token = re.search(r'name="csrf-token" content="([^"]+)"', r.text)
    if not token:
        raise RuntimeError("no CSRF token on the Magenta page")
    headers = {"X-CSRF-TOKEN": token.group(1), "X-Requested-With": "XMLHttpRequest", "Referer": base + "/lowongan/magang"}
    items, total, page, last = [], None, 1, 1
    while page <= max(last, 1) and page <= 20:
        d = session.post(base + "/lowongan/list", data={"_token": token.group(1), "page": page, "type": "magang"},
                         headers=headers, timeout=30).json()
        total = (d.get("result") or {}).get("total_job", total)
        listing = d.get("jobposting") or ""
        last = max([int(p) for p in re.findall(r'data-page="(\d+)"', listing)] or [1])
        blocks = listing.split("job-posting-item")[1:]
        if not blocks:
            break
        for b in blocks:
            pid = re.search(r'data-id="(\d+)"', b)
            details = [visible(p) for p in re.findall(r'<p[^>]*content-detail[^>]*>(.*?)</p>', b, re.S)]
            title = visible((re.search(r'<h2[^>]*title[^>]*>(.*?)</h2>', b, re.S) or [None, ""])[1])
            text = visible(b)
            quota = re.search(r"(\d+)\s*Posisi\s*•?\s*(\d+)\s*Pelamar", text)
            closing = re.search(r"Penutupan\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+\d{4})", text)
            loc = details[1] if len(details) > 1 else ""
            if province_of(loc) in (None, UNSPECIFIED):
                continue
            items.append(item(title, details[0] if details else "", loc,
                              f"{base}/lowongan?posting={pid.group(1)}" if pid else base + "/lowongan/magang",
                              deadline=human_date(closing.group(1)) if closing else None,
                              applicants=int(quota.group(2)) if quota else None,
                              note=f"{quota.group(1)} position(s)" if quota else ""))
        page += 1
    is_open = any((i["deadline"] or "9999") >= today for i in items)
    return {"headline": f"{total or 0} internship postings open nationwide; {len(items)} on Java",
            "status": "open" if total else "closed", "items": items, "total": total,
            "items_label": "Open postings on Java" + (" (none right now)" if not is_open else "")}


def check_sscasn(today):
    r = get("https://sscasn.bkn.go.id/")
    text = visible(r.text) if r is not None and r.ok else ""
    m = re.search(r"Masuk Buat Akun Masuk (.*?) Kontak", text)
    headline = m.group(1) if m else text[:200]
    no_timeline = "belum tersedia" in headline.lower()
    return {"headline": headline, "status": "closed" if no_timeline else None, "items": [], "total": None}


def check_bca(today):
    r = get("https://karir.bca.co.id/magang-bakti")
    text = visible(r.text) if r is not None and r.ok else ""
    m = re.search(r"tersedia berikut ini\s*:\s*(.*?)\s*Galeri", text)
    names = [clean(n) for n in re.split(r"\s*Lihat Detail\s*", m.group(1)) if clean(n)] if m else []
    items = [item(n, "BCA", url="https://karir.bca.co.id/magang-bakti") for n in names]
    return {"headline": f"{len(items)} Magang Bakti program(s) listed on the BCA careers site" if items else "No Magang Bakti program listed",
            "status": "open" if items else "closed", "items": items, "total": len(items)}


def check_bri(today):
    r = get("https://e-recruitment.bri.co.id/")
    text = visible(r.text) if r is not None and r.ok else ""
    items = []
    for title, deadline in re.findall(r"Lowongan Kerja (.{5,200}?)\.?\s*Lamar Sebelum ([A-Za-z]{3,9} \d{4}, \d{1,2})", text):
        items.append(item(title, "BRI", url="https://e-recruitment.bri.co.id/", deadline=human_date(deadline)))
    open_items = [i for i in items if (i["deadline"] or "9999") >= today]
    return {"headline": f"{len(open_items)} posting(s) open on BRI e-recruitment",
            "status": "open" if open_items else "closed", "items": items, "total": len(items)}


def check_bni(today):
    code = "pt-bank-negara-indonesia-persero-tbk"
    r = get("https://www.kalibrr.com/kjs/job_board/search", params={"limit": 100, "offset": 0, "company": code})
    jobs = [j for j in (r.json().get("jobs", []) if r is not None and r.ok else [])
            if (j.get("company") or {}).get("code") == code]
    items = []
    for j in jobs:
        if not re.search(r"development program|\bodp\b|\badp\b|\bmdp\b|officer|talent pool|trainee", j.get("name", ""), re.I):
            continue
        addr = (j.get("google_location") or {}).get("address_components") or {}
        items.append(item(j["name"], "BNI", ", ".join(x for x in [addr.get("city"), addr.get("region")] if x),
                          f"https://www.kalibrr.com/c/{code}/jobs/{j['id']}/{j.get('slug', '')}",
                          deadline=(j.get("application_end_date") or "")[:10] or None))
    open_items = [i for i in items if (i["deadline"] or "9999") >= today]
    return {"headline": f"{len(open_items)} development-program posting(s) open on Kalibrr",
            "status": "open" if open_items else "closed", "items": items, "total": len(items)}


def check_bi_pcpm(today, known_batch=41):
    latest = None
    for n in range(known_batch, known_batch + 4):
        r = get(f"https://www.bi.go.id/id/karier/Pages/Seleksi-Penerimaan-PCPM-Angkatan-{n}.aspx")
        text = visible(r.text) if r is not None and r.ok else ""
        if "PCPM" in text and f"Angkatan {n}" in text:
            latest = n
        elif latest is not None:
            break
    if latest and latest > known_batch:
        headline = f"New: Bank Indonesia has a page for PCPM Angkatan {latest} – check its dates"
    else:
        headline = f"Latest announcement on bi.go.id: PCPM Angkatan {latest or known_batch}"
    return {"headline": headline, "status": None, "items": [], "total": None, "latest_batch": latest}


CHECKERS = {"maganghub": check_maganghub, "magenta": check_magenta, "sscasn": check_sscasn, "bca": check_bca,
            "bri": check_bri, "bni": check_bni, "bi_pcpm": check_bi_pcpm}


def status_from_window(window, today):
    window = window or {}
    start, end = window.get("from"), window.get("until")
    if start and today < start:
        return "upcoming"
    if end and today > end:
        return "closed"
    if end or start:
        return "open"
    return "unknown"


def collect_programs():
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    programs = json.loads(PROGRAMS_FILE.read_text(encoding="utf-8"))["programs"]
    for p in programs:
        live = None
        if p.get("auto") in CHECKERS:
            live = cache.get(f"program:{p['id']}", CHECK_MAX_AGE_HOURS)
            if live:
                log(f"  {p['id']}: reused today's check")
            else:
                try:
                    kwargs = {"known_batch": (p.get("window") or {}).get("batch", 41)} if p["auto"] == "bi_pcpm" else {}
                    live = {"ok": True, "checked_at": now, **CHECKERS[p["auto"]](today, **kwargs)}
                    cache.put(f"program:{p['id']}", live)
                except Exception as e:  # a broken site must not stop the run
                    live = {"ok": False, "checked_at": now, "error": str(e)[:200], "status": None, "items": []}
                log(f"  {p['id']}: " + (live.get("headline", "") if live["ok"] else "FAILED " + live["error"])[:120])
        p["live"] = live
        if live and live.get("status"):
            p["status"], p["status_basis"] = live["status"], "live check of the official site"
        else:
            p["status"] = status_from_window(p.get("window"), today)
            p["status_basis"] = "last known dates (checked " + p.get("checked", "?") + ")" if p["status"] != "unknown" else ""
    return programs


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    log("[Programs] checking official sites…")
    update_section("programs", collect_programs)
