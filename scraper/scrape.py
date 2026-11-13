"""
Collect software-engineering job listings on Java island (Indonesia), score how easy each
one is for a fresh graduate, and write the result to site/data/ for the website.

Run:  python scraper/scrape.py
"""
import html
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "site" / "data"   # one small list file per tab + a details file loaded in the background
LEGACY_OUT_FILE = HERE.parent / "site" / "jobs.js"  # old single-file output, removed after the first new run
HISTORY_FILE = HERE / "history.json"       # applicant / bid counts over time
HISTORY_KEEP_DAYS = 60
COMPANIES_FILE = HERE / "companies.json"
SEEN_FILE = HERE / "seen.json"   # when each job was first/last seen, for the "New" label
SEEN_KEEP_DAYS = 60              # forget jobs not seen for this long

# Search terms for Glints (it has no "IT" category filter that works without login).
SEARCH_KEYWORDS = [
    "software engineer", "backend", "frontend", "fullstack", "full stack", "web developer",
    "programmer", "mobile developer", "android", "ios developer", "flutter", "react native",
    "machine learning", "ai engineer", "data engineer", "data scientist", "qa engineer",
    "quality assurance", "software tester", "devops", "site reliability", "cloud engineer",
    "golang", "java developer", "php developer", "python developer", "node.js", "laravel",
    "react", ".net developer",
]
LINKEDIN_KEYWORDS = [
    "software engineer", "backend engineer", "frontend engineer", "fullstack developer",
    "mobile developer", "machine learning engineer", "ai engineer", "data engineer",
    "qa engineer", "devops engineer", "web developer", "programmer",
]
LINKEDIN_PAGES = 5            # 10 jobs per page, per keyword
LINKEDIN_MAX_DETAILS = 250    # detail pages give applicant count + description; LinkedIn rate-limits
JOBSTREET_PROVINCES = ["Jakarta Raya", "Jawa Barat", "Banten", "Jawa Tengah", "Yogyakarta", "Jawa Timur"]
JOBSTREET_MAX_PAGES = 15      # 100 jobs per page, per province
COMPANY_ABOUT_MAX = 2000      # characters of "about the company" text kept per job

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
})


def log(*a):
    print(*a, flush=True)


def get(url, **kw):
    """GET with a few retries. Returns the response, or None if it never succeeded."""
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30, **kw)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            return r
        except requests.RequestException:
            time.sleep(2)
    return None


def parallel(fn, items, workers=4):
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(fn, items))


# ---------------------------------------------------------------------------
# Cache: things already fetched are reused instead of downloaded again
# ---------------------------------------------------------------------------
CACHE_FILE = HERE / "cache.json"
DETAIL_MAX_AGE_HOURS = 7 * 24   # a job's detail page is re-read at most once a week
CACHE_KEEP_DAYS = 30            # entries not used for this long are dropped


