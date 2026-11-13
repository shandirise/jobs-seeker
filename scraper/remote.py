"""
Remote jobs and freelance projects from anywhere in the world that people living in Indonesia can take.

Kept only when:
  - the listing accepts Indonesia: worldwide / anywhere, Asia-Pacific, or Indonesia is in its country list
  - English is enough (listings asking for another language, or written in another language, are dropped)
  - it is an IT role (engineering, UI/UX, data, security, IT support, tech product/project, technical writing)

Runs as part of scrape.py, or on its own:  python scraper/remote.py
Each source is read at most once every REMOTE_MAX_AGE_HOURS; the result is kept in cache.json.
"""
import html
import re
import sys
import time
from datetime import date
from email.utils import parsedate_to_datetime

from scrape import (CATEGORIES, cache, clean, details, experience, get, log, norm, score, strip_html, title_core,
                    to_date, update_section)

REMOTE_MAX_AGE_HOURS = 6
FX_MAX_AGE_HOURS = 24             # exchange rates are fetched at most once a day
HOURS_PER_MONTH = 160             # hourly pay -> monthly
PER_MONTH = {"year": 1 / 12, "month": 1, "hour": HOURS_PER_MONTH}
DESCRIPTION_MAX = 6000            # characters kept per listing (keeps site/data small)
HIMALAYAS_MAX_PAGES = 120         # 20 jobs per page
FREELANCER_MAX_PROJECTS = 300     # newest active projects
FREELANCER_SKILLS = {3: "PHP", 13: "Python", 9: "JavaScript", 7: "Java", 17: "Website Design", 69: "WordPress",
                     44: "Mobile App Development", 59: "Android", 1067: "iOS Development", 759: "React.js",
                     500: "Node.js", 669: "Laravel", 292: "Machine Learning (ML)", 167: "Software Testing",
                     959: "UI / User Interface", 1678: "DevOps"}
SKILL_CATEGORY = {"Mobile App Development": "Mobile", "Android": "Mobile", "iOS Development": "Mobile",
                  "Machine Learning (ML)": "AI / ML", "Software Testing": "QA / Testing", "DevOps": "DevOps / Cloud",
                  "UI / User Interface": "UI/UX & Design", "Website Design": "UI/UX & Design",
                  "PHP": "Backend", "Laravel": "Backend", "Python": "Backend", "Java": "Backend", "Node.js": "Backend",
                  "JavaScript": "Frontend", "React.js": "Frontend"}

# ---------------------------------------------------------------------------
# Role: every IT field
# ---------------------------------------------------------------------------
EXTRA_IT = [(name, re.compile(rx, re.I)) for name, rx in [
    ("UI/UX & Design", r"\bui\b|\bux\b|user experience|user interface|product design|interaction design|web design"),
    ("Data & Analytics", r"data analy|business intelligence|\bbi\b|analytics|data visuali|tableau|power bi"),
    ("Security", r"security|cyber|penetration|pentest|\bsoc\b|infosec"),
    ("IT Support & SysAdmin", r"\bit support|technical support|tech support|help ?desk|system administrator|sysadmin|"
                              r"network (?:engineer|admin)|it specialist|desktop support|\bit technician|\bnoc\b"),
    ("Product & Project (tech)", r"product manager|product owner|technical project manager|technical program manager|"
                                 r"scrum master|engineering manager|delivery manager"),
    ("Technical Writing", r"technical writer|documentation|developer advocate|devrel|developer relations"),
]]
NOT_IT = re.compile(
    r"sales|marketing|recruit|talent acquisition|account (?:manager|executive)|business develop|"
    r"customer (?:success|service|support|care|experience)|copywrit|content (?:writer|creator|marketing|moderat)|"
    r"teacher|tutor|trainer|annotat|accountant|bookkeep|legal|lawyer|nurse|doctor|physician|therap|driver|warehouse|"
    r"virtual assistant|data entry|social media|\bseo\b|translator|transcri|\bhr\b|human resources|payroll", re.I)


