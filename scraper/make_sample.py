"""
Builds the small example data in site/sample/ from the real data in site/data/, so the website can be
tried without running the scraper. Personal data is removed: recruiter names / emails are dropped, and
email addresses, phone numbers and WhatsApp links in any text are replaced.

    python scraper/make_sample.py
"""
import json
import re
import sys

from scrape import DATA_DIR, log, read_js

SAMPLE_DIR = DATA_DIR.parent / "sample"
JOBS_PER_CATEGORY = 2
REMOTE_JOBS, FREELANCE_PROJECTS = 8, 4
PROGRAM_ITEMS = 5

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Emails written to dodge scrapers: "nameATgmailDOTcom", "name [at] gmail [dot] com"
HIDDEN_EMAIL = re.compile(r"[\w.+-]+\s*(?:AT|(?i:\[at\]|\(at\)|\{at\}))\s*[\w-]+"
                          r"(?:\s*(?:DOT|(?i:\[dot\]|\(dot\)|\{dot\}))\s*[A-Za-z]{2,})+")
PHONE = re.compile(r"(?:\+62|\b62|\b0)8\d[\d\s.-]{6,13}\d|\+\d[\d\s.-]{8,}\d")
WHATSAPP = re.compile(r"(?:https?://)?(?:wa\.me|api\.whatsapp\.com)/\S+", re.I)


def scrub(value):
    """Remove contact details from every string inside value."""
    if isinstance(value, str):
        value = WHATSAPP.sub("[link removed]", value)
        value = EMAIL.sub("[email removed]", value)
        value = HIDDEN_EMAIL.sub("[email removed]", value)
        return PHONE.sub("[phone removed]", value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k != "recruiter"}
    return value


def write(name, var, value):
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLE_DIR / f"{name}.js").write_text(
        f"window.{var} = " + json.dumps(scrub(value), ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")


def pick_jobs(jobs):
    picked, per_category = [], {}
    for j in sorted(jobs, key=lambda j: -j["score"]):
        if per_category.get(j["category"], 0) < JOBS_PER_CATEGORY:
            per_category[j["category"]] = per_category.get(j["category"], 0) + 1
            picked.append(j)
    return picked


def pick_remote(jobs):
    remote = [j for j in jobs if j["kind"] != "Freelance project"]
    freelance = [j for j in jobs if j["kind"] == "Freelance project"]
    seen, picked = set(), []
    for j in sorted(remote, key=lambda j: -j["score"]):  # one per role first, for variety
        if j["category"] not in seen and len(picked) < REMOTE_JOBS:
            seen.add(j["category"])
            picked.append(j)
    return picked + sorted(freelance, key=lambda j: -j["score"])[:FREELANCE_PROJECTS]


def main():
    jobs, remote = read_js(DATA_DIR / "jobs.js"), read_js(DATA_DIR / "remote.js")
    programs = read_js(DATA_DIR / "programs.js")
    if not jobs:
        sys.exit("No data in site/data/ yet. Run python scraper/scrape.py first.")
    for name, var, data, pick in [("jobs", "JOBS_DATA", jobs, pick_jobs), ("remote", "REMOTE_DATA", remote, pick_remote)]:
        if not data:
            continue
        chosen = pick(data["jobs"])
        details = read_js(DATA_DIR / f"{name}-details.js") or {}
        write(name, var, {**data, "jobs": chosen})
        write(f"{name}-details", var.replace("_DATA", "_DETAILS"), {j["key"]: details.get(j["key"], {}) for j in chosen})
        log(f"  {name}: {len(chosen)} of {len(data['jobs'])}")
    if programs:
        for p in programs["programs"]:
            if p.get("live") and p["live"].get("items"):
                p["live"]["items"] = p["live"]["items"][:PROGRAM_ITEMS]
        write("programs", "PROGRAMS_DATA", programs)
        log(f"  programs: {len(programs['programs'])}")
    log(f"Sample written to {SAMPLE_DIR}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
