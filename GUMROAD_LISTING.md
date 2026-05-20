# Gumroad Listing Copy

---

## Product Name
**Job Tracker — AI-Powered Job Feed to Google Sheets**

## Suggested Price
**$19** (or name your own price, minimum $9)

---

## Short Description (shown in search results)
Stop manually scanning career pages. This tool fetches jobs from 80+ employers, scores them for your profile with Claude AI, and populates your Google Sheet twice a week — automatically.

---

## Full Description

### You're spending hours you don't have on job hunting.

You open LinkedIn. You check 12 company career pages. You scroll past 40 irrelevant postings to find 3 worth applying to. You close the laptop and do it again next week.

There's a better way.

---

### Job Tracker runs on autopilot.

Once set up, this tool:

- **Fetches jobs** directly from employer ATS systems (Greenhouse, Lever, Ashby, Workday, SmartRecruiters) — the same databases behind the "Careers" pages of 80+ companies
- **Scores each posting 1–10** using Claude AI, calibrated specifically to *your* background and target roles
- **Writes only the relevant ones** to a Google Sheet, with a one-line AI explanation for why each role was flagged
- **Runs automatically** every Monday and Wednesday — you wake up to a curated job list, not a firehose

---

### What's inside

- `job_tracker.py` — the main script; handles fetching, filtering, and writing to Sheets
- `profile.yaml` — fill out your background, target roles, and location once; AI does the rest
- `companies.json` — ~80 pre-loaded employers (universities, foundations, UN agencies, tech companies, nonprofits, media); add or remove as you like
- `.github/workflows/job_tracker.yml` — GitHub Actions config for fully automated, twice-weekly runs
- Full setup guide (README) — step-by-step instructions for non-technical users

---

### Works for any job seeker

The profile system is fully configurable. Whether you're targeting:
- **Strategy & operations / chief of staff roles**
- **Policy, government affairs, nonprofit leadership**
- **Business development and partnerships**
- **University administration**
- **Media and entertainment (business side)**
- **International organizations (UN, World Bank, etc.)**
- **Philanthropy and foundations**
- ... or anything else — just describe your background and target roles in `profile.yaml` and the AI calibrates to you.

---

### Requirements

- A GitHub account (free)
- An Anthropic API key (~$0.01–0.05 per run with the default model)
- A Google account

**Total monthly cost: under $1.**

---

### Setup takes about 30 minutes.

The README walks you through every step — creating a Google service account, adding GitHub secrets, and running your first job scan. No coding required to get started.

---

### What you get

One-time purchase. Lifetime access to the repo. All future updates included.

If you get stuck during setup, open a GitHub issue and I'll help you get it running.

---

## Tags (for Gumroad discovery)
job search, job tracker, AI tools, automation, career, Google Sheets, Python, GitHub Actions, productivity, job hunting

## Content Type
Digital product — GitHub repo access (zip download + link to fork)

## Cover Image Ideas
- Screenshot of a populated Google Sheet with scored job listings
- Before/after: "20 tabs open" vs. "curated list in Google Sheets"
- Simple text card: "Your job search, on autopilot."

---

## What to include in the download

Zip file containing:
- `job_tracker.py`
- `profile.yaml`
- `companies.json`
- `filter_prompt.txt` (optional override)
- `requirements.txt`
- `.github/workflows/job_tracker.yml`
- `README.md`

Also include a note pointing buyers to your GitHub repo so they can fork it and get future updates.
