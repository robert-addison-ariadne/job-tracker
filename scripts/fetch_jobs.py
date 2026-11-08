"""Fetch job listings from Adzuna and/or Reed into data/jobs.json.

Runs daily in GitHub Actions (see .github/workflows/fetch-jobs.yml), or locally:
    ADZUNA_APP_ID=... ADZUNA_APP_KEY=... REED_API_KEY=... python scripts/fetch_jobs.py

Each source is skipped if its keys aren't set. Uses only the standard library.
Listings are merged with the existing file: new ones get first_seen = today,
ones that disappear from results are kept (marked stale) for 30 days, then dropped.
"""
import base64
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config.json")
OUT = os.path.join(ROOT, "data", "jobs.json")
KEEP_STALE_DAYS = 30
UA = "job-tracker/1.0 (personal dashboard)"


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def clean(text, limit=600):
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def excluded(title, words):
    t = title.lower()
    return any(re.search(r"\b" + re.escape(w.lower()) + r"\b", t) for w in words)


def fetch_adzuna(cfg):
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("Adzuna: no keys, skipping")
        return []
    s, out = cfg["search"], []
    km = round(s.get("distance_miles", 25) * 1.609)
    for q in s["queries"]:
        params = {
            "app_id": app_id, "app_key": app_key, "what": q,
            "where": s.get("location", ""), "distance": km,
            "max_days_old": s.get("max_days_old", 14),
            "results_per_page": 50, "content-type": "application/json",
        }
        url = f"https://api.adzuna.com/v1/api/jobs/{s.get('country', 'gb')}/search/1?" + urllib.parse.urlencode(params)
        try:
            data = get_json(url)
        except Exception as e:  # keep going if one query fails
            print(f"Adzuna '{q}': {e}", file=sys.stderr)
            continue
        for r in data.get("results", []):
            out.append({
                "id": f"adzuna-{r['id']}",
                "source": "Adzuna",
                "title": clean(r.get("title"), 200),
                "company": (r.get("company") or {}).get("display_name", ""),
                "location": (r.get("location") or {}).get("display_name", ""),
                "salary_min": r.get("salary_min"),
                "salary_max": r.get("salary_max"),
                "salary_predicted": r.get("salary_is_predicted") == "1",
                "category": (r.get("category") or {}).get("label", ""),
                "contract": r.get("contract_time") or "",
                "posted": (r.get("created") or "")[:10],
                "url": r.get("redirect_url"),
                "description": clean(r.get("description")),
                "query": q,
            })
        print(f"Adzuna '{q}': {len(data.get('results', []))}")
        time.sleep(1)
    return out


def fetch_reed(cfg):
    key = os.environ.get("REED_API_KEY")
    if not key:
        print("Reed: no key, skipping")
        return []
    s, out = cfg["search"], []
    auth = "Basic " + base64.b64encode(f"{key}:".encode()).decode()
    for q in s["queries"]:
        params = {
            "keywords": q, "locationName": s.get("location", ""),
            "distanceFromLocation": s.get("distance_miles", 25), "resultsToTake": 100,
        }
        try:
            data = get_json("https://www.reed.co.uk/api/1.0/search?" + urllib.parse.urlencode(params), {"Authorization": auth})
        except Exception as e:
            print(f"Reed '{q}': {e}", file=sys.stderr)
            continue
        cutoff = date.today() - timedelta(days=s.get("max_days_old", 14))
        n = 0
        for r in data.get("results", []):
            try:
                posted = datetime.strptime(r.get("date", ""), "%d/%m/%Y").date()
            except ValueError:
                posted = None
            if posted and posted < cutoff:
                continue
            n += 1
            out.append({
                "id": f"reed-{r['jobId']}",
                "source": "Reed",
                "title": clean(r.get("jobTitle"), 200),
                "company": r.get("employerName") or "",
                "location": r.get("locationName") or "",
                "salary_min": r.get("minimumSalary"),
                "salary_max": r.get("maximumSalary"),
                "salary_predicted": False,
                "category": "",
                "contract": "",
                "posted": posted.isoformat() if posted else "",
                "closes": _reed_date(r.get("expirationDate")),
                "url": r.get("jobUrl"),
                "description": clean(r.get("jobDescription")),
                "query": q,
            })
        print(f"Reed '{q}': {n}")
        time.sleep(1)
    return out


def _reed_date(s):
    try:
        return datetime.strptime(s or "", "%d/%m/%Y").date().isoformat()
    except ValueError:
        return ""


def dedupe_key(j):
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    return norm(j["title"]) + "|" + norm(j["company"])


def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    try:
        with open(OUT, encoding="utf-8") as f:
            existing = {j["id"]: j for j in json.load(f).get("jobs", [])}
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {}

    today = date.today().isoformat()
    blocked = {b.lower() for b in cfg.get("blocked_employers", [])}
    words = cfg["search"].get("exclude_title_words", [])

    fresh, seen_keys = {}, set()
    for j in fetch_adzuna(cfg) + fetch_reed(cfg):
        if excluded(j["title"], words) or j["company"].lower() in blocked:
            continue
        k = dedupe_key(j)
        if k in seen_keys:
            continue  # same role listed on both boards / under several queries
        seen_keys.add(k)
        fresh[j["id"]] = j

    if not fresh and existing and not (os.environ.get("ADZUNA_APP_ID") or os.environ.get("REED_API_KEY")):
        print("No API keys set; leaving data/jobs.json unchanged.")
        return

    merged = {}
    for jid, j in fresh.items():
        prev = existing.get(jid, {})
        j["first_seen"] = prev.get("first_seen", today)
        j["last_seen"] = today
        merged[jid] = j
    stale_cutoff = (date.today() - timedelta(days=KEEP_STALE_DAYS)).isoformat()
    for jid, j in existing.items():
        if jid not in merged and dedupe_key(j) not in seen_keys and j.get("last_seen", today) >= stale_cutoff:
            merged[jid] = j

    jobs = sorted(merged.values(), key=lambda j: (j.get("first_seen", ""), j.get("posted", "")), reverse=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "jobs": jobs}, f, indent=1, ensure_ascii=False)
    new = sum(1 for j in jobs if j.get("first_seen") == today and j["id"] not in existing)
    print(f"Wrote {len(jobs)} listings ({new} new).")


if __name__ == "__main__":
    main()