class Cache:
    """JSON key -> value store with a timestamp per entry."""

    def __init__(self, path):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.used = set()
        self.lock = threading.Lock()

    def get(self, key, max_age_hours=None):
        """The stored value, or None if missing or older than max_age_hours (None = any age is fine)."""
        entry = self.data.get(key)
        if not entry:
            return None
        with self.lock:
            self.used.add(key)
        age = datetime.now(timezone.utc) - datetime.fromisoformat(entry["t"])
        if max_age_hours is not None and age > timedelta(hours=max_age_hours):
            return None
        return entry["v"]

    def put(self, key, value):
        with self.lock:
            self.data[key] = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "v": value}
            self.used.add(key)

    def save(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_KEEP_DAYS)
        keep = {k: e for k, e in self.data.items() if k in self.used or datetime.fromisoformat(e["t"]) > cutoff}
        self.path.write_text(json.dumps(keep, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


cache = Cache(CACHE_FILE)


def fetch_details(prefix, ids, fetch, workers=4, empty=None):
    """fetch(id) for every id that has no cached result from the last week; the rest come from the cache.
    If a fetch fails, an older cached copy is used when there is one."""
    keys = [f"{prefix}:{i}" for i in ids]
    todo = [(i, k) for i, k in zip(ids, keys) if cache.get(k, DETAIL_MAX_AGE_HOURS) is None]
    fetched = dict(zip([k for _, k in todo], parallel(lambda ik: fetch(ik[0]), todo, workers)))
    for k, v in fetched.items():
        if v:
            cache.put(k, v)
    if ids:
        log(f"  {prefix}: {len(ids) - len(todo)} details reused from cache, {len(todo)} fetched")
    return [fetched.get(k) or cache.get(k) or (empty if empty is not None else {}) for k in keys]


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def strip_html(s):
    """HTML -> readable plain text that keeps line breaks and bullet points."""
    s = re.sub(r"<li[^>]*>", "\n• ", s or "", flags=re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>|</div>|</h\d>|</ul>|</ol>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return tidy(html.unescape(s))


def tidy(s):
    lines = [re.sub(r"[ \t\r\f\v ]+", " ", line).strip() for line in (s or "").split("\n")]
    s = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return re.sub(r"\n\n(?=• )", "\n", s).strip()  # no blank line between bullet points


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(str(s or ""))).strip()


def human(code):
    """FULL_TIME / competitiveSalary / on_site -> 'Full time' / 'Competitive salary' / 'On site'."""
    if code in (None, ""):
        return None
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(code)).replace("_", " ").strip().lower()
    return s[:1].upper() + s[1:]


def draftjs_text(raw):
    """Glints stores rich text as Draft.js JSON."""
    try:
        doc = json.loads(raw or "null") or {}
    except ValueError:
        return ""
    lines = []
    for b in doc.get("blocks", []):
        t = (b.get("text") or "").rstrip()
        lines.append("• " + t if b.get("type") in ("unordered-list-item", "ordered-list-item") and t else t)
    return tidy("\n".join(lines))


def section(title, text):
    text = tidy(text)
    return f"{title}\n{text}" if text else ""


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def to_date(value):
    """ISO string / epoch-ms / datetime -> 'YYYY-MM-DD' (UTC), or None."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.date().isoformat()
    except ValueError:
        m = re.match(r"\d{4}-\d{2}-\d{2}", str(value))
        return m.group(0) if m else None


def money(lo, hi, period="month"):
    def fmt(v):
        return f"{v / 1_000_000:.1f}".rstrip("0").rstrip(".") + " jt"
    if not lo and not hi:
        return None
    if lo and hi and lo != hi:
        return f"Rp {fmt(lo)} – {fmt(hi)} / {period}"
    return f"Rp {fmt(hi or lo)} / {period}"


def parse_salary(label):
    """'Rp 10.000.000 – Rp 15.000.000 per month' / 'Rp 6,5 jt' -> (min, max) in IDR per month, or None."""
    if not label or re.search(r"\$|usd|sgd|hour|jam\b|day|hari|week|minggu", label, re.I):
        return None
    nums = []
    for m in re.finditer(r"(\d[\d.,]*)\s*(jt|juta|million|k|rb|ribu)?", label, re.I):
        raw, unit = m.group(1).rstrip(".,"), (m.group(2) or "").lower()
        try:
            if unit in ("jt", "juta", "million"):
                nums.append(float(raw.replace(",", ".")) * 1e6)
            elif unit in ("k", "rb", "ribu"):
                nums.append(float(raw.replace(".", "").replace(",", ".")) * 1e3)
            else:
                nums.append(float(re.sub(r"[.,]", "", raw)))
        except ValueError:
            continue
    nums = [n for n in nums if n >= 100_000]
    if not nums:
        return None
    lo, hi = min(nums), max(nums)
    if re.search(r"year|tahun|annum|annual", label, re.I):
        lo, hi = lo / 12, hi / 12
    return int(lo), int(hi)


def as_list(x):
    return x if isinstance(x, list) else [x] if x else []


def label_of(x):
    return x.get("label") if isinstance(x, dict) else x


def step_name(step):
    if isinstance(step, dict):
        return clean(step.get("name") or step.get("title") or step.get("label") or step.get("type"))
    return clean(step)


def details(description="", facts=(), timeline=(), skills=(), benefits=(), company=None, recruiter=None,
            hiring_steps=()):
    """Extra information shown when a job card is clicked. Empty values are dropped."""
    def val(v):
        if isinstance(v, bool):
            return "Yes" if v else "No"
        return clean(v) if v not in (None, "", "null", "-") else None

    company = {k: (tidy(v)[:COMPANY_ABOUT_MAX] if k == "about" else val(v)) for k, v in (company or {}).items()}
    d = {
        "description": tidy(description),
        "facts": [[k, val(v)] for k, v in facts if val(v)],
        "timeline": sorted(([k, to_date(v)] for k, v in timeline if to_date(v)), key=lambda x: x[1]),
        "skills": list(dict.fromkeys(s for s in (clean(x) for x in skills) if s)),
        "benefits": list(dict.fromkeys(s for s in (clean(x) for x in benefits) if s)),
        "company": {k: v for k, v in company.items() if v},
        "recruiter": {k: val(v) for k, v in (recruiter or {}).items() if val(v)},
        "hiring_steps": [s for s in (step_name(x) for x in hiring_steps) if s],
    }
    return {k: v for k, v in d.items() if v}


def make_job(source, sid, title, company, location, url, *, posted=None, remote=False, applicants=None,
             exp_years=None, exp_label=None, text="", salary=None, salary_range=None, province_hint=None,
             indonesian_board=True, info=None):
    info = info or {}
    lo, hi = salary_range or parse_salary(salary) or (None, None)
    return {
        "source": source, "id": f"{source}:{sid}", "title": clean(title), "company": clean(company),
        "location": clean(location), "url": url, "posted": to_date(posted), "remote": bool(remote),
        "applicants": applicants, "exp_years": exp_years, "exp_label": exp_label,
        "text": text or info.get("description", ""), "salary": salary,
        "salary_min": int(lo) if lo else None, "salary_max": int(hi or lo) if (hi or lo) else None,
        "province_hint": province_hint, "indonesian_board": indonesian_board, "details": info,
    }


# ---------------------------------------------------------------------------
# Role category (engineering roles only)
# ---------------------------------------------------------------------------
# Order matters: the first match wins. AI / ML comes after the concrete roles so that
# "Mobile Developer - AI app" is Mobile, while "AI Engineer" / "Machine Learning Engineer" stay AI / ML.
CATEGORIES = [
    ("Fullstack", r"full[\s-]?stack"),
    ("Data Engineering", r"data engineer|\betl\b|big data|data platform|analytics engineer|data warehouse|\bdwh\b|\bbi developer|database developer|data pipeline"),
    ("QA / Testing", r"\bqa\b|quality assurance|quality engineer|tester|\btest(?:ing)? engineer|\bsdet\b|automation test|test automation|software test"),
    ("DevOps / Cloud", r"devops|devsecops|\bsre\b|site reliability|cloud engineer|platform engineer|infrastructure engineer|kubernetes|release engineer"),
    ("Mobile", r"android|\bios\b|flutter|react native|mobile (?:developer|engineer|programmer|apps?|application)|kotlin|swift"),
    ("Frontend", r"front[\s-]?end|\bui engineer|\bui developer|react(?:\.?js)? developer|\bvue|angular|next\.?js"),
    ("Backend", r"back[\s-]?end|golang|\bgo (?:developer|engineer)|\bjava\b|\bphp\b|python (?:developer|engineer)|node\.?js|laravel|\.net\b|\bc#|\bruby|\brails\b|spring ?boot|api developer"),
    ("AI / ML", r"machine learning|\bml\b|\bai\b|artificial intelligence|deep learning|\bnlp\b|computer vision|\bllm|data scien|mlops|generative"),
    ("Software Engineer (general)", r"software|programmer|developer|pengembang|web dev|application engineer|aplikasi"),
]
CATEGORIES = [(name, re.compile(rx, re.I)) for name, rx in CATEGORIES]
NOT_ENGINEERING = re.compile(
    r"sales|marketing|recruit|talent acquisition|account (?:manager|executive)|business develop|teacher|guru|tutor|"
    r"instructor|mentor|trainer|property|real estate|content|copywrit|designer|ui/ux|\bux\b|\badmin\b|customer|"
    r"support|helpdesk|network|security|technician|teknisi|analyst|product manager|project manager|scrum|"
    r"consultant|game|annotat|asset|\boperations?\b|business (?:manager|partner|owner)|barista", re.I)


def classify(title):
    if not title or NOT_ENGINEERING.search(title):
        return None
    for name, rx in CATEGORIES:
        if rx.search(title):
            return name
    return None


# ---------------------------------------------------------------------------
# Location -> province on Java
# ---------------------------------------------------------------------------
PROVINCES = {
    "DKI Jakarta": ["jakarta", "dki", "jabodetabek"],
    "Banten": ["banten", "tangerang", "serpong", "bsd", "serang", "cilegon", "pandeglang", "lebak", "karawaci",
               "alam sutera", "bintaro", "cikupa", "balaraja"],
    "West Java": ["jawa barat", "west java", "bandung", "bekasi", "bogor", "depok", "cikarang", "karawang", "cimahi",
                  "cirebon", "sukabumi", "tasikmalaya", "purwakarta", "subang", "garut", "sumedang", "cianjur",
                  "indramayu", "majalengka", "ciamis", "cibinong", "cileungsi", "sentul"],
    "Central Java": ["jawa tengah", "central java", "semarang", "solo", "surakarta", "magelang", "salatiga",
                     "pekalongan", "tegal", "purwokerto", "banyumas", "kudus", "jepara", "klaten", "boyolali",
                     "sukoharjo", "cilacap", "kebumen", "pati", "demak", "kendal", "batang", "brebes", "wonosobo",
                     "temanggung", "rembang", "blora", "grobogan", "sragen", "karanganyar", "wonogiri",
                     "purbalingga", "banjarnegara", "pemalang", "purworejo"],
    "DI Yogyakarta": ["yogyakarta", "jogja", "yogya", "jogjakarta", "sleman", "bantul", "kulon progo", "gunungkidul",
                      "gunung kidul"],
    "East Java": ["jawa timur", "east java", "surabaya", "malang", "sidoarjo", "gresik", "kediri", "jember", "madiun",
                  "mojokerto", "pasuruan", "probolinggo", "blitar", "banyuwangi", "batu", "lamongan", "tuban",
                  "bojonegoro", "jombang", "nganjuk", "ponorogo", "tulungagung", "lumajang", "situbondo",
                  "bondowoso", "pamekasan", "sumenep", "bangkalan", "sampang", "magetan", "ngawi", "pacitan",
                  "trenggalek"],
}
PROVINCE_RX = [(p, re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b", re.I)) for p, words in PROVINCES.items()]
UNSPECIFIED = "Remote / unspecified"
FILLER_WORDS = re.compile(r"\b(indonesia|remote|id|wfh|work from home|hybrid|on-?site|anywhere|multiple locations|"
                          r"and|or|other|area|metropolitan)\b|[^a-z]", re.I)


def province_of(location, hint=None, indonesian_board=True):
    """Province on Java, UNSPECIFIED (Indonesia/remote without a city), or None (outside Java -> drop)."""
    text = location or ""
    best = None
    for prov, rx in PROVINCE_RX:
        m = rx.search(text)
        if m and (best is None or m.start() < best[1]):
            best = (prov, m.start())
    if best:
        return best[0]
    if hint:
        return province_of(hint)
    leftover = FILLER_WORDS.sub("", text)
    if leftover:
        return None
    if indonesian_board or re.search(r"indonesia", text, re.I):
        return UNSPECIFIED
    return None


# ---------------------------------------------------------------------------
# Experience required
# ---------------------------------------------------------------------------
WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "satu": 1, "dua": 2, "tiga": 3,
            "empat": 4, "lima": 5, "enam": 6}
FRESH_RX = re.compile(r"fresh\s*-?\s*grad|lulusan baru|tanpa pengalaman|no (?:prior |work )?experience (?:is )?(?:required|needed)|"
                      r"\b0\s*(?:-|–|to|sampai)\s*1\s*(?:years?|tahun)|new grad|recent graduate", re.I)
YEARS_RX = re.compile(
    r"(?<![\d.,])(\d{1,2}|one|two|three|four|five|six|satu|dua|tiga|empat|lima|enam)\s*(?:\+|plus)?\s*"
    r"(?:(?:-|–|—|to|sampai|s/d|hingga)\s*\d{1,2}\s*)?\+?\s*(?:years?|yrs?|tahun|thn)\b", re.I)
NOT_EXPERIENCE_BEFORE = re.compile(r"usia|umur|\bage\b|kontrak|contract|durasi|duration|period|berdiri|established|since|maks", re.I)
NOT_EXPERIENCE_AFTER = re.compile(r"^\W*(old|of age|contract|kontrak|warranty|garansi)", re.I)
EXPERIENCE_WORDS = re.compile(r"experien|pengalaman|\bexp\b|berpengalaman", re.I)


def years_from_text(text):
    """Find the minimum years of experience stated in a job description. Returns (years, snippet) or None."""
    if not text:
        return None
    m = FRESH_RX.search(text)
    if m:
        return 0, snippet(text, m)
    found = []
    for m in YEARS_RX.finditer(text):
        before, after = text[max(0, m.start() - 25):m.start()], text[m.end():m.end() + 15]
        if NOT_EXPERIENCE_BEFORE.search(before) or NOT_EXPERIENCE_AFTER.search(after):
            continue
        n = m.group(1).lower()
        years = WORD_NUM.get(n, None) if not n.isdigit() else int(n)
        if years is None or years > 15:
            continue
        near = text[max(0, m.start() - 80):m.end() + 80]
        found.append((0 if EXPERIENCE_WORDS.search(near) else 1, m.start(), years, m))
    if not found:
        return None
    found.sort(key=lambda f: (f[0], f[1]))  # prefer matches near "experience", then earliest
    _, _, years, m = found[0]
    return years, snippet(text, m)


def snippet(text, m):
    s = text[max(0, m.start() - 50):m.end() + 30].replace("\n", " ")
    return "…" + re.sub(r"\s+", " ", s).strip() + "…"


def years_from_title(title):
    t = title or ""
    if re.search(r"\b(intern|internship|magang|trainee|fresh\s*grad\w*|graduate program|apprentice)\b", t, re.I):
        return 0
    if re.search(r"\b(junior|jr\.?|entry)\b", t, re.I):
        return 1
    if re.search(r"\b(mid|middle|intermediate)\b", t, re.I):
        return 2
    if re.search(r"\b(senior|sr\.?|lead|principal|head|manager|architect|director|chief|vp|expert)\b", t, re.I):
        return 4
    return None


def experience(job):
    """Returns (years or None, how-we-know text)."""
    if job["exp_years"] is not None:
        return job["exp_years"], job["exp_label"] or f"Listing field: min {job['exp_years']} yr"
    found = years_from_text(job["text"])
    if found:
        return found[0], f"Description: {found[1]}"
    y = years_from_title(job["title"])
    if y is not None:
        return y, "Guessed from job title"
    return None, "Not stated"


# ---------------------------------------------------------------------------
# Agency / outsourcing flag (informational only, does not change the score)
# ---------------------------------------------------------------------------
AGENCY_NAME_RX = re.compile(
    r"outsourc|alih daya|staffing|manpower|headhunt|recruit|rekrut|placement|personnel|tenaga kerja|"
    r"sumber daya manusia|\bsdm\b|human (?:resource|capital)|\bhr\b|talent(?!a)|executive search", re.I)
AGENCY_TEXT_RX = re.compile(
    r"\bfor our client\b(?!s)|our client (?:is|a|an|in|which|that)\b|one of our clients|on behalf of (?:our|a) client|"
    r"salah satu (?:klien|client) kami|(?:klien|client) kami (?:adalah|merupakan|yang|sebuah|bergerak)|"
    r"placed at (?:our |the )?client|client's (?:site|side)|(?<!payroll )outsourc|alih daya|headhunt", re.I)


def agency_reason(job):
    """Why this job looks like it comes from a recruitment agency / outsourcing company, or None."""
    m = AGENCY_NAME_RX.search(job["company"] or "")
    if m:
        return f'Company name contains "{m.group(0)}"'
    m = AGENCY_TEXT_RX.search(job["title"] + "\n" + job["text"])
    if m:
        return f"Description: {snippet(job['title'] + chr(10) + job['text'], m)}"
    return None


# ---------------------------------------------------------------------------
# Score (0-100): experience 60 + competition 25 + freshness 15
# ---------------------------------------------------------------------------
def score(exp_years, applicants, posted, today):
    if exp_years is None:
        exp = 30
    else:
        exp = {0: 60, 1: 45, 2: 25, 3: 10}.get(int(exp_years), 0)

    if applicants is None:
        comp = 12
    elif applicants <= 25:
        comp = 25
    elif applicants <= 50:
        comp = 20
    elif applicants <= 100:
        comp = 14
    elif applicants <= 200:
        comp = 8
    else:
        comp = 3

    if posted is None:
        fresh = 7
    else:
        days = (today - datetime.fromisoformat(posted).date()).days
        fresh = 15 if days <= 3 else 12 if days <= 7 else 8 if days <= 14 else 4 if days <= 30 else 0

    return exp + comp + fresh, {"experience": exp, "competition": comp, "freshness": fresh}


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
NEXT_DATA_RX = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def glints_detail(job_id):
    """Only the fields we use (the full page data is large, and this goes into the cache)."""
    r = get(f"https://glints.com/id/opportunities/jobs/x/{job_id}")
    m = NEXT_DATA_RX.search(r.text) if r is not None and r.ok else None
    if not m:
        return {}
    try:
        d = json.loads(m.group(1))["props"]["pageProps"]["initialData"]["data"] or {}
    except (KeyError, TypeError, ValueError):
        return {}
    company, creator = d.get("company") or {}, d.get("creator") or {}
    slim = {k: d.get(k) for k in ("descriptionJsonString", "educationLevel", "gender", "minAge", "maxAge", "isActivelyHiring",
                                  "creatorResponseRate", "creatorResponseTime", "updatedAt", "expiryDate",
                                  "interviewProcessJsonString")}
    slim.update(
        creator={"name": creator.get("name"), "lastSeen": creator.get("lastSeen")},
        benefits=[{"title": b.get("title")} for b in d.get("benefits") or []],
        company={"industry": {"name": (company.get("industry") or {}).get("name")}, "size": company.get("size"),
                 "website": company.get("website"), "address": company.get("address"),
                 "descriptionJsonString": company.get("descriptionJsonString")},
        companyAddress={"poi": {"addressLabel": ((d.get("companyAddress") or {}).get("poi") or {}).get("addressLabel")}},
    )
    return slim


def src_glints():
    listing = {}
    for kw in SEARCH_KEYWORDS:
        r = get("https://glints.com/id/opportunities/jobs/explore",
                params={"keyword": kw, "country": "ID", "locationName": "All Cities/Provinces"})
        m = NEXT_DATA_RX.search(r.text) if r is not None and r.ok else None
        if m:
            page = json.loads(m.group(1))["props"]["pageProps"]
            for j in (page.get("initialJobs") or {}).get("jobsInPage") or []:
                listing.setdefault(j["id"], j)
        time.sleep(0.5)
    wanted = [j for j in listing.values() if classify(j["title"])]
    log(f"  Glints: {len(listing)} listings, {len(wanted)} engineering")
    full = fetch_details("glints", [j["id"] for j in wanted], glints_detail)

    out = []
    for j, d in zip(wanted, full):
        loc = j.get("location") or {}
        names = [loc.get("formattedName")]
        for p in loc.get("parents") or []:
            names.append(p.get("formattedName"))
            names += [g.get("formattedName") for g in p.get("parents") or []]
        location = ", ".join(dict.fromkeys(n for n in names if n)) or (j.get("city") or {}).get("name") or "Indonesia"
        salary = None
        if j.get("shouldShowSalary") and j.get("salaries"):
            s = j["salaries"][0]
            if s.get("CurrencyCode") in (None, "IDR"):
                salary = money(s.get("minAmount"), s.get("maxAmount"), (human(s.get("salaryMode")) or "month").lower())
        lo, hi = j.get("minYearsOfExperience"), j.get("maxYearsOfExperience")
        company = d.get("company") or {}
        creator = d.get("creator") or {}
        address = ((d.get("companyAddress") or {}).get("poi") or {}).get("addressLabel") or company.get("address")
        info = details(
            description=draftjs_text(d.get("descriptionJsonString")),
            facts=[("Employment type", human(j.get("type"))),
                   ("Work arrangement", human(j.get("workArrangementOption"))),
                   ("Education", human(d.get("educationLevel") or j.get("educationLevel"))),
                   ("Experience range", f"{lo}–{hi} years" if lo is not None and hi is not None else None),
                   ("Job category", (j.get("hierarchicalJobCategory") or {}).get("name")),
                   ("Gender preference", human(d.get("gender"))),
                   ("Age", f"{d.get('minAge') or '?'}–{d.get('maxAge') or '?'}" if d.get("minAge") or d.get("maxAge") else None),
                   ("Actively hiring", d.get("isActivelyHiring")),
                   ("Recruiter response rate", d.get("creatorResponseRate")),
                   ("Recruiter response time", d.get("creatorResponseTime"))],
            timeline=[("Posted", j.get("createdAt")), ("Updated", d.get("updatedAt") or j.get("updatedAt")),
                      ("Application deadline", d.get("expiryDate")), ("Recruiter last online", creator.get("lastSeen"))],
            benefits=[b.get("title") for b in d.get("benefits") or []],
            company={"industry": (company.get("industry") or {}).get("name"), "size": human(company.get("size")),
                     "website": company.get("website"), "address": address,
                     "about": draftjs_text(company.get("descriptionJsonString"))},
            recruiter={"name": creator.get("name")},
            hiring_steps=[line for line in draftjs_text(d.get("interviewProcessJsonString")).split("\n") if line],
        )
        out.append(make_job(
            "Glints", j["id"], j["title"], (j.get("company") or {}).get("name"), location,
            f"https://glints.com/id/opportunities/jobs/{slugify(j['title'])}/{j['id']}",
            posted=j.get("createdAt"), remote=j.get("workArrangementOption") == "REMOTE",
            exp_years=lo, salary=salary, info=info))
    return out


KALIBRR_PERKS = {"med_ins": "Medical insurance", "med_plans": "Medical plans", "mat_pat_leave": "Maternity/paternity leave",
                 "trans": "Transportation", "perf_bonus": "Performance bonus", "life_ins": "Life insurance",
                 "wfh": "Work from home", "sign_bonus": "Signing bonus"}


def src_kalibrr():
    out = []
    for offset in range(0, 3000, 100):
        r = get("https://www.kalibrr.com/kjs/job_board/search",
                params={"limit": 100, "offset": offset, "function": "IT and Software", "country": "Indonesia"})
        jobs = r.json().get("jobs", []) if r is not None and r.ok else []
        for j in jobs:
            addr = (j.get("google_location") or {}).get("address_components") or {}
            company = j.get("company") or {}
            company_info = j.get("company_info") or {}
            perks = j.get("perks") or {}
            salary = None
            if j.get("salary_shown") and j.get("salary_currency") in (None, "IDR"):
                salary = money(j.get("base_salary"), j.get("maximum_salary"), j.get("salary_interval") or "month")
            arrangement = "Work from home" if j.get("is_work_from_home") else "Hybrid" if j.get("is_hybrid") else "On site"
            rate = j.get("response_rate")
            info = details(
                description="\n\n".join(x for x in [section("Qualifications", strip_html(j.get("qualifications"))),
                                                    section("Job description", strip_html(j.get("description")))] if x),
                facts=[("Employment type", j.get("tenure")), ("Work arrangement", arrangement),
                       ("Openings", j.get("number_of_openings")),
                       ("Open to fresh graduates", j.get("is_open_to_fresh_grads")),
                       ("Function", j.get("function")),
                       ("Recruiter response rate", f"{rate:.0f}%" if isinstance(rate, (int, float)) else None)],
                timeline=[("Created", j.get("created_at")), ("Posted", j.get("activation_date")),
                          ("Application deadline", j.get("application_end_date")),
                          ("Recruiter last active", j.get("es_recruiter_last_seen"))],
                skills=[s.get("name") if isinstance(s, dict) else s for s in j.get("job_sds_skills") or []],
                benefits=[KALIBRR_PERKS.get(p) or human(p) for p in perks.get("types") or []] + [perks.get("other")],
                company={"industry": company.get("industry") or company_info.get("industry"),
                         "website": company_info.get("url"),
                         "about": strip_html(company_info.get("description") or company.get("description"))},
            )
            out.append(make_job(
                "Kalibrr", j["id"], j["name"], j.get("company_name") or company.get("name"),
                ", ".join(x for x in [addr.get("city"), addr.get("region")] if x) or "Indonesia",
                f"https://www.kalibrr.com/c/{company.get('code')}/jobs/{j['id']}/{j.get('slug', '')}",
                posted=j.get("activation_date") or j.get("created_at"), remote=j.get("is_work_from_home"),
                exp_years=0 if j.get("is_open_to_fresh_grads") else None,
                exp_label="Listing field: open to fresh graduates", salary=salary, info=info))
        if len(jobs) < 100:
            break
        time.sleep(0.3)
    return out


JOBSTREET_DETAIL_QUERY = """query jobDetails($jobId: ID!) { jobDetails(id: $jobId) { job {
  content(platform: WEB) status isExpired
  listedAt { dateTimeUtc } expiresAt { dateTimeUtc }
  salary { label } workTypes { label } products { bullets }
  tracking { classificationInfo { classification subClassification } }
} } }"""


def jobstreet_detail(job_id):
    q = {"operationName": "jobDetails", "variables": {"jobId": str(job_id)}, "query": JOBSTREET_DETAIL_QUERY}
    for _ in range(2):
        try:
            r = session.post("https://id.jobstreet.com/graphql", json=q, timeout=30,
                             headers={"seek-request-brand": "jobstreet", "seek-request-country": "ID"})
            if r.ok:
                return (((r.json().get("data") or {}).get("jobDetails") or {}).get("job")) or {}
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2)
    return {}


def src_jobstreet():
    listings = {}
    for where in JOBSTREET_PROVINCES:
        for page in range(1, JOBSTREET_MAX_PAGES + 1):
            r = get("https://id.jobstreet.com/api/jobsearch/v5/search",
                    params={"siteKey": "ID-Main", "sourcesystem": "houston", "page": page, "pageSize": 100,
                            "classification": "6281", "where": where, "locale": "en-ID"})
            data = r.json().get("data", []) if r is not None and r.ok else []
            for d in data:
                listings.setdefault(d["id"], (d, where))
            if len(data) < 100:
                break
            time.sleep(0.3)
    wanted = [(d, where) for d, where in listings.values() if classify(d.get("title"))]
    log(f"  JobStreet: {len(listings)} ICT listings, {len(wanted)} engineering")
    # 2 at a time: with 4, JobStreet refused about a third of the requests.
    full = fetch_details("jobstreet", [d["id"] for d, _ in wanted], jobstreet_detail, workers=2)

    out = []
    for (d, where), job in zip(wanted, full):
        arrangements = ", ".join(a.get("label", {}).get("text", "") for a in (d.get("workArrangements") or {}).get("data", []))
        classification = ((job.get("tracking") or {}).get("classificationInfo") or {})
        info = details(
            description=strip_html(job.get("content")) or d.get("teaser", ""),
            facts=[("Employment type", (job.get("workTypes") or {}).get("label") or ", ".join(d.get("workTypes") or [])),
                   ("Work arrangement", arrangements),
                   ("Category", " › ".join(x for x in [classification.get("classification"), classification.get("subClassification")] if x)),
                   ("Status", job.get("status"))],
            timeline=[("Posted", (job.get("listedAt") or {}).get("dateTimeUtc") or d.get("listingDate")),
                      ("Listing expires", (job.get("expiresAt") or {}).get("dateTimeUtc"))],
            benefits=(job.get("products") or {}).get("bullets") or d.get("bulletPoints") or [],
        )
        out.append(make_job(
            "JobStreet", d["id"], d["title"], d.get("companyName") or (d.get("advertiser") or {}).get("description"),
            ", ".join(l.get("label", "") for l in d.get("locations") or []) or where,
            f"https://id.jobstreet.com/job/{d['id']}", posted=d.get("listingDate"),
            remote="remote" in arrangements.lower(), salary=(job.get("salary") or {}).get("label") or d.get("salaryLabel") or None,
            province_hint=where, info=info))
    return out


LI_CARD_RX = {
    "id": re.compile(r"urn:li:jobPosting:(\d+)"),
    "title": re.compile(r'base-search-card__title[^>]*>\s*(.*?)\s*</h3>', re.S),
    "company": re.compile(r'base-search-card__subtitle[^>]*>.*?(?:<a[^>]*>)?\s*([^<]+?)\s*(?:</a>|</h4>)', re.S),
    "location": re.compile(r'job-search-card__location[^>]*>\s*(.*?)\s*</span>', re.S),
    "date": re.compile(r'<time[^>]*datetime="([\d-]+)"'),
}
LI_CRITERIA_RX = re.compile(r'description__job-criteria-subheader[^>]*>\s*([^<]+?)\s*<.*?'
                            r'description__job-criteria-text[^>]*>\s*([^<]+?)\s*<', re.S)


def linkedin_cards(page_html):
    cards = []
    for block in page_html.split("<li>")[1:]:
        f = {k: rx.search(block) for k, rx in LI_CARD_RX.items()}
        if not f["id"] or not f["title"]:
            continue
        cards.append({k: clean(v.group(1)) if v else "" for k, v in f.items()})
    return cards


def linkedin_detail(job_id):
    """Returns dict(applicants, description, facts), or None when rate-limited."""
    r = get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}")
    if r is None or r.status_code == 429:
        return None
    if not r.ok:
        return {}
    applicants = None
    m = re.search(r"num-applicants__caption[^>]*>\s*([^<]+?)\s*<", r.text)
    if m:
        n = re.search(r"(\d[\d,.]*)", m.group(1))
        if n:
            applicants = int(re.sub(r"[,.]", "", n.group(1))) + (1 if re.search(r"over|lebih", m.group(1), re.I) else 0)
    d = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', r.text, re.S)
    return {"applicants": applicants, "description": strip_html(d.group(1)) if d else "",
            "facts": [(clean(k), clean(v)) for k, v in LI_CRITERIA_RX.findall(r.text)]}


def src_linkedin():
    cards = {}
    for kw in LINKEDIN_KEYWORDS:
        for page in range(LINKEDIN_PAGES):
            r = get("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                    params={"keywords": kw, "location": "Indonesia", "f_TPR": "r2592000", "start": page * 10})
            got = linkedin_cards(r.text) if r is not None and r.ok else []
            if not got:
                break
            for c in got:
                cards.setdefault(c["id"], c)
            time.sleep(1)
    wanted = [c for c in cards.values() if classify(c["title"]) and province_of(c["location"]) is not None]
    # Spend the limited detail budget on jobs that are not obviously senior first.
    wanted.sort(key=lambda c: (years_from_title(c["title"]) or 0) >= 4)
    out, blocked, fetched, reused = [], False, 0, 0
    for c in wanted:
        key = f"linkedin:{c['id']}"
        res = cache.get(key, DETAIL_MAX_AGE_HOURS)
        if res is not None:
            reused += 1
        elif fetched < LINKEDIN_MAX_DETAILS and not blocked:
            res = linkedin_detail(c["id"])
            fetched += 1
            if res is None:
                blocked = True
                log(f"  LinkedIn: rate-limited after {fetched - 1} new detail pages; the rest use older cached data or none")
            elif res:
                cache.put(key, res)
            time.sleep(1)
        res = res or cache.get(key) or {}  # older cached copy if this run couldn't fetch it
        info = details(description=res.get("description", ""), facts=res.get("facts", []), timeline=[("Posted", c["date"])])
        out.append(make_job("LinkedIn", c["id"], c["title"], c["company"], c["location"],
                            f"https://www.linkedin.com/jobs/view/{c['id']}/", posted=c["date"] or None,
                            remote="remote" in c["location"].lower(), applicants=res.get("applicants"), info=info))
    log(f"  LinkedIn: {len(cards)} cards, {len(wanted)} engineering on Java/remote; "
        f"{reused} details reused from cache, {fetched} fetched")
    return out


def src_dealls():
    docs, page = [], 1
    while True:
        r = get("https://api.sejutacita.id/v1/explore-job/job",
                params={"page": page, "limit": 50, "categorySlug": "it-and-software-engineering"})
        data = (r.json().get("data") or {}) if r is not None and r.ok else {}
        docs += data.get("docs", [])
        if page >= (data.get("totalPages") or 0):
            break
        page += 1

    def detail(job_id):
        r = get(f"https://api.sejutacita.id/v1/job-portal/job/{job_id}")
        res = ((r.json().get("data") or {}).get("result") or {}) if r is not None and r.ok else {}
        return {k: res.get(k) for k in ("responsibilities", "requirements", "description", "jobRole", "jobRoleSubCategory",
                                        "cvRequired", "portofolioRequired", "perks", "customPerks", "recruitmentSteps")} if res else {}

    full = fetch_details("dealls", [d["id"] for d in docs], detail)
    out = []
    for d, res in zip(docs, full):
        company = d.get("company") or {}
        insight = company.get("insight") or {}
        pref = d.get("candidatePreference") or {}
        age = pref.get("age") or {}
        sr = d.get("salaryRange") or {}
        author = d.get("author") or {}
        info = details(
            description="\n\n".join(x for x in [section("Responsibilities", strip_html(res.get("responsibilities"))),
                                                section("Requirements", strip_html(res.get("requirements"))),
                                                section("Description", strip_html(res.get("description")))] if x),
            facts=[("Employment type", ", ".join(human(t) for t in d.get("employmentTypes") or [])),
                   ("Work arrangement", human(d.get("workplaceType"))),
                   ("Role", (res.get("jobRole") or {}).get("name")),
                   ("Sub-category", (res.get("jobRoleSubCategory") or {}).get("name")),
                   ("Views", (d.get("stats") or {}).get("viewCount")),
                   ("Minimum GPA", pref.get("minimumGpa")),
                   ("Gender preference", pref.get("gender")),
                   ("Age", f"{age.get('min') or '?'}–{age.get('max') or '?'}" if age.get("restriction") else None),
                   ("CV required", res.get("cvRequired")),
                   ("Portfolio required", res.get("portofolioRequired")),
                   ("Urgently needed", d.get("urgentlyNeeded"))],
            timeline=[("Posted", d.get("publishedAt")), ("Updated by employer", d.get("updatedAtByEmployer")),
                      ("Recruiter last actively hiring", d.get("lastActivelyHiringAt"))],
            skills=[s.get("name") for s in d.get("skills") or []],
            benefits=[human(b) for b in insight.get("benefits") or []]
                     + [step_name(p) for p in as_list(res.get("perks")) + as_list(res.get("customPerks"))],
            company={"sector": company.get("sector"), "funding stage": human(insight.get("fundingStage")),
                     "working policy": ", ".join(human(w) for w in insight.get("workingPolicies") or [])},
            recruiter={"name": author.get("name"), "email": author.get("email")},
            hiring_steps=as_list(res.get("recruitmentSteps")),
        )
        out.append(make_job(
            "Dealls", d["id"], d["role"], company.get("name"), (d.get("city") or {}).get("name") or "Indonesia",
            f"https://dealls.com/loker/{d['slug']}~{company.get('slug')}", posted=d.get("publishedAt"),
            remote=d.get("workplaceType") == "remote", applicants=(d.get("stats") or {}).get("applicantCount"),
            salary=money(sr.get("start"), sr.get("end")), info=info))
    return out


def src_greenhouse(slug, name):
    r = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
    out = []
    for j in (r.json().get("jobs", []) if r is not None and r.ok else []):
        location = (j.get("location") or {}).get("name", "")
        info = details(
            description=strip_html(html.unescape(j.get("content", ""))),
            facts=[("Department", ", ".join(x.get("name", "") for x in j.get("departments") or [])),
                   ("Office", ", ".join(x.get("name", "") for x in j.get("offices") or []))],
            timeline=[("Posted", j.get("first_published")), ("Updated", j.get("updated_at"))])
        out.append(make_job("Company site", j["id"], j["title"], name, location, j["absolute_url"],
                            posted=j.get("first_published") or j.get("updated_at"),
                            remote="remote" in location.lower(), indonesian_board=False, info=info))
    return out


def src_lever(slug, name):
    r = get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    out = []
    for j in (r.json() if r is not None and r.ok else []):
        cat = j.get("categories") or {}
        location = "; ".join(dict.fromkeys([cat.get("location") or ""] + (cat.get("allLocations") or [])))
        info = details(
            description="\n\n".join(x for x in [tidy(j.get("descriptionPlain"))]
                                    + [section(l.get("text", ""), strip_html(l.get("content"))) for l in j.get("lists") or []]
                                    + [tidy(j.get("additionalPlain"))] if x),
            facts=[("Employment type", cat.get("commitment")), ("Team", cat.get("team")),
                   ("Department", cat.get("department")), ("Work arrangement", human(j.get("workplaceType")))],
            timeline=[("Posted", j.get("createdAt"))])
        out.append(make_job("Company site", j["id"], j["text"], name, location, j["hostedUrl"], posted=j.get("createdAt"),
                            remote=j.get("workplaceType") == "remote", indonesian_board=False, info=info))
    return out


def src_smartrecruiters(slug, name):
    items, offset = [], 0
    while True:
        r = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 100, "offset": offset})
        data = r.json() if r is not None and r.ok else {}
        items += data.get("content", [])
        offset += 100
        if offset >= (data.get("totalFound") or 0):
            break
    wanted = [p for p in items
              if ((p.get("location") or {}).get("country") or "").lower() == "id" and classify(p.get("name"))]

    def detail(posting_id):
        r = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}")
        d = r.json() if r is not None and r.ok else {}
        return {k: d.get(k) for k in ("postingUrl", "jobAd", "typeOfEmployment", "experienceLevel", "function",
                                      "industry", "department")} if d else {}

    out = []
    for p, d in zip(wanted, fetch_details(f"smartrecruiters:{slug}", [p["id"] for p in wanted], detail, workers=2)):
        loc = p.get("location") or {}
        sec = (d.get("jobAd") or {}).get("sections") or {}
        def label(key):
            return label_of(d.get(key) or p.get(key))
        info = details(
            description="\n\n".join(x for x in [section((sec.get(k) or {}).get("title") or human(k), strip_html((sec.get(k) or {}).get("text")))
                                                for k in ("jobDescription", "qualifications", "additionalInformation")] if x),
            facts=[("Employment type", label("typeOfEmployment")), ("Experience level", label("experienceLevel")),
                   ("Function", label("function")), ("Industry", label("industry")), ("Department", label("department"))],
            timeline=[("Posted", p.get("releasedDate"))],
            company={"about": strip_html((sec.get("companyDescription") or {}).get("text"))})
        location = loc.get("fullLocation") or ", ".join(x for x in [loc.get("city"), loc.get("region"), "Indonesia"] if x)
        out.append(make_job("Company site", p["id"], p["name"], (p.get("company") or {}).get("name") or name, location,
                            d.get("postingUrl") or f"https://jobs.smartrecruiters.com/{slug}/{p['id']}",
                            posted=p.get("releasedDate"), remote=loc.get("remote"), indonesian_board=False, info=info))
    return out


def src_workable(slug, name):
    r = get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}", params={"details": "true"})
    out = []
    for j in (r.json().get("jobs", []) if r is not None and r.ok else []):
        locs = j.get("locations") or [{"city": j.get("city"), "region": j.get("state"), "country": j.get("country")}]
        location = "; ".join(", ".join(x for x in [l.get("city"), l.get("region"), l.get("country")] if x) for l in locs)
        info = details(
            description=strip_html(j.get("description")),
            facts=[("Employment type", j.get("employment_type")), ("Experience level", j.get("experience")),
                   ("Education", j.get("education")), ("Function", j.get("function")),
                   ("Industry", j.get("industry")), ("Department", j.get("department"))],
            timeline=[("Created", j.get("created_at")), ("Posted", j.get("published_on"))])
        out.append(make_job("Company site", j["shortcode"], j["title"], name, location, j.get("url") or j.get("shortlink"),
                            posted=j.get("published_on") or j.get("created_at"), remote=j.get("telecommuting"),
                            indonesian_board=False, info=info))
    return out


def src_traveloka():
    """Traveloka's own careers site: JSON list API + description from each job page."""
    headers = {"Origin": "https://careers.traveloka.com", "Referer": "https://careers.traveloka.com/"}
    jobs, page = [], 1
    while True:
        r = get("https://careers-api.mte.traveloka.com/career/jobs/search",
                params={"location": "ID", "limit": 100, "page": page}, headers=headers)
        data = (r.json().get("data") or {}) if r is not None and r.ok else {}
        jobs += data.get("jobs") or []
        if page >= (data.get("lastPage") or 0):
            break
        page += 1

    def description(link):
        r = get("https://careers.traveloka.com" + link)
        m = re.search(r"Job Description</h1>\s*<span[^>]*>(.*?)</span>\s*</div>", r.text, re.S) if r is not None and r.ok else None
        return strip_html(m.group(1)) if m else ""

    wanted = [j for j in jobs if classify(j.get("title"))]
    out = []
    for j, text in zip(wanted, fetch_details("traveloka", [j["link"] for j in wanted], description, empty="")):
        info = details(description=text,
                       facts=[("Employment type", j.get("employmentType")), ("Department", j.get("department"))],
                       timeline=[("Posted", j.get("createdAt"))])
        out.append(make_job("Company site", j["requisitionId"], j["title"], "Traveloka", j.get("location"),
                            "https://careers.traveloka.com" + j["link"], posted=j.get("createdAt"),
                            indonesian_board=False, info=info))
    return out


def src_shopee():
    """Shopee's own careers site (careers.shopee.co.id). Locations come as region codes listed in /api/meta/."""
    base = "https://careers.shopee.co.id/api/"
    r = get(base + "meta/")
    meta = r.json() if r is not None and r.ok else {}
    regions = {x["value"]: x["default_text"] for x in meta.get("regions") or []}
    levels = {x["value"]: x["default_text"] for x in meta.get("position_levels") or []}
    departments = {x["value"]: x["default_text"] for x in meta.get("departments") or []}

    items = []
    for offset in range(0, 20000, 100):
        r = get(base + "positions/search/", params={"limit": 100, "offset": offset})
        page = r.json().get("positions", []) if r is not None and r.ok else []
        items += page
        if len(page) < 100:
            break
    wanted = [p for p in items
              if regions.get(p.get("region"), "").startswith("Indonesia") and classify(p.get("position_name"))]

    def detail(position_id):
        r = get(base + "positions/detail/", params={"id": position_id})
        pres = ((r.json() if r is not None and r.ok else {}).get("position_presentation") or [{}])[0]
        return {k: pres.get(k) for k in ("sub_team_description", "job_description", "job_requirement")} if pres else {}

    out = []
    for p, pres in zip(wanted, fetch_details("shopee", [p["id"] for p in wanted], detail)):
        info = details(
            description="\n\n".join(x for x in [section("About the team", strip_html(pres.get("sub_team_description"))),
                                                section("Job description", strip_html(pres.get("job_description"))),
                                                section("Requirements", strip_html(pres.get("job_requirement")))] if x),
            facts=[("Level", levels.get(p.get("position_level"))), ("Department", departments.get(p.get("dept_id"))),
                   ("Job ID", p.get("external_job_id"))])
        out.append(make_job("Company site", p["id"], p["position_name"], "Shopee", regions.get(p.get("region")),
                            f"https://careers.shopee.co.id/job-detail/{p['id']}/", indonesian_board=False, info=info))
    return out


def src_companies():
    companies = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))
    fetchers = {"greenhouse": src_greenhouse, "lever": src_lever,
                "smartrecruiters": src_smartrecruiters, "workable": src_workable}
    jobs = [(f"{platform}/{slug}", lambda f=fetch, s=slug, n=name: f(s, n))
            for platform, fetch in fetchers.items() for slug, name in (companies.get(platform) or {}).items()]
    jobs += [("traveloka", src_traveloka), ("shopee", src_shopee)]
    out = []
    for label, fetch in jobs:
        try:
            out += fetch()
        except Exception as e:  # one broken company page should not stop the run
            log(f"  {label} failed: {e}")
    return out


