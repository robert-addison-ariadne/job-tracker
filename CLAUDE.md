# Job tracker: notes for Claude

- The owner is not a coder: explain everything in plain language.
- For any change to this project, delegate to the **`job-tracker`** subagent (Sonnet), which has the full project context: sources, scoring rules, the twice-weekly web search routine and its setup quirks.
- Settings live in `config.json`; the morning search and all scoring are in `scripts/fetch_jobs.py`; the dashboard is `index.html`.
- There's no Python on the owner's laptop: test by running the **Fetch jobs** workflow on GitHub.
- Always `git pull --rebase` before editing, because the daily search commits to `main` every morning.
