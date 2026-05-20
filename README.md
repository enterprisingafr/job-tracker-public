# Job Tracker — AI-Powered Job Feed to Google Sheets

Automatically fetches job postings from dozens of employers, scores them with Claude AI for relevance to *your* profile, and populates a Google Sheet — twice a week, fully automated via GitHub Actions.

**Stop manually scanning LinkedIn and 20 company career pages. Let the tracker do it.**

> **Want a step-by-step setup guide?** Get the packaged version with full instructions at [pegzster.gumroad.com/l/job-tracker](https://pegzster.gumroad.com/l/job-tracker) ($19).

---

## What it does

1. **Fetches** job postings directly from employer ATS systems (Greenhouse, Lever, Ashby, Workday, SmartRecruiters) — no scraping paid job boards
2. **Pre-filters** by location, seniority, and job type before spending any API credits
3. **Scores** each posting 1–10 using Claude AI, calibrated to your background and target roles
4. **Writes** only the relevant ones (score ≥ 7 by default) to a Google Sheet, with the AI's reasoning
5. **Runs automatically** every Monday and Wednesday at 8 AM via GitHub Actions — free

### Example output (Google Sheet)

| Date | Company | Title | Location | Remote? | Score | AI Reason | Link | Status |
|------|---------|-------|----------|---------|-------|-----------|------|--------|
| 2026-05-19 | Ford Foundation | Program Officer, Democracy | New York, NY | No | 9 | Matches policy + philanthropy background; NYC-based | [Apply](#) | To Review |
| 2026-05-19 | Coursera | Partnerships Manager, Enterprise | Remote | Yes | 8 | Strong edtech + BD fit; remote-friendly | [Apply](#) | To Review |
| 2026-05-19 | UNDP | Programme Specialist, Strategic Planning | New York, NY | Hybrid | 8 | Multilateral org, strategic planning, multilingual valued | [Apply](#) | To Review |

---

## Setup (one-time, ~30 minutes)

### What you need

- A GitHub account (free)
- An Anthropic API key — [get one here](https://console.anthropic.com)
- A Google account

---

### Step 1 — Fork this repo

Click **Fork** in the top-right of this GitHub page. This gives you your own private copy.

---

### Step 2 — Edit your profile

Open `profile.yaml` in your forked repo and fill it out with your background, target roles, and location preferences. Every field has comments explaining what to put.

```yaml
candidate:
  education:
    - "Your University — Degree, Major"
  experience:
    - "Company Name — your role description"
  skills:
    - "Your key skills"

target_roles:
  - category: "Strategy & Operations"
    description: "Chief of Staff, Strategy & Operations, Business Operations..."
```

This file drives everything — Claude reads your profile and scores jobs against it automatically.

---

### Step 3 — Edit your company list

Open `companies.json` and add or remove the employers you want to monitor. The file ships with ~80 companies across:
- Universities (NYU, Columbia, Harvard, Stanford, etc.)
- Foundations (Ford, MacArthur, Gates, Rockefeller, etc.)
- UN system and development banks
- Nonprofits and think tanks
- Tech companies, media, and more

Each entry looks like:

```json
{ "name": "Ford Foundation", "ats": "greenhouse", "slug": "fordfoundation" }
```

Supported ATS platforms and how to find the slug:
- **Greenhouse**: slug is in the careers URL — `boards.greenhouse.io/[slug]`
- **Lever**: `jobs.lever.co/[slug]`
- **Ashby**: `jobs.ashbyhq.com/[slug]`
- **Workday**: requires the full API URL — see examples in the file
- **SmartRecruiters**: use the company ID from their careers page URL
- **Custom**: provide the careers page URL directly

---

### Step 4 — Create your Google Sheet

1. Go to [Google Sheets](https://sheets.google.com) and create a new spreadsheet
2. Name the first tab **Jobs** (exact spelling, capital J)
3. Copy the spreadsheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/`**`1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms`**`/edit`

---

### Step 5 — Create a Google service account

This gives the script permission to write to your sheet.

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Google Sheets API** (search for it in the API library)
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
5. Give it any name (e.g. `job-tracker`)
6. Click **Create and Continue** → skip role → **Done**
7. Click the service account → **Keys** tab → **Add Key → JSON**
8. Download the JSON file — keep it safe

Now share your Google Sheet with the service account:
- Open your sheet → **Share** → paste the service account email (looks like `job-tracker@your-project.iam.gserviceaccount.com`) → **Editor** → **Send**

---

### Step 6 — Add secrets to GitHub

In your forked repo: **Settings → Secrets and variables → Actions → New repository secret**

Add three secrets:

| Name | Value |
|------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (starts with `sk-ant-...`) |
| `GOOGLE_SHEETS_ID` | The spreadsheet ID from Step 4 |
| `GOOGLE_CREDS_JSON` | The entire contents of the JSON file from Step 5 (paste the whole thing) |

---

### Step 7 — Run it

Go to **Actions** in your GitHub repo → **Job Tracker** → **Run workflow**

Watch the logs. After a minute or two, check your Google Sheet — new jobs should appear.

From now on it runs automatically every Monday and Wednesday at 8 AM EST.

---

## Customization

### Adjust the relevance threshold

In `job_tracker.py`, change `RELEVANCE_THRESHOLD` (default: 7). Lower it to see more jobs; raise it for stricter filtering.

```python
RELEVANCE_THRESHOLD = 7   # jobs scoring below this are excluded
```

### Change the schedule

In `.github/workflows/job_tracker.yml`, edit the cron expressions. [crontab.guru](https://crontab.guru) is useful for building cron syntax.

```yaml
- cron: "0 13 * * 1"   # Monday 8 AM EST
- cron: "0 13 * * 3"   # Wednesday 8 AM EST
```

### Upgrade the Claude model

The default is `claude-haiku-4-5-20251001` (fast and cheap — about $0.01–0.05 per run). Swap to `claude-sonnet-4-6` for more nuanced scoring.

```python
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
```

---

## Cost

- **GitHub Actions**: free (well within the free tier for a twice-weekly job)
- **Anthropic API**: roughly $0.01–0.05 per run with Haiku; ~$0.20–0.50 with Sonnet
- **Google Sheets API**: free

A typical month costs less than $1.

---

## Troubleshooting

**No jobs appear in my sheet**
- Check the Actions log for errors
- Verify all three secrets are set correctly
- Make sure the sheet tab is named exactly `Jobs`
- Make sure the service account has Editor access to the sheet

**Claude returns invalid JSON**
- This is rare. The script logs a warning and skips the batch; it will retry on the next run.

**A company's jobs aren't showing up**
- The ATS slug may have changed. Check the company's careers page URL and update `companies.json`.

**I want to add a company not in the list**
- Find their ATS (look at the careers URL — it usually contains "greenhouse", "lever", "ashby", etc.)
- Add them to `companies.json` following the format of existing entries

---

## Questions?

Open an issue in this repo.