def classify_it(title):
    t = title or ""
    if NOT_IT.search(t) and not re.search(r"\b(?:engineer|developer|programmer|architect)s?\b", t, re.I):
        return None
    # Specific engineering roles, then the other IT fields, then AI / ML and the generic "developer" bucket,
    # so "UI Designer - AI app" is UI/UX rather than AI / ML.
    engineering = CATEGORIES[:-2]
    for name, rx in engineering + EXTRA_IT + CATEGORIES[-2:]:
        if rx.search(t):
            return name
    return None


# ---------------------------------------------------------------------------
# Who may apply
# ---------------------------------------------------------------------------
def region_of(text):
    """'Worldwide' / 'Asia-Pacific' / 'Includes Indonesia', or None when Indonesia is not clearly accepted."""
    t = (text or "").lower()
    if "indonesia" in t:
        return "Includes Indonesia"
    if re.search(r"anywhere in the (?!world)|\bonly\b", t) and not re.search(r"asia|apac", t):
        return None  # "USA Only", "Anywhere in the US"
    if re.search(r"worldwide|anywhere|global|all countries|no location restriction", t):
        return "Worldwide"
    if re.search(r"\bapac\b|asia|south[- ]?east asia", t):
        return "Asia-Pacific"
    return None


# ---------------------------------------------------------------------------
# English is enough
# ---------------------------------------------------------------------------
OTHER_LANGS = (r"german|french|spanish|portuguese|italian|dutch|japanese|korean|mandarin|chinese|cantonese|arabic|"
               r"hebrew|russian|polish|turkish|swedish|norwegian|danish|finnish|czech|hungarian|romanian|greek|thai|"
               r"vietnamese|hindi|ukrainian")
LANG_NEEDED = re.compile(
    rf"\b(?:fluent|fluency|native|proficien\w*|business[- ]level|bilingual|speak\w*|written and spoken)\b[^.\n]{{0,40}}\b(?:{OTHER_LANGS})\b"
    rf"|\b(?:{OTHER_LANGS})\b[- ]?(?:speaker|speaking|speaks|fluency|fluent|native|language skills|is (?:a must|required|mandatory))",
    re.I)
LANG_IN_TITLE = re.compile(rf"\b(?:{OTHER_LANGS})\b", re.I)
EN_WORDS = re.compile(r"\b(?:the|and|you|with|for|our|we|will|are|to|of|is|your)\b", re.I)
FOREIGN_WORDS = re.compile(r"\b(?:und|der|das|wir|für|mit|nicht|auf|los|las|para|con|una|que|del|por|como|você|não|são|"
                           r"uma|les|des|pour|avec|vous|nous|dans|une|het|een|voor|wij|zijn|och|att|jest|się)\b", re.I)


def english_only(title, text):
    if LANG_IN_TITLE.search(title or ""):
        return False
    sample = (text or "")[:4000]
    if LANG_NEEDED.search(sample):
        return False
    return len(EN_WORDS.findall(sample)) >= 2 * len(FOREIGN_WORDS.findall(sample))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def any_date(value):
    """ISO / RFC 2822 ('Wed, 12 Nov 2026 10:00:00 +0000') / epoch seconds -> 'YYYY-MM-DD'."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        return to_date(int(value) * 1000)
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return to_date(value)


def num(v):
    try:
        return float(v) if v not in (None, "", "None") and float(v) > 0 else None
    except (TypeError, ValueError):
        return None


def period_of(text):
    t = (text or "").lower()
    return "year" if ("year" in t or "annual" in t) else "month" if "month" in t else "hour" if "hour" in t else None


def fx_rates():
    """Exchange rates against USD from open.er-api.com (free, no account), fetched at most once a day.
    Falls back to the last saved rates when the site can't be reached."""
    rates = cache.get("fx:USD", FX_MAX_AGE_HOURS)
    if rates:
        return rates
    r = get("https://open.er-api.com/v6/latest/USD")
    data = r.json() if r is not None and r.ok else {}
    if data.get("result") == "success" and (data.get("rates") or {}).get("IDR"):
        rates = {"rates": data["rates"], "updated": data.get("time_last_update_utc")}
        cache.put("fx:USD", rates)
        return rates
    return cache.get("fx:USD")


