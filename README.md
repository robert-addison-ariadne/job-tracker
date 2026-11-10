# Job Tracker

A personal dashboard for a selective graduate job search. Every morning it collects jobs, keeps the ones that fit, and shows them for a twice-weekly review.

**Dashboard:** https://robert-addison-ariadne.github.io/job-tracker/

## How it works

1. **Every morning (about 6:30am UK time)** a scheduled GitHub task runs `scripts/fetch_jobs.py`:
   - searches **Reed** around seven towns across the south of England, plus Reed's graduate jobs
   - reads the vacancy feeds of ten universities in the south (listed in `config.json`)
   - reads **Higherin**'s graduate jobs and internships pages (keeping only jobs in the south)
   - searches **Remotive** for remote and international roles (and **ReliefWeb** once it's set up)
   - scores every job against `config.json` and hides anything outside your areas, technical, too senior (£50k+) or in Wales
   - fetches the full advert for jobs that could be suggested and pulls out a four-sentence summary
   - saves everything to `data/jobs.json`
2. **The dashboard** (`index.html`) shows:
   - **New**: suggested jobs you haven't ticked yet. Tick **✓ Potential** or **✕ Not for me**.
   - **Seen**: a deadline timeline for your Potential jobs, then the Potential and Not-for-me lists.
   - Jobs abroad only appear when they're a strong match, in a purple box.

Your ticks are saved in your browser. Use **Export my ticks** at the bottom of the page to back them up.

## Areas it looks for

Music (marketing & comms side) · Sustainability & social impact · Journalism & communications · Public sector (roles using policy, research, analysis, strategy, engagement or comms skills) · Not-for-profits working on sustainability. Graduate level; full time preferred.

## Access codes (GitHub → Settings → Secrets and variables → Actions)

| Name | Where from | Status |
|---|---|---|
| `REED_API_KEY` | reed.co.uk/developers | set up |
| `RELIEFWEB_APPNAME` | apidoc.reliefweb.int (request an appname) | optional |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | developer.adzuna.com (paid) | optional |