SOURCES = {
    "Glints": src_glints,
    "Kalibrr": src_kalibrr,
    "JobStreet": src_jobstreet,
    "LinkedIn": src_linkedin,
    "Dealls": src_dealls,
    "Company site": src_companies,
}


# ---------------------------------------------------------------------------
# Combine, dedupe, score, write
# ---------------------------------------------------------------------------
def norm(s):
    s = re.sub(r"\b(pt|tbk|persero|cv)\b\.?", "", (s or "").lower())
    return re.sub(r"[^a-z0-9]+", "", s)


TITLE_NOISE = re.compile(r"placement|penempatan|remote|hybrid|\bwf[oh]\b|on-?site|urgent\w*|immediate\w*|hiring|"
                         r"lokasi|location|based|\barea\b|\bkota\b|\bkab\b", re.I)


def is_noise(part):
    """True for title parts that only say where/how: '(Surakarta)', '(Placement: Jakarta)', '- Remote', '[URGENT]'."""
    return len(part) < 45 and bool(TITLE_NOISE.search(part) or any(rx.search(part) for _, rx in PROVINCE_RX))


def title_core(title):
    t = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", lambda m: " " if is_noise(m.group(0)[1:-1]) else m.group(0), title or "")
    t = re.sub(r"\s+[-–|]\s*([^-–|]+)$", lambda m: "" if is_noise(m.group(1)) else m.group(0), t)
    return norm(t)


