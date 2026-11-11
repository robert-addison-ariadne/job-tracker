# Twice-weekly web search for jobs

You are topping up a personal graduate job-search dashboard with good jobs that the automatic feeds (Reed, Remotive) miss. You run on Monday and Thursday mornings. The person's profile is given to you in the prompt that started this session; the rules below say how to search and what to save.

## 1. Read first
- `config.json`: the areas of interest (`areas`), roles to avoid (`roles.hide_title_words`), level rules (`level`), the search towns (`search.locations`), and places to exclude (`exclude_locations`).
- `data/jobs.json`: jobs the feeds already found. **Don't add any job already in here** (same advert URL, or same employer and a very similar title).
- `data/web_finds.json`: jobs earlier web searches found. Don't add duplicates of these either.

## 2. What to look for (priorities)
1. **Graduate schemes and early-careers programmes from well-known organisations**: these are the person's top priority, and the automatic feeds miss most of them. **Check these every run**, and save any that are open in the south of England (or nationwide):
   - Public sector: Civil Service Fast Stream, National Graduate Development Programme (NGDP, local government), Houses of Parliament graduate / apprentice schemes, GLA graduate programme, regulators' graduate schemes (Ofcom, Ofgem, Ofwat, CMA, FCA, Electoral Commission, Bank of England *policy* tracks), ONS.
   - Journalism & media: BBC journalism trainee schemes, Guardian / Scott Trust bursary, Reach plc trainee scheme, PA Media, Reuters, Bloomberg, Financial Times, The Economist, Tortoise, Channel 4 / ITN graduate schemes, Creative Access listings.
   - Politics, think tanks & public affairs: Institute for Government, IPPR, Resolution Foundation, Centre for Cities, Demos, New Economics Foundation, Joseph Rowntree Foundation, Social Market Foundation, Bright Blue, Fabian Society internships; public affairs agencies' graduate schemes (e.g. Hanover, Portland, Cicero, WPI Strategy, Instinctif).
   - Social justice, charities & development: Charityworks graduate scheme, Oxfam, Amnesty UK, Save the Children, British Red Cross, Shelter, Crisis, JUSTICE, Liberty, Refugee Council, Citizens Advice, Year Here, Social Finance, NPC.
   - Music: Sony Music, Universal Music, Warner Music UK graduate / early-careers schemes (marketing, communications or editorial tracks only), PRS Foundation, UK Music.
2. **Roles in politics, social justice and journalism**: policy and research assistants, parliamentary/MP office roles, caseworkers, campaigns and advocacy officers, editorial assistants, trainee reporters, researchers at think tanks or charities.
3. Other roles in the five areas from `config.json`.

**Avoid** generic marketing, social-media, content-creator or brand executive roles (only include marketing/comms roles in the music industry), and listings that are not clearly aimed at graduates or early-career candidates.

Run roughly 25 varied searches, spread across these priorities and across the south of England (London, Brighton, Kent, Hampshire, Oxford/Reading, Bristol/Bath, Devon), for example:
- `NGDP 2027 applications`, `BBC journalism trainee scheme 2027`, `think tank research assistant London`, `parliamentary assistant MP job`, `graduate policy officer charity London`, `campaigns assistant human rights charity`, `editorial assistant magazine Bristol`, `Charityworks 2027`, `Sony Music graduate scheme marketing`.

Good places to find adverts: employers' own careers pages, Civil Service Jobs, local council job pages, CharityJob, Guardian Jobs, w4mpjobs, journalism.co.uk, jobs.ac.uk, Escape the City, Idealist, ReliefWeb, Devex, UN Careers, Music Week / Creative Access / UK Music job boards. **Don't use LinkedIn or Indeed** (their rules don't allow it).

## 3. Check every candidate
Open each advert page and confirm it is real and still open. Only keep a job when **all** of these are true:
- It is still accepting applications (closing date in the future, or no date given and posted within the last 30 days).
- It is in the south of England, or remote from the UK. Jobs abroad are allowed only when they are an outstanding fit.
- It sits in at least one area from `config.json` and isn't technical, scientific or engineering work (see `roles.hide_title_words`).
- It is graduate / early-career level: no requirement for several years' experience, not a manager role, salary under £50k.
- It plays to the person's strengths described in the prompt.

Quality over quantity: **add at most 15 jobs per run**, and it's fine to add none.

## 4. Save
Add each job to the `jobs` list in `data/web_finds.json` in exactly this shape:

```json
{
  "id": "web-<short lowercase slug of employer and title>",
  "source": "Web search",
  "title": "Communications Assistant",
  "company": "Example Charity",
  "location": "London (hybrid)",
  "country": "United Kingdom",
  "abroad": false,
  "salary_text": "£27,000 – £29,000",
  "posted": "2026-11-09",
  "closes": "2026-11-30",
  "url": "https://the-real-advert-page",
  "summary": "Exactly four plain-English sentences: what the organisation does, what the role involves day to day, who they're looking for, and one practical detail (contract, hours, hybrid, etc.).",
  "first_seen": "<today's date>",
  "fit": { "total": 7, "areas": ["Journalism & communications"], "pos": [], "neg": [], "hidden": null, "show": true }
}
```

- Dates are `YYYY-MM-DD`. Use `""` for `closes` or `salary_text` when the advert doesn't give them, rather than guessing.
- `fit.total` is your 1–10 judgement of how well the job matches; only save jobs you'd score **6 or more**. Use the area names exactly as written in `config.json`.
- For jobs abroad set `"abroad": true` and `country` to the country.
- **Remove** any job in `data/web_finds.json` whose closing date has passed.
- Set the top-level `"updated"` to the current UTC time (ISO format).

## 5. Publish
Only change `data/web_finds.json`. Commit with the message `Web search finds <YYYY-MM-DD>` and push to `main`. If the push is rejected because the daily feed committed first, run `git pull --rebase` and push again.

Finish with a short list of what you added (title, employer, closing date) and anything you removed.
