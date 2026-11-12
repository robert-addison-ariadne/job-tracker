"""Collect jobs, score them against config.json, and write data/jobs.json.

Runs every morning in GitHub Actions (.github/workflows/fetch-jobs.yml).

Sources (each is skipped if its access code isn't set):
  - Reed (UK)                     REED_API_KEY
  - Adzuna (UK)                   ADZUNA_APP_ID + ADZUNA_APP_KEY
  - ReliefWeb (worldwide, humanitarian/development)   RELIEFWEB_APPNAME
  - Remotive (remote / international)                 no code needed
  - University job feeds (config.json "universities") no code needed

For every job that could be suggested, the full advert is fetched once and a
four-sentence summary is pulled out of it. Scoring happens here too, so the
dashboard only has to display the result. Standard library only.
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
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config.json")
OUT = os.path.join(ROOT, "data", "jobs.json")
KEEP_STALE_DAYS = 30
MAX_DETAIL_FETCHES = 400
UA = "job-tracker/1.0 (personal job search dashboard)"
TODAY = date.today()


# ---------------------------------------------------------------- helpers

def http_json(url, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": UA, **(headers or {})}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def html_to_text(s):
    """HTML -> plain text, keeping paragraph / bullet breaks as new lines."""
    s = html.unescape(s or "")
    s = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|/div|/tr)\s*/?>", "\n", s)
    s = re.sub(r"(?i)<\s*li[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace(" ", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*", "\n", s)
    return s.strip()


def one_line(s, limit=None):
    s = re.sub(r"\s+", " ", html_to_text(s)).strip()
    return s[:limit] if limit else s


def kw(words):
    """Same rule as the dashboard: whole words, or any ending with a trailing *."""
    if not words:
        return None
    parts = []
    for w in words:
        w = w.lower()
        if w.endswith("*"):
            parts.append(re.escape(w[:-1]))
        else:
            parts.append(re.escape(w) + r"(?![a-z0-9])")
    return re.compile(r"(?<![a-z0-9])(" + "|".join(parts) + ")", re.I)


def hits(rx, text):
    return [m.group(0).lower() for m in rx.finditer(text)] if rx and text else []


def uniq(xs):
    return ", ".join(dict.fromkeys(xs))


def parse_date(s, fmt=None):
    if not s:
        return ""
    try:
        if fmt:
            return datetime.strptime(s, fmt).date().isoformat()
        return s[:10] if re.match(r"\d{4}-\d{2}-\d{2}", s) else ""
    except ValueError:
        return ""


def yearly(n):
    """Hourly / daily rates -> rough yearly equivalent."""
    if not n:
        return 0
    return n * 1950 if n < 200 else n * 230 if n < 2000 else n


# ---------------------------------------------------------------- summary

BOILERPLATE = re.compile(
    r"\b(apply|applying|applications?|click|cv|cvs|reed|please|right to work|visa|sponsorship|gdpr|privacy|"
    r"data protection|cookies|shortlist\w*|closing date|deadline|unfortunately|successful candidates?|"
    r"we reserve|safeguarding|dbs|equal opportunit\w*|disability confident|guaranteed interview|"
    r"recruitment (agency|business|consultancy)|employment agency|job reference|ref(erence)? ?no)\b",
    re.I,
)
LABEL_LINE = re.compile(r"^[\w /&()-]{1,30}:\s")


def summarise(text, n=4):
    """Pick the first n informative sentences from the full advert."""
    prose, bullets = [], []
    for line in (text or "").split("\n"):
        line = line.strip(" -•*·\t")
        if len(line) < 40:
            continue
        if LABEL_LINE.match(line) and len(line) < 90:
            continue  # "Salary: £28,000", "Location: London"
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(“])", line)
        for p in parts:
            p = p.strip()
            if not (40 <= len(p) <= 320) or BOILERPLATE.search(p):
                continue
            if sum(c.isupper() for c in p) > len(p) * 0.5:
                continue  # SHOUTY HEADINGS
            if p[-1] in ".!?":
                prose.append(p)
            else:
                bullets.append(p + ".")
    picked = list(dict.fromkeys(prose))[:n]
    if len(picked) < n:
        picked += [b for b in dict.fromkeys(bullets) if b not in picked][: n - len(picked)]
    return " ".join(picked)


# ---------------------------------------------------------------- sources

def searches(s):
    for loc in s.get("locations", []):
        for q in s.get("queries", []):
            yield q, loc["name"], loc.get("distance_miles", 25)


def fetch_reed(cfg):
    key = os.environ.get("REED_API_KEY")
    if not key:
        print("Reed: no key, skipping")
        return []
    s, out = cfg["search"], []
    auth = {"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()}
    cutoff = (TODAY - timedelta(days=s.get("max_days_old", 14))).isoformat()

    runs = [({"keywords": q, "locationName": w, "distanceFromLocation": m}, f"'{q}' near {w}", False)
            for q, w, m in searches(s)]
    if s.get("graduate_pass"):
        runs += [({"graduate": "true", "locationName": l["name"], "distanceFromLocation": l.get("distance_miles", 25)},
                  f"graduate jobs near {l['name']}", True) for l in s.get("locations", [])]

    for params, label, graduate in runs:
        params = {**params, "resultsToTake": 100}
        try:
            data = http_json("https://www.reed.co.uk/api/1.0/search?" + urllib.parse.urlencode(params), auth)
        except Exception as e:
            print(f"Reed {label}: {e}", file=sys.stderr)
            continue
        n = 0
        for r in data.get("results", []):
            posted = parse_date(r.get("date"), "%d/%m/%Y")
            if posted and posted < cutoff:
                continue
            n += 1
            out.append({
                "id": f"reed-{r['jobId']}", "source": "Reed", "source_id": r["jobId"],
                "title": one_line(r.get("jobTitle"), 200),
                "company": r.get("employerName") or "",
                "location": r.get("locationName") or "",
                "country": "United Kingdom", "abroad": False,
                "salary_min": r.get("minimumSalary"), "salary_max": r.get("maximumSalary"),
                "posted": posted, "closes": parse_date(r.get("expirationDate"), "%d/%m/%Y"),
                "url": r.get("jobUrl"), "description": one_line(r.get("jobDescription"), 600),
                "graduate": graduate, "near": params.get("locationName", ""),
            })
        print(f"Reed {label}: {n}")
        time.sleep(0.4)
    return out


def reed_details(job):
    key = os.environ.get("REED_API_KEY")
    auth = {"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()}
    job_id = job.get("source_id") or job["id"].split("-", 1)[1]
    r = http_json(f"https://www.reed.co.uk/api/1.0/jobs/{job_id}", auth)
    if r.get("partTime") and not r.get("fullTime"):
        job["part_time"] = True
    return html_to_text(r.get("jobDescription"))


def _higherin_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def fetch_higherin(cfg):
    """Higherin's public graduate / internship listing pages (no official feed; pages allowed by its robots.txt)."""
    h, out = cfg.get("higherin") or {}, []
    for cat in h.get("categories", []):
        page, last = 1, 1
        while page <= min(last, h.get("max_pages", 40)):
            try:
                text = _higherin_page(f"https://higherin.com/search-jobs/{cat}" + (f"?page={page}" if page > 1 else ""))
                i = text.index("__RMP_SEARCH_RESULTS_INITIAL_STATE__")
                blob = text[text.index("{", i):]
                state = json.loads(blob[:blob.index("</script>")].strip().rstrip(";"))
            except Exception as e:
                print(f"Higherin {cat} page {page}: {e}", file=sys.stderr)
                break
            last = (state.get("meta") or {}).get("lastPage") or state.get("lastPage") or last
            if page == 1:
                m = re.search(r'"lastPage":(\d+)', blob)
                last = int(m.group(1)) if m else last
            for r in state.get("data", []):
                sal_text = (r.get("salary") or "").strip()
                sal = re.search(r"£\s*([\d,]+)", sal_text)
                yearly_sal = sal and re.search(r"year|annum|p\.?a", sal_text, re.I)
                deadline = re.sub(r"(\d)(st|nd|rd|th)", r"\1", r.get("deadline") or "")
                closes = parse_date(deadline, "%d %B %Y") or parse_date(deadline, "%d %b %Y")
                kind = r.get("jobTypeName") or ""
                out.append({
                    "id": f"higherin-{r.get('jobId') or r.get('id')}", "source": "Higherin",
                    "title": one_line(r.get("jobTitle"), 200), "company": r.get("companyName") or "",
                    "location": r.get("jobLocationNames") or "", "country": "United Kingdom", "abroad": False,
                    "check_south": True,
                    "salary_text": sal_text,
                    "salary_min": int(sal.group(1).replace(",", "")) if yearly_sal else None,
                    "posted": "", "closes": closes, "url": r.get("url"),
                    "description": f"{kind}. {r.get('relevantFor') or ''}".strip(),
                    "graduate": "graduate" in kind.lower(),
                })
            page += 1
            time.sleep(1.5)
        print(f"Higherin {cat}: {page - 1} pages")
    return out