def exact_key(j):
    return f"{norm(j['title'])}|{norm(j['company'])}|{j['province']}"


def job_key(j):
    """Same job across sources and runs. Location / placement notes in the title are ignored, so
    'Developer (Surakarta)' and 'Developer (Placement: Surakarta)' at the same company count as one job."""
    return f"{title_core(j['title'])}|{norm(j['company'])}|{j['province']}"


def finalize(raw):
    today = datetime.now(timezone.utc).date()
    jobs = []
    for j in raw:
        category = classify(j["title"])
        if not category:
            continue
        province = province_of(j["location"], j.pop("province_hint"), j.pop("indonesian_board"))
        if province is None:
            continue
        years, basis = experience(j)
        deadline = next((d for label, d in j["details"].get("timeline", [])
                         if label in ("Application deadline", "Listing expires")), None)
        j.update(category=category, province=province, exp_years=years, exp_basis=basis,
                 remote=j["remote"] or province == UNSPECIFIED, deadline=deadline, agency=agency_reason(j))
        jobs.append(j)

    # Same title + company + province from several sources -> keep the richest record, link the rest.
    def richness(j):
        return ((j["applicants"] is not None) * 2 + (j["exp_basis"].startswith(("Listing", "Description"))) * 2
                + bool(j["salary"]) + bool(j["posted"]) + bool(j["details"].get("description")))

    groups = {}
    for j in jobs:
        groups.setdefault(job_key(j), []).append(j)
    final = []
    for group in groups.values():
        group.sort(key=richness, reverse=True)
        best = group[0]
        best["also"] = [{"source": g["source"], "url": g["url"]} for g in group[1:] if g["url"] != best["url"]]
        if best["applicants"] is None:
            best["applicants"] = next((g["applicants"] for g in group if g["applicants"] is not None), None)
        best["agency"] = next((g["agency"] for g in group if g["agency"]), None)
        best["deadline"] = best["deadline"] or next((g["deadline"] for g in group if g["deadline"]), None)
        best["key"] = job_key(best)  # stable id across runs; the website's application tracking uses it
        # Exact-title keys of every merged record (older versions used these as the key) keep tracking working.
        best["aliases"] = sorted({exact_key(g) for g in group} - {best["key"]})
        best["score"], best["parts"] = score(best["exp_years"], best["applicants"], best["posted"], today)
        del best["text"], best["exp_label"]
        final.append(best)
    final.sort(key=lambda j: j["posted"] or "", reverse=True)
    final.sort(key=lambda j: j["score"], reverse=True)  # stable: highest score, then newest
    return final