def to_idr(amount, currency, rates):
    table = (rates or {}).get("rates") or {}
    cur = (currency or "USD").upper()
    if not amount or cur not in table or "IDR" not in table:
        return None
    return amount / table[cur] * table["IDR"]


def rupiah(v):
    return (f"{v / 1e6:,.1f}".rstrip("0").rstrip(".") + " jt") if v >= 1e6 else f"{v / 1e3:,.0f} rb"


def rupiah_range(lo, hi):
    lo, hi = lo or hi, hi or lo
    return f"Rp {rupiah(lo)}" + (f" – {rupiah(hi)}" if round(hi) != round(lo) else "")


def salary_label(lo, hi, currency="USD", period="year"):
    lo, hi = num(lo), num(hi)
    if not lo and not hi:
        return None
    amount = f"{lo:,.0f} – {hi:,.0f}" if lo and hi and lo != hi else f"{(hi or lo):,.0f}"
    return f"{currency or 'USD'} {amount} / {(period or 'year').lower()}"


def as_list(v):
    if isinstance(v, list):
        return [clean(x) for x in v if x]
    return [clean(x) for x in str(v or "").split(",") if clean(x)]


def remote_item(source, sid, title, company, region, url, *, who="", kind="Remote job", posted=None, deadline=None,
                text="", salary=None, pay=None, applicants=None, facts=(), skills=(), category=None):
    """pay = (min, max, currency, period) as numbers/text, used to show the pay in Rupiah."""
    text = (text or "")[:DESCRIPTION_MAX]
    posted, deadline = any_date(posted), any_date(deadline)
    key = f"remote|{source}|{sid}" if kind == "Freelance project" else f"remote|{norm(title)}|{norm(company)}"
    lo, hi, currency, period = pay or (None, None, None, None)
    return {
        "source": source, "id": f"{source}:{sid}", "key": key, "kind": kind, "title": clean(title),
        "company": clean(company), "region": region, "province": region, "location": clean(who) or region,
        "url": url, "posted": posted, "deadline": deadline, "remote": True, "applicants": applicants,
        "salary": salary, "category": category or classify_it(title), "exp_years": None, "exp_label": None,
        "pay": {"min": num(lo), "max": num(hi), "currency": currency, "period": period} if (num(lo) or num(hi)) else None,
        "text": text,
        "details": details(description=text,
                           facts=[("Type", kind), ("Who can apply", clean(who) or region)] + list(facts),
                           timeline=[("Posted", posted), ("Expires", deadline)], skills=skills),
    }


def rss_tag(item, name):
    m = re.search(rf"<{name}>(.*?)</{name}>", item, re.S)
    if not m:
        return ""
    v = re.sub(r"^\s*<!\[CDATA\[(.*?)\]\]>\s*$", r"\1", m.group(1), flags=re.S)
    return html.unescape(v).strip()


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def src_weworkremotely():
    feeds = ["remote-jobs", "categories/remote-programming-jobs", "categories/remote-back-end-programming-jobs",
             "categories/remote-front-end-programming-jobs", "categories/remote-full-stack-programming-jobs",
             "categories/remote-devops-sysadmin-jobs", "categories/remote-design-jobs", "categories/remote-product-jobs"]
    out = {}
    for feed in feeds:
        r = get(f"https://weworkremotely.com/{feed}.rss")
        for it in re.findall(r"<item>(.*?)</item>", r.text if r is not None and r.ok else "", re.S):
            who = rss_tag(it, "region")
            company, _, title = rss_tag(it, "title").partition(": ")
            if not title:
                company, title = "", company
            text = strip_html(rss_tag(it, "description"))
            link = rss_tag(it, "link") or rss_tag(it, "guid")
            region = region_of(who)
            if not region or not classify_it(title) or not english_only(title, text) or link in out:
                continue
            out[link] = remote_item("We Work Remotely", link.rstrip("/").rsplit("/", 1)[-1], title, company, region, link,
                                    who=who, posted=rss_tag(it, "pubDate"), deadline=rss_tag(it, "expires_at"), text=text,
                                    facts=[("Job type", rss_tag(it, "type"))], skills=as_list(rss_tag(it, "skills")))
        time.sleep(0.5)
    return list(out.values())


