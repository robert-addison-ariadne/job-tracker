# Job Tracker

A personal dashboard for a selective graduate job search. It pulls listings daily from job boards, scores each one on **sector fit** and **values alignment**, and lets you track where each application has got to.

**Live dashboard:** `https://<your-username>.github.io/job-tracker/` (once GitHub Pages is on)

## How it works

| Piece | What it does |
|---|---|
| `config.json` | Your search terms, sectors, values and employer ratings. **Edit this first.** |
| `.github/workflows/fetch-jobs.yml` | Runs every day at 06:30 UTC (or on demand), calls `scripts/fetch_jobs.py`, and commits `data/jobs.json`. |
| `data/jobs.json` | Listings from the job boards. Generated, so don't edit it by hand. |
| `data/manual.json` | Roles you find yourself. Add them here. |
| `index.html` | The dashboard (served by GitHub Pages). |

### Fit score

`fit = sector (0–3) + values + employer`

- **Sector:** how strongly the title, category and description match one of your `sectors` keyword lists. A role that matches no sector is capped at 1.
- **Values:** each group in `values` adds its `weight` when the advert has a positive signal (e.g. "B Corp", "Living Wage", "hybrid"). It subtracts its weight when the advert has a negative signal (e.g. "oil and gas", "commission only"). A real advertised salary adds +1.
- **Employer:** your own rating from −5 to +5 in `employers`, for companies you've researched. Use `blocked_employers` to hide a company completely.

Score bands: **5+ strong**, **3–4 good**, **1–2 weak**, **≤0 poor**. Keyword matching only shows what an advert *says*, so research an employer before you apply and record what you find under `employers`.

## Setup

1. **Get free API keys** (one source is enough, both is better):
   - Adzuna: https://developer.adzuna.com/ → you get an *App ID* and an *App Key*
   - Reed: https://www.reed.co.uk/developers/jobseeker → you get an *API key*
2. **Add them as repository secrets:** Settings → Secrets and variables → Actions → New repository secret
   - `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `REED_API_KEY`
3. **Turn on GitHub Pages:** Settings → Pages → Source: *Deploy from a branch* → `main` / `(root)`.
4. **Run the first fetch:** Actions → *Fetch jobs* → *Run workflow*.
5. **Tune `config.json`:** set your location, search `queries`, `exclude_title_words` and sectors. Commit the changes and the dashboard updates on the next page load.

## Tracking applications

Each card has a status (New → Shortlisted → Applied → Interviewing → Offer, or Rejected / Passed) and a notes box. These are saved in your browser's local storage, so they never reach the repo. Use **Export** / **Import** to back them up or move them to another device.

## Local preview

```powershell
powershell -ExecutionPolicy Bypass -File serve.ps1
```

Then open http://localhost:8766/.