def read_js(path):
    """Value stored in a 'window.X = {...};' data file, or None."""
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text[text.index("=") + 1:].strip().rstrip(";"))
    except (OSError, ValueError):
        return None


def write_js(name, var, value):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{name}.js").write_text(
        f"window.{var} = " + json.dumps(value, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")


def write_list(name, var, generated, items, extra=None):
    """A light list file (what the cards need) + a '-details' file the page loads in the background."""
    write_js(name, var, {"generated": generated, **(extra or {}), "jobs": [{k: v for k, v in j.items() if k != "details"} for j in items]})
    write_js(f"{name}-details", var.replace("_DATA", "_DETAILS"), {j["key"]: j.get("details", {}) for j in items})


def previous_jobs():
    data = read_js(DATA_DIR / "jobs.js") or read_js(LEGACY_OUT_FILE) or {}
    return data.get("jobs", []), (data.get("generated") or "")[:10]


def lookup(store, j):
    """Entry for this job under its key, or under one of its older keys (moved to the current key)."""
    for k in [j["key"]] + j.get("aliases", []):
        if k in store:
            if k != j["key"]:
                store[j["key"]] = store.pop(k)
            return store[j["key"]]
    return None


def mark_new(jobs, today):
    """Set first_seen / new on each job using seen.json (seeded from the previous output on first use)."""
    seen = {}
    if SEEN_FILE.exists():
        seen = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    else:
        prev, prev_date = previous_jobs()
        for j in prev:
            seen[j.get("key") or job_key(j)] = [j.get("first_seen") or prev_date or today, prev_date or today]
    first_run = not seen
    for j in jobs:
        entry = lookup(seen, j)
        if entry:
            entry[1] = today
        else:
            seen[j["key"]] = [today, today]
        j["first_seen"] = seen[j["key"]][0]
        j["new"] = not first_run and not entry  # not in any earlier run
    cutoff = (datetime.fromisoformat(today) - timedelta(days=SEEN_KEEP_DAYS)).date().isoformat()
    seen = {k: v for k, v in seen.items() if v[1] >= cutoff}
    SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=0), encoding="utf-8")