def src_himalayas():
    """Himalayas' own country filter returns only jobs open to people in Indonesia (worldwide or listing it)."""
    out, page, pages = [], 1, 1
    while page <= min(pages, HIMALAYAS_MAX_PAGES):
        jobs = []
        for attempt in range(2):  # it rate-limits fast requests; wait and retry once
            r = get("https://himalayas.app/jobs/api/search", params={"country": "Indonesia", "page": page})
            d = r.json() if r is not None and r.ok else {}
            jobs = d.get("jobs") or []
            if jobs or (r is not None and r.ok):
                break
            time.sleep(20)
        if not jobs:
            if page < pages:
                log(f"  Himalayas: stopped at page {page} of {pages} (site not answering)")
            break
        pages = -(-(d.get("totalCount") or 0) // 20)
        for j in jobs:
            title = j.get("title")
            text = strip_html(j.get("description"))
            if not classify_it(title) or not english_only(title, text):
                continue
            countries = j.get("locationRestrictions") or []
            tz = [t for t in (j.get("timezoneRestrictions") or []) if isinstance(t, (int, float))]
            who = ("Anywhere" if not countries else ", ".join(countries) if len(countries) <= 12
                   else f"{len(countries)} countries including Indonesia")
            out.append(remote_item(
                "Himalayas", j.get("guid"), title, j.get("companyName"), "Worldwide" if not countries else "Includes Indonesia",
                j.get("guid") or j.get("applicationLink"), who=who, posted=j.get("pubDate"), deadline=j.get("expiryDate"),
                text=text, salary=salary_label(j.get("minSalary"), j.get("maxSalary"), j.get("currency"), j.get("salaryPeriod")),
                pay=(j.get("minSalary"), j.get("maxSalary"), j.get("currency"), j.get("salaryPeriod")),
                facts=[("Employment type", j.get("employmentType")), ("Seniority", ", ".join(as_list(j.get("seniority")))),
                       ("Working hours (UTC offsets)", f"{min(tz):+g} to {max(tz):+g}" if tz else None)]))
        page += 1
        time.sleep(1)
    return out


def src_jobicy():
    out = {}
    for geo in ("anywhere", "apac"):
        r = get("https://jobicy.com/api/v2/remote-jobs", params={"count": 100, "geo": geo})
        for j in (r.json().get("jobs", []) if r is not None and r.ok else []):
            who = j.get("jobGeo") or ""
            title = html.unescape(j.get("jobTitle") or "")
            text = strip_html(j.get("jobDescription"))
            region = region_of(who)
            if not region or not classify_it(title) or not english_only(title, text):
                continue
            out[j["id"]] = remote_item(
                "Jobicy", j["id"], title, j.get("companyName"), region, j.get("url"), who=who, posted=j.get("pubDate"),
                text=text, salary=salary_label(j.get("salaryMin"), j.get("salaryMax"), j.get("salaryCurrency"), j.get("salaryPeriod")),
                pay=(j.get("salaryMin"), j.get("salaryMax"), j.get("salaryCurrency"), j.get("salaryPeriod")),
                facts=[("Job type", ", ".join(as_list(j.get("jobType")))), ("Level", j.get("jobLevel"))])
    return list(out.values())


def src_workingnomads():
    r = get("https://www.workingnomads.com/api/exposed_jobs/")
    out = []
    for j in (r.json() if r is not None and r.ok else []):
        who, title = j.get("location") or "", j.get("title")
        text = strip_html(j.get("description"))
        region = region_of(who)
        if not region or not classify_it(title) or not english_only(title, text):
            continue
        out.append(remote_item("Working Nomads", j.get("url"), title, j.get("company_name"), region, j.get("url"), who=who,
                               posted=j.get("pub_date"), text=text, skills=as_list(j.get("tags"))))
    return out


def src_remotive():
    r = get("https://remotive.com/api/remote-jobs")
    out = []
    for j in (r.json().get("jobs", []) if r is not None and r.ok else []):
        who, title = j.get("candidate_required_location") or "", j.get("title")
        text = strip_html(j.get("description"))
        region = region_of(who)
        if not region or not classify_it(title) or not english_only(title, text):
            continue
        out.append(remote_item("Remotive", j["id"], title, j.get("company_name"), region, j.get("url"), who=who,
                               posted=j.get("publication_date"), text=text, salary=clean(j.get("salary")) or None,
                               facts=[("Job type", human(j.get("job_type")))], skills=as_list(j.get("tags"))))
    return out


def src_remoteok():
    r = get("https://remoteok.com/api")
    out = []
    for j in (r.json() if r is not None and r.ok else []):
        if not isinstance(j, dict) or not j.get("position"):
            continue  # the first element is a legal notice
        who, title = j.get("location") or "", j.get("position")
        text = strip_html(j.get("description"))
        region = region_of(who)
        if not region or not classify_it(title) or not english_only(title, text):
            continue
        out.append(remote_item("Remote OK", j.get("id"), title, j.get("company"), region, j.get("url"), who=who,
                               posted=j.get("date"), text=text, salary=salary_label(j.get("salary_min"), j.get("salary_max")),
                               pay=(j.get("salary_min"), j.get("salary_max"), "USD", "year"), skills=as_list(j.get("tags"))))
    return out


def src_freelancer():
    """Freelancer.com is open to freelancers in any country; only English, non-local projects with IT skills."""
    out = []
    for offset in range(0, FREELANCER_MAX_PROJECTS, 100):
        r = get("https://www.freelancer.com/api/projects/0.1/projects/active/",
                params={"limit": 100, "offset": offset, "compact": "true", "job_details": "true",
                        "full_description": "true", "jobs[]": list(FREELANCER_SKILLS), "languages[]": "en"})
        result = (r.json().get("result") or {}) if r is not None and r.ok else {}
        projects = result.get("projects") or []
        for p in projects:
            title, text = p.get("title"), strip_html(p.get("description"))
            if p.get("local") or (p.get("language") or "en") != "en" or not english_only(title, text):
                continue
            skills = [j.get("name") for j in p.get("jobs") or [] if j.get("name")]
            budget, cur = p.get("budget") or {}, (p.get("currency") or {}).get("code") or ""
            hourly = p.get("type") == "hourly"
            lo, hi = budget.get("minimum"), budget.get("maximum")
            amount = (f"{lo:,.0f} – {hi:,.0f}" if lo and hi else f"{lo or hi:,.0f}+") if (lo or hi) else ""
            salary = f"{cur} {amount} {'per hour' if hourly else 'fixed price'}".strip() if amount else None
            bids = p.get("bid_stats") or {}
            out.append(remote_item(
                "Freelancer.com", p["id"], title, "Freelancer.com client", "Worldwide",
                f"https://www.freelancer.com/projects/{p.get('seo_url')}", who="Freelancers from any country",
                kind="Freelance project", posted=p.get("time_submitted"), text=text, salary=salary,
                pay=(lo, hi, cur, "hour" if hourly else "project"), applicants=bids.get("bid_count"), skills=skills,
                category=classify_it(title) or next((SKILL_CATEGORY[s] for s in skills if s in SKILL_CATEGORY), "Software Engineer (general)"),
                facts=[("Budget", salary), ("Average bid", f"{cur} {bids['bid_avg']:,.0f}" if bids.get("bid_avg") else None)]))
        if not projects or offset + 100 >= (result.get("total_count") or 0):
            break
        time.sleep(1)
    return out


def human(v):
    return clean(str(v or "").replace("_", " ")).capitalize() or None


SOURCES = {
    "We Work Remotely": src_weworkremotely,
    "Himalayas": src_himalayas,
    "Jobicy": src_jobicy,
    "Working Nomads": src_workingnomads,
    "Remotive": src_remotive,
    "Remote OK": src_remoteok,
    "Freelancer.com": src_freelancer,
}


def pay_in_rupiah(j, rates):
    """Adds salary_idr (label), and for remote jobs salary_min / salary_max in Rupiah per month."""
    pay = j.pop("pay", None) or {}
    lo, hi = to_idr(pay.get("min"), pay.get("currency"), rates), to_idr(pay.get("max"), pay.get("currency"), rates)
    if not (lo or hi):
        return
    if j["kind"] == "Freelance project":
        j["salary_idr"] = "≈ " + rupiah_range(lo, hi) + (" per hour" if pay.get("period") == "hour" else " for the project")
        return
    factor = PER_MONTH.get(period_of(pay.get("period")))
    if factor:
        j["salary_min"], j["salary_max"] = int((lo or hi) * factor), int((hi or lo) * factor)
        j["salary_idr"] = "≈ " + rupiah_range(j["salary_min"], j["salary_max"]) + " / month"


def finalize_remote(items):
    today = date.today()
    rates = fx_rates()
    groups = {}
    for j in items:
        j = dict(j)
        # Re-apply the current rules to cached listings too.
        category = classify_it(j["title"])
        if not category and j["kind"] != "Freelance project":
            continue
        j["category"] = category or j["category"]
        if j["kind"] != "Freelance project":
            old_key = j["key"]
            j["key"] = f"remote|{title_core(j['title'])}|{norm(j['company'])}"
            j["aliases"] = [old_key] if old_key != j["key"] else []
        j["exp_years"], j["exp_basis"] = experience(j)
        groups.setdefault(j["key"], []).append(j)
    out = []
    for group in groups.values():
        group.sort(key=lambda g: (g["applicants"] is not None, bool(g["salary"]), len(g["details"].get("description", ""))),
                   reverse=True)
        best = group[0]
        best["also"] = [{"source": g["source"], "url": g["url"]} for g in group[1:] if g["url"] != best["url"]]
        best["aliases"] = sorted({a for g in group for a in g.get("aliases", [])} - {best["key"]})
        best["score"], best["parts"] = score(best["exp_years"], best["applicants"], best["posted"], today)
        pay_in_rupiah(best, rates)
        best.pop("text", None)
        best.pop("exp_label", None)
        out.append(best)
    out.sort(key=lambda j: j["posted"] or "", reverse=True)
    out.sort(key=lambda j: j["score"], reverse=True)
    return out


def collect_remote():
    items = []
    for name, fetch in SOURCES.items():
        got = cache.get(f"remote:{name}", REMOTE_MAX_AGE_HOURS)
        if got is not None:
            log(f"  {name}: {len(got)} reused (read less than {REMOTE_MAX_AGE_HOURS} h ago)")
        else:
            try:
                got = fetch()
            except Exception as e:  # one broken source must not stop the others
                log(f"  {name}: FAILED {e}")
                got = []
            if got:
                cache.put(f"remote:{name}", got)
                log(f"  {name}: {len(got)} fetched")
            else:
                got = cache.get(f"remote:{name}") or []
                log(f"  {name}: nothing fetched, using {len(got)} older cached listings")
        items += got
    return finalize_remote(items)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    log("[Remote & freelance] collecting…")
    update_section("remote", collect_remote)