def higherin_details(job):
    """Full advert text from the job page's structured data."""
    text = _higherin_page(job["url"])
    for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', text, re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                if d.get("datePosted"):
                    job["posted"] = parse_date(d["datePosted"])
                return html_to_text(d.get("description"))
    return ""


def _workday_base(site):
    return f"https://{site['host']}/wday/cxs/{site['tenant']}/{site['site']}"


def fetch_workday(cfg):
    """Employers' own Workday careers sites (e.g. Universal Music UK, Warner Music)."""
    out = []
    for site in cfg.get("workday_sites", []):
        offset, total, n = 0, 1, 0
        while offset < min(total, site.get("max_jobs", 200)):
            body = {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": site.get("search", "")}
            try:
                data = http_json(_workday_base(site) + "/jobs", body=body)
            except Exception as e:
                print(f"{site['name']}: {e}", file=sys.stderr)
                break
            total = data.get("total") or 0 if offset == 0 else total
            posts = data.get("jobPostings") or []
            if not posts:
                break
            for p in posts:
                path = p.get("externalPath") or ""
                ago = re.search(r"(\d+)\+? Days? Ago", p.get("postedOn") or "")
                posted = (TODAY - timedelta(days=int(ago.group(1)))).isoformat() if ago else \
                    TODAY.isoformat() if "Today" in (p.get("postedOn") or "") else \
                    (TODAY - timedelta(days=1)).isoformat() if "Yesterday" in (p.get("postedOn") or "") else ""
                n += 1
                out.append({
                    "id": f"workday-{site['tenant']}-{path.rsplit('_', 1)[-1]}", "source": site["name"],
                    "workday": {"base": _workday_base(site), "path": path},
                    "title": one_line(p.get("title"), 200), "company": site["name"],
                    "location": p.get("locationsText") or "", "country": "United Kingdom", "abroad": False,
                    "check_south": True, "posted": posted, "closes": "",
                    "url": f"https://{site['host']}/{site['site']}{path}",
                    "description": "", "part_time": "part" in (p.get("timeType") or "").lower(),
                })
            offset += 20
            time.sleep(1)
        print(f"{site['name']}: {n}")
    return out


def workday_details(job):
    info = http_json(job["workday"]["base"] + job["workday"]["path"]).get("jobPostingInfo", {})
    if info.get("endDate"):
        job["closes"] = parse_date(info["endDate"])
    if info.get("startDate"):
        job["posted"] = parse_date(info["startDate"])
    return html_to_text(info.get("jobDescription"))


def fetch_adzuna(cfg):
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("Adzuna: no keys, skipping")
        return []
    s, out = cfg["search"], []
    for q, where, miles in searches(s):
        params = {"app_id": app_id, "app_key": app_key, "what": q, "where": where,
                  "distance": round(miles * 1.609), "max_days_old": s.get("max_days_old", 14),
                  "results_per_page": 50, "content-type": "application/json"}
        try:
            data = http_json("https://api.adzuna.com/v1/api/jobs/gb/search/1?" + urllib.parse.urlencode(params))
        except Exception as e:
            print(f"Adzuna '{q}' near {where}: {e}", file=sys.stderr)
            continue
        for r in data.get("results", []):
            out.append({
                "id": f"adzuna-{r['id']}", "source": "Adzuna",
                "title": one_line(r.get("title"), 200),
                "company": (r.get("company") or {}).get("display_name", ""),
                "location": (r.get("location") or {}).get("display_name", ""),
                "country": "United Kingdom", "abroad": False,
                "salary_min": r.get("salary_min"), "salary_max": r.get("salary_max"),
                "salary_predicted": r.get("salary_is_predicted") == "1",
                "posted": parse_date(r.get("created")), "closes": "",
                "url": r.get("redirect_url"), "description": one_line(r.get("description"), 600),
            })
        print(f"Adzuna '{q}' near {where}: {len(data.get('results', []))}")
        time.sleep(1)
    return out


def fetch_remotive(cfg):
    a, out = cfg.get("abroad", {}), []
    cutoff = (TODAY - timedelta(days=cfg["search"].get("max_days_old", 14))).isoformat()
    for cat in a.get("remotive_categories", []):
        try:
            data = http_json("https://remotive.com/api/remote-jobs?" + urllib.parse.urlencode({"category": cat}))
        except Exception as e:
            print(f"Remotive {cat}: {e}", file=sys.stderr)
            continue
        n = 0
        for r in data.get("jobs", []):
            posted = parse_date(r.get("publication_date"))
            if posted and posted < cutoff:
                continue
            n += 1
            where = r.get("candidate_required_location") or "Worldwide"
            full = html_to_text(r.get("description"))
            out.append({
                "id": f"remotive-{r['id']}", "source": "Remotive",
                "title": one_line(r.get("title"), 200), "company": r.get("company_name") or "",
                "location": f"Remote ({where})", "country": where,
                "abroad": not re.search(r"\b(uk|united kingdom|england|britain)\b", where, re.I),
                "salary_text": (r.get("salary") or "").strip(),
                "posted": posted, "closes": "", "url": r.get("url"),
                "description": one_line(full, 600), "details_text": full[:6000], "details_fetched": True,
            })
        print(f"Remotive {cat}: {n}")
        time.sleep(2)
    return out


def fetch_reliefweb(cfg):
    app = os.environ.get("RELIEFWEB_APPNAME")
    if not app:
        print("ReliefWeb: no appname, skipping")
        return []
    a = cfg.get("abroad", {})
    since = (TODAY - timedelta(days=cfg["search"].get("max_days_old", 14))).isoformat() + "T00:00:00+00:00"
    conditions = [{"field": "date.created", "value": {"from": since}}]
    if a.get("reliefweb_categories"):
        conditions.append({"field": "career_categories.name", "value": a["reliefweb_categories"], "operator": "OR"})
    body = {
        "limit": 300, "sort": ["date.created:desc"],
        "query": {"value": a.get("reliefweb_query", "communications"), "fields": ["title"]},
        "filter": {"operator": "AND", "conditions": conditions},
        "fields": {"include": ["title", "body", "url", "url_alias", "source.name", "country.name", "city.name",
                               "date.closing", "date.created", "experience.name", "career_categories.name"]},
    }
    try:
        data = http_json("https://api.reliefweb.int/v2/jobs?" + urllib.parse.urlencode({"appname": app}), body=body)
    except Exception as e:
        print(f"ReliefWeb: {e}", file=sys.stderr)
        return []
    out = []
    for item in data.get("data", []):
        f = item.get("fields", {})
        countries = [c.get("name", "") for c in f.get("country", [])]
        cities = [c.get("name", "") for c in f.get("city", [])]
        country = ", ".join(countries) or "Worldwide"
        exp = ", ".join(e.get("name", "") for e in f.get("experience", []))
        full = html_to_text(f.get("body", "").replace("\n", "<br>"))
        out.append({
            "id": f"reliefweb-{item.get('id')}", "source": "ReliefWeb",
            "title": one_line(f.get("title"), 200),
            "company": ", ".join(s.get("name", "") for s in f.get("source", [])),
            "location": ", ".join(cities + countries) or "Worldwide", "country": country,
            "abroad": "United Kingdom" not in countries,
            "posted": parse_date((f.get("date") or {}).get("created")),
            "closes": parse_date((f.get("date") or {}).get("closing")),
            "url": f.get("url_alias") or f.get("url"),
            "description": one_line((f"Experience: {exp} years. " if exp else "") + full, 600),
            "details_text": ((f"Experience required: {exp} years.\n" if exp else "") + full)[:6000],
            "details_fetched": True,
        })
    print(f"ReliefWeb: {len(out)}")
    return out


def fetch_universities(cfg):
    """Universities' own vacancy feeds (research, policy, comms and sustainability roles)."""
    out = []
    for uni in cfg.get("universities", []):
        try:
            req = urllib.request.Request(uni["feed"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                root = ET.fromstring(r.read())
        except Exception as e:
            print(f"{uni['name']}: {e}", file=sys.stderr)
            continue
        n = 0
        for item in root.iter("item"):
            title = one_line(item.findtext("title"), 200)
            title = re.sub(r"\s*\([A-Z0-9-]{4,}\)\s*$", "", title)  # drop the "(3549226BA)" reference
            link = (item.findtext("link") or "").strip()
            full = html_to_text(item.findtext("description"))
            category = one_line(item.findtext("category"))
            sal = re.search(r"Salary:\s*£?\s*([\d,]+)(?:\.\d+)?(?:\s*(?:to|-|–)\s*£?\s*([\d,]+))?", full, re.I)
            closes = re.search(r"Closing Date:\s*(\d{1,2} \w{3,9} \d{4})", full, re.I)
            try:
                posted = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
            except (TypeError, ValueError):
                posted = ""
            close_iso = ""
            if closes:
                for fmt in ("%d %b %Y", "%d %B %Y"):
                    close_iso = parse_date(closes.group(1), fmt)
                    if close_iso:
                        break
            n += 1
            out.append({
                "id": f"uni-{re.sub(r'[^a-z0-9]+', '-', uni['name'].lower())}-{re.sub(r'[^A-Za-z0-9]+', '', link.split('=')[-1])[:40]}",
                "source": uni["name"], "title": title, "company": uni["name"],
                "location": uni.get("location", ""), "country": "United Kingdom", "abroad": False,
                "salary_min": int(sal.group(1).replace(",", "")) if sal else None,
                "salary_max": int(sal.group(2).replace(",", "")) if sal and sal.group(2) else None,
                "posted": posted, "closes": close_iso, "url": link,
                "description": one_line(full, 600),
                "details_text": ((f"Job category: {category}.\n" if category else "") + full)[:6000],
                "details_fetched": True,
            })
        print(f"{uni['name']}: {n}")
        time.sleep(0.5)
    return out


# ---------------------------------------------------------------- scoring

class Rules:
    def __init__(self, cfg):
        self.areas = [{
            "name": a["name"], "re": kw(a.get("keywords")), "ex": kw(a.get("exclude")),
            # common words (e.g. "community") only count in the job title, not the advert text
            "body_re": None if a.get("title_only") else
                       kw([w for w in a.get("keywords", []) if w not in set(a.get("title_only_keywords", []))]),
            "title_re": kw(a.get("needs_title_words")), "needs_area": a.get("needs_area"),
            "needs_scheme": a.get("needs_graduate_scheme", False),
        } for a in cfg.get("areas", [])]
        self.areas.sort(key=lambda a: bool(a["needs_area"]))  # areas that depend on others go last
        r = cfg.get("roles", {})
        self.skills, self.hide_title = kw(r.get("cv_skill_title_words")), kw(r.get("hide_title_words"))
        self.down, self.down_pts = kw(r.get("downweight_title_words")), r.get("downweight_penalty", 3)
        self.down_exempt = set(r.get("downweight_exempt_areas", []))
        # words that normally hide a job, but are fine inside the music industry (e.g. "commercial")
        self.music_ok = {w.lower() for w in r.get("allowed_in_music", [])}
        self.priority, self.priority_pts = kw(r.get("priority_title_words")), r.get("priority_bonus", 2)
        self.priority_body = kw(r.get("priority_title_words"))
        L = cfg.get("level", {})
        self.entry, self.senior = kw(L.get("entry_signals")), kw(L.get("senior_signals"))
        self.scheme = kw(L.get("graduate_scheme_words"))
        self.senior_title = kw(L.get("senior_title_words"))
        self.too_senior, self.hide_salary = L.get("too_senior_salary", 0), L.get("hide_above_salary", 0)
        ex = cfg.get("exclude_locations", {})
        self.bad_places = kw(ex.get("places"))
        pc = ex.get("postcode_areas") or []
        self.bad_postcodes = re.compile(r"(^|[\s,(])(" + "|".join(pc) + r")\d", re.I) if pc else None
        self.south = kw(cfg.get("south_of_england_places"))  # for sources that list jobs UK-wide
        jt = cfg.get("job_type", {})
        self.part_time, self.pt_penalty = kw(jt.get("part_time_signals")), jt.get("part_time_penalty", 2)
        self.values = [{"name": v["name"], "w": v.get("weight", 1), "pos": kw(v.get("positive")),
                        "neg": kw(v.get("negative"))} for v in cfg.get("values", [])]
        self.employers = {k.lower(): v for k, v in cfg.get("employers", {}).items() if not k.startswith("_")}
        self.blocked = {b.lower() for b in cfg.get("blocked_employers", [])}
        self.min_fit = cfg.get("min_fit", 3)
        self.abroad_min = cfg.get("abroad", {}).get("min_fit", 5)


def score(job, R):
    title = (job.get("title") or "").lower()
    body = (job.get("details_text") or job.get("description") or "").lower()
    company = (job.get("company") or "").lower()
    text = f"{title} {body}"
    pos, neg, areas, hidden = [], [], [], None
    # A structured graduate scheme / programme (Higherin labels these; otherwise judge by the title)
    is_scheme = bool(hits(R.scheme, title)) or (job.get("source") == "Higherin" and job.get("graduate"))

    # Which of your areas is it in?
    title_areas = []
    best, body_needed = 0, 2 if len(body) < 1500 else 3
    for a in R.areas:
        if a["ex"] and a["ex"].search(text):
            continue
        t = len(hits(a["re"], title)) + len(hits(a["re"], company))
        bh = hits(a["body_re"], body)
        b = len(bh)
        # In the title, or mentioned repeatedly in the advert using at least two different keywords
        # (long adverts mention things like "sustainable" in passing, so they need more evidence)
        distinct_needed = 2 if len(body) < 1500 else 3
        if not (t or (b >= body_needed + (1 if len(body) >= 1500 else 0) and len(set(bh)) >= distinct_needed)):
            continue
        if a["title_re"] and not a["title_re"].search(title):
            continue
        if a["needs_area"] and a["needs_area"] not in areas:
            continue
        if a["needs_scheme"] and not is_scheme:
            continue
        areas.append(a["name"])
        if t:
            title_areas.append(a["name"])
        best = max(best, t * 2 + b)
    # Graduate schemes must fit your areas by their title or organisation, not a passing mention in the advert
    if is_scheme and not title_areas:
        areas = []
    area_pts = 0 if not areas else 3 if best >= 4 else 2 if best >= 2 else 1

    # Is it your kind of role?
    role_pts = 0
    sk = hits(R.skills, title)
    if sk:
        role_pts = 2
        pos.append(f"Uses your skills: {uniq(sk)}")
    # Your priority topics (politics, social justice, journalism) get a boost...
    pr = hits(R.priority, title)
    if pr:
        role_pts += R.priority_pts
        pos.append(f"Priority topic: {uniq(pr)}")
    elif len(set(hits(R.priority_body, body))) >= 3:
        role_pts += 1
        pos.append("Priority topics in the advert")
    # ...and generic marketing / social media roles are turned down (except in music)
    dn = hits(R.down, title)
    if dn and not (set(areas) & R.down_exempt):
        role_pts -= R.down_pts
        neg.append(f"Marketing / social media role: {uniq(dn)}")

    # Aimed at graduates / students? Strongest when the title or listing says so.
    level = 0
    e_title = hits(R.entry, title)
    e = hits(R.entry, text)
    if is_scheme:
        level += 4
        pos.append("Graduate scheme")
    elif e_title or job.get("graduate"):
        level += 3
        pos.append("Aimed at graduates" + (f": {uniq(e_title)}" if e_title else ""))
    elif e:
        level += 1
        pos.append(f"Entry level hints: {uniq(e)}")
    else:
        level -= 1
        neg.append("Not obviously aimed at graduates")
    s = hits(R.senior, body)
    if s:
        level -= 2
        neg.append(f"Asks for a lot of experience: {uniq(s)}")
    st = hits(R.senior_title, title)
    if st and not hits(R.entry, title):
        level -= 2
        neg.append(f"Senior-sounding title: {uniq(st)}")
    pay = yearly(job.get("salary_min")) if not job.get("salary_predicted") else 0
    if R.too_senior and pay >= R.too_senior:
        level -= 2
        neg.append("Salary suggests a senior role")
    level = max(level, -4)

    if job.get("part_time") or hits(R.part_time, text):
        level -= R.pt_penalty
        neg.append("Part-time")

    values = 0
    for v in R.values:
        p, n = hits(v["pos"], text), hits(v["neg"], text)
        if p:
            values += v["w"]
            pos.append(f"{v['name']}: {uniq(p)}")
        if n:
            values -= v["w"]
            neg.append(f"{v['name']}: {uniq(n)}")
    if job.get("salary_min") and not job.get("salary_predicted"):
        values += 1
        pos.append("Salary shown")

    emp = R.employers.get(company, {})
    employer = int(emp.get("score", 0) or 0)

    total = area_pts + role_pts + level + values + employer

    # Reasons to hide it completely
    loc = job.get("location") or ""
    if company in R.blocked:
        hidden = "blocked employer"
    elif set(hits(R.hide_title, title)) - (R.music_ok if set(areas) & R.down_exempt else set()):
        hidden = "not your kind of role"
    elif not areas:
        hidden = "outside your areas"
    elif not job.get("abroad") and ((R.bad_places and R.bad_places.search(loc)) or
                                    (R.bad_postcodes and R.bad_postcodes.search(loc))):
        hidden = "outside the south of England"
    elif job.get("check_south") and R.south and not R.south.search(loc):
        hidden = "outside the south of England"
    elif R.hide_salary and pay >= R.hide_salary:
        hidden = "too senior"
    elif job.get("closes") and job["closes"] < TODAY.isoformat():
        hidden = "closed"

    need = R.abroad_min if job.get("abroad") else R.min_fit
    return {"total": total, "areas": areas, "pos": pos, "neg": neg, "hidden": hidden,
            "show": hidden is None and total >= need}


# ---------------------------------------------------------------- main

def dedupe_key(j):
    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", re.sub(r"\(.*?\)", "", (s or "").lower())).split()
    return " ".join(norm(j.get("company"))) + "|" + " ".join(norm(j.get("title"))[:5])


def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    try:
        with open(OUT, encoding="utf-8") as f:
            existing = {j["id"]: j for j in json.load(f).get("jobs", [])}
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {}

    if not any(os.environ.get(k) for k in ("REED_API_KEY", "ADZUNA_APP_ID", "RELIEFWEB_APPNAME")):
        print("No access codes set; leaving data/jobs.json unchanged. See README > Setup.")
        return

    words = cfg["search"].get("exclude_title_words", [])
    title_block = kw(words)
    fresh, keys = {}, {}
    for j in fetch_reed(cfg) + fetch_adzuna(cfg) + fetch_universities(cfg) + fetch_higherin(cfg) \
            + fetch_workday(cfg) + fetch_reliefweb(cfg) + fetch_remotive(cfg):
        if title_block and title_block.search(j["title"]):
            continue
        if j["id"] in fresh:
            fresh[j["id"]]["graduate"] = fresh[j["id"]].get("graduate") or j.get("graduate")
            continue
        k = dedupe_key(j)
        if k in keys:
            continue  # same job posted again / on another board
        keys[k] = j["id"]
        fresh[j["id"]] = j

    today = TODAY.isoformat()
    merged = {}
    for jid, j in fresh.items():
        prev = existing.get(jid, {})
        for k in ("summary", "details_text", "details_fetched", "part_time"):
            if k in prev and k not in j:
                j[k] = prev[k]
        for k in ("closes", "posted"):  # dates learnt from the full advert on an earlier day
            if not j.get(k) and prev.get(k):
                j[k] = prev[k]
        j["graduate"] = j.get("graduate") or prev.get("graduate", False)
        j["first_seen"] = prev.get("first_seen", today)
        j["last_seen"] = today
        merged[jid] = j
    stale_cutoff = (TODAY - timedelta(days=KEEP_STALE_DAYS)).isoformat()
    for jid, j in existing.items():
        if jid in merged or dedupe_key(j) in keys:
            continue
        if j.get("last_seen", today) >= stale_cutoff and not (j.get("closes") and j["closes"] < today):
            merged[jid] = j

    # Score everything; fetch full adverts for jobs that could be suggested, then re-score.
    R = Rules(cfg)
    fetched = 0
    for j in merged.values():
        j["fit"] = score(j, R)
        # Higherin listings have no description, so also open southern, non-technical ones to judge the area
        maybe = j["fit"]["hidden"] is None or (
            j["source"] == "Higherin" and j["fit"]["hidden"] == "outside your areas"
            and R.south and R.south.search(j.get("location") or "")
            and not hits(R.hide_title, (j.get("title") or "").lower()))
        if maybe and not j.get("details_fetched") and (j["source"] in ("Reed", "Higherin") or j.get("workday")) \
                and fetched < MAX_DETAIL_FETCHES:
            try:
                fetch_details = reed_details if j["source"] == "Reed" else workday_details if j.get("workday") \
                    else higherin_details
                j["details_text"] = fetch_details(j)[:6000]
                j["details_fetched"] = True
                fetched += 1
                time.sleep(0.3 if j["source"] == "Reed" else 1.5)
            except Exception as e:
                print(f"Reed details {j['id']}: {e}", file=sys.stderr)
                j["details_fetched"] = True  # don't retry a broken advert every morning
            j["fit"] = score(j, R)
        if j["fit"]["show"] and not j.get("summary"):
            j["summary"] = summarise(j.get("details_text") or j.get("description"))
        if not j["fit"]["show"]:
            j.pop("details_text", None) if j["fit"]["hidden"] in ("outside your areas", "not your kind of role") else None

    jobs = sorted(merged.values(), key=lambda j: (j["fit"]["show"], j["fit"]["total"]), reverse=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "jobs": jobs},
                  f, indent=0, ensure_ascii=False)
    shown = [j for j in jobs if j["fit"]["show"]]
    print(f"Wrote {len(jobs)} jobs; {len(shown)} suggested "
          f"({sum(1 for j in shown if j.get('abroad'))} abroad); fetched {fetched} full adverts.")


if __name__ == "__main__":
    main()