def record_history(items, today):
    """Remember applicant / bid counts over time (history.json). A point is added when the count changes,
    or when the last point is a week old. Jobs with 2+ points get 'applicants_history' for the popup."""
    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        history = {}
    for j in items:
        points = lookup(history, j) or []
        if j.get("applicants") is not None:
            last = points[-1] if points else None
            if last and last[0] == today:
                last[1] = j["applicants"]
            elif not last or last[1] != j["applicants"] or \
                    (datetime.fromisoformat(today) - datetime.fromisoformat(last[0])).days >= 7:
                points.append([today, j["applicants"]])
            history[j["key"]] = points
        if len(points) >= 2:
            j["applicants_history"] = points
    cutoff = (datetime.fromisoformat(today) - timedelta(days=HISTORY_KEEP_DAYS)).date().isoformat()
    history = {k: v for k, v in history.items() if v and v[-1][0] >= cutoff}
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def save_section(section, value, generated):
    """Write one tab's data files. 'remote' gets applicant / bid history first."""
    if section == "programs":
        write_js("programs", "PROGRAMS_DATA", {"generated": generated, "programs": value})
    elif section == "remote":
        record_history(value, generated[:10])
        write_list("remote", "REMOTE_DATA", generated, value)


def main():
    started = datetime.now(timezone.utc)
    raw, stats = [], {}
    for name, fetch in SOURCES.items():
        log(f"[{name}] fetching…")
        t0 = time.time()
        try:
            got = fetch()
            stats[name] = {"fetched": len(got), "ok": True}
        except Exception as e:  # keep going with the other sources
            got = []
            stats[name] = {"fetched": 0, "ok": False, "error": str(e)[:200]}
            log(f"[{name}] FAILED: {e}")
        log(f"[{name}] {len(got)} listings in {time.time() - t0:.0f}s")
        raw += got

    jobs = finalize(raw)
    today, generated = started.date().isoformat(), started.isoformat(timespec="seconds")
    mark_new(jobs, today)
    record_history(jobs, today)
    for name in stats:
        stats[name]["kept"] = sum(1 for j in jobs if j["source"] == name)
    write_list("jobs", "JOBS_DATA", generated, jobs, {"sources": stats})
    counts = {"jobs": len(jobs)}
    # programs.py and remote.py import this module, so they are imported here rather than at the top.
    for key, label, module, func in [("programs", "Programs", "programs", "collect_programs"),
                                     ("remote", "Remote & freelance", "remote", "collect_remote")]:
        log(f"[{label}] collecting…")
        try:
            value = getattr(__import__(module), func)()
            save_section(key, value, generated)
            counts[key] = len(value)
        except Exception as e:  # the tab keeps its previous data files
            log(f"[{label}] FAILED: {e}")
    cache.save()
    if LEGACY_OUT_FILE.exists():
        LEGACY_OUT_FILE.unlink()  # replaced by site/data/*.js
    size = sum(f.stat().st_size for f in DATA_DIR.glob("*.js")) / 1e6
    log(f"\nDone in {(datetime.now(timezone.utc) - started).seconds // 60} min: {counts} written to {DATA_DIR} ({size:.1f} MB)")
    for name, s in stats.items():
        log(f"  {name:13} fetched {s['fetched']:5}  kept {s['kept']:5}" + ("" if s["ok"] else f"  ERROR: {s['error']}"))


def update_section(key, collect):
    """Refresh one tab (programs / remote) without re-running the job boards."""
    value = collect()
    save_section(key, value, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    cache.save()
    log(f"Done: {len(value)} {key} entries written to {DATA_DIR}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import scrape  # run as the importable module so programs.py / remote.py share its cache and session
    scrape.main()
