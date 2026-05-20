"""
Job Tracker — runs on GitHub Actions every Monday & Wednesday.
Fetches job postings from ATS APIs + custom career pages,
filters with Claude AI, deduplicates, and writes to Google Sheets.
"""

import json
import os
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
import anthropic
import gspread
import yaml
from google.oauth2.service_account import Credentials

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_PATH  = Path(__file__).parent / "companies.json"
PROFILE_PATH = Path(__file__).parent / "profile.yaml"
PROMPT_PATH  = Path(__file__).parent / "filter_prompt.txt"  # optional manual override

def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        log.error(
            f"Missing required secret: {name}\n"
            "Add it under Settings → Secrets and variables → Actions in your GitHub repo.\n"
            "See README.md Step 6 for instructions."
        )
        raise SystemExit(1)
    return val

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_SHEETS_ID  = os.environ.get("GOOGLE_SHEETS_ID", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")

# Job board domains that require payment to apply — links from these are excluded
PAID_JOB_BOARD_DOMAINS = [
    "theladders.com",
    "hired.com",
    "toptal.com",
    "ladders.com",
]

RELEVANCE_THRESHOLD = 7   # 1–10; jobs scoring below this are skipped
SHEET_NAME = "Jobs"
REQUEST_TIMEOUT = 15      # seconds per HTTP request
CLAUDE_MODEL = "claude-haiku-4-5-20251001"   # cheapest; swap to sonnet for better filtering

SHEET_HEADERS = [
    "Date Found", "Company", "Title", "Location", "Remote?",
    "Relevance Score", "AI Reason", "Apply Link", "ATS / Source", "Status"
]


# ── ATS Fetchers ───────────────────────────────────────────────────────────────

def fetch_greenhouse(slug: str) -> list[dict]:
    """Greenhouse public API — no auth required."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
        return [
            {
                "title": j.get("title", ""),
                "location": j.get("location", {}).get("name", ""),
                "description": _strip_html(j.get("content", "")),
                "url": j.get("absolute_url", ""),
                "id": f"greenhouse_{slug}_{j['id']}",
            }
            for j in jobs
        ]
    except Exception as e:
        log.warning(f"Greenhouse {slug}: {e}")
        return []


def fetch_lever(slug: str) -> list[dict]:
    """Lever public API — no auth required."""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        jobs = r.json()
        return [
            {
                "title": j.get("text", ""),
                "location": j.get("categories", {}).get("location", ""),
                "description": _strip_html(
                    j.get("descriptionPlain", "") or j.get("description", "")
                ),
                "url": j.get("hostedUrl", ""),
                "id": f"lever_{slug}_{j['id']}",
            }
            for j in jobs
        ]
    except Exception as e:
        log.warning(f"Lever {slug}: {e}")
        return []


def fetch_ashby(slug: str) -> list[dict]:
    """Ashby HQ public API — no auth required."""
    url = f"https://jobs.ashbyhq.com/api/non-user-facing/job-board/list-jobs-for/{slug}"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
        return [
            {
                "title": j.get("title", ""),
                "location": j.get("location", ""),
                "description": _strip_html(j.get("descriptionHtml", "")),
                "url": f"https://jobs.ashbyhq.com/{slug}/{j['id']}",
                "id": f"ashby_{slug}_{j['id']}",
            }
            for j in jobs
        ]
    except Exception as e:
        log.warning(f"Ashby {slug}: {e}")
        return []


def fetch_workday(base_url: str, company_name: str) -> list[dict]:
    """
    Workday — used by large enterprises, universities, banks, UN agencies.
    base_url example: "https://wd5.myworkdayjobs.com/wday/cxs/un/UNCareers"
    """
    url = f"{base_url}/jobs"
    try:
        r = requests.post(
            url,
            json={"limit": 100, "offset": 0},
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        jobs = r.json().get("jobPostings", [])
        return [
            {
                "title": j.get("title", ""),
                "location": j.get("locationsText", ""),
                "description": j.get("jobDescription", {}).get("jobDescription", ""),
                "url": base_url.replace("/cxs/", "/") + j.get("externalPath", ""),
                "id": f"workday_{company_name}_{j.get('bulletFields', [''])[0]}",
            }
            for j in jobs
        ]
    except Exception as e:
        log.warning(f"Workday {company_name}: {e}")
        return []


def fetch_smartrecruiters(company_id: str) -> list[dict]:
    """SmartRecruiters — used by many nonprofits and media orgs."""
    url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings?limit=100"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        jobs = r.json().get("content", [])
        return [
            {
                "title": j.get("name", ""),
                "location": j.get("location", {}).get("city", ""),
                "description": j.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", ""),
                "url": f"https://jobs.smartrecruiters.com/{company_id}/{j['id']}",
                "id": f"smartrecruiters_{company_id}_{j['id']}",
            }
            for j in jobs
        ]
    except Exception as e:
        log.warning(f"SmartRecruiters {company_id}: {e}")
        return []


def fetch_custom(url: str, company_name: str) -> list[dict]:
    """
    Fallback for companies with no standard ATS.
    Fetches raw HTML/JSON — Claude will do its best with the text.
    For real scraping, replace with BeautifulSoup logic per-company.
    """
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        # Return a single synthetic job for Claude to analyze
        # In production, add BeautifulSoup parsing here per company
        return [
            {
                "title": f"[Custom scrape] {company_name}",
                "location": "See link",
                "description": r.text[:3000],  # first 3k chars
                "url": url,
                "id": f"custom_{company_name}_{hash(url)}",
            }
        ]
    except Exception as e:
        log.warning(f"Custom {company_name}: {e}")
        return []


# ── Profile & Prompt ───────────────────────────────────────────────────────────

def load_profile() -> dict:
    """Loads profile.yaml if present; returns empty dict otherwise."""
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def build_filter_prompt(profile: dict) -> str:
    """
    Generates the Claude system prompt from profile.yaml.
    Falls back to filter_prompt.txt if the profile is empty or the file exists as an override.
    """
    if PROMPT_PATH.exists() and not profile:
        return PROMPT_PATH.read_text(encoding="utf-8")

    c = profile.get("candidate", {})
    education  = "\n".join(f"- {e}" for e in c.get("education", []))
    experience = "\n".join(f"- {e}" for e in c.get("experience", []))
    skills     = "\n".join(f"- {s}" for s in c.get("skills", []))
    languages  = "\n".join(f"- {l}" for l in c.get("languages", []))

    roles_text = ""
    for role in profile.get("target_roles", []):
        roles_text += f"\n**{role['category']}**\n{role['description']}\n"

    seniority   = profile.get("seniority", {})
    ideal_band  = ", ".join(seniority.get("target_titles", []))

    scoring = profile.get("scoring", {})
    boost_lines = []
    if scoring.get("boost_remote"):
        boost_lines.append("- **Boost +1** if role is remote-friendly or based in a target city")
    if scoring.get("boost_multilingual"):
        boost_lines.append("- **Boost +1** if the role explicitly values multilingual candidates or international experience")
    if exp_range := scoring.get("boost_experience_range"):
        boost_lines.append(f"- **Boost +1** if {exp_range} of experience is mentioned (matches profile)")

    deprioritize_lines = ""
    for dp in seniority.get("deprioritize", []):
        deprioritize_lines += (
            f"- **Score '{dp['pattern']}' roles low ({dp['max_score']} max)**: {dp['reason']}\n"
        )

    return f"""You are a job relevance screener for a highly qualified professional. Score each posting 1–10 based on fit. Reserve 9–10 for near-perfect matches.

## Candidate Background

**Education**
{education}

**Career History**
{experience}

**Skills**
{skills}

**Languages**
{languages}

---

## Target Roles

Score HIGH (7–10) for roles in these categories:
{roles_text}
---

## Scoring Guide

| Score | Meaning |
|-------|---------|
| 9–10 | Near-perfect: matches 2+ target categories, seniority fits, location or remote works |
| 7–8  | Strong: matches primary target category well, candidate would be competitive |
| 5–6  | Partial: adjacent field or role type, worth knowing about but not a priority |
| 3–4  | Weak: only tangential connection |
| 1–2  | Not relevant: pure engineering, pure medicine, pure trading, etc. |

---

## Scoring Rules

- **Target seniority band**: {ideal_band}
- **Penalize -3** if the role requires 10+ years of experience in a specific industry
- **Penalize -3** if the title is VP, SVP, EVP, Managing Director, Partner, or C-suite (unless small nonprofit/startup)
- **Penalize -2** if the role requires deep technical skills (engineering, data science, clinical) as primary qualification
- **Penalize -2** if the role is clearly entry-level (coordinator, assistant, junior associate, intern)
- **Penalize -1** if the role requires a specific industry license (CPA, Series 7, MD) as a hard requirement
{chr(10).join(boost_lines)}
{deprioritize_lines}
## Output Format

Respond ONLY with a valid JSON array. No preamble, no explanation outside the array.
Each object: {{"job_index": N, "score": N, "reason": "one sentence max 20 words", "remote": "Yes|No|Hybrid"}}"""


def _get_location_keywords(profile: dict) -> list[str]:
    locs = profile.get("locations", {})
    keywords = [kw.lower() for kw in locs.get("target_cities", [])]
    if locs.get("remote_ok", True):
        keywords += ["remote", "anywhere", "distributed", "work from home", "work from anywhere"]
    return keywords


def is_target_location(job: dict, profile: dict) -> bool:
    keywords = _get_location_keywords(profile)
    if not keywords:
        return True
    loc = (job.get("location", "") + " " + job.get("title", "")).lower()
    if not job.get("location"):
        return True
    return any(kw in loc for kw in keywords)


def filter_jobs_with_claude(jobs: list[dict], base_prompt: str, profile: dict = None) -> list[dict]:
    """
    Sends batches of job postings to Claude for relevance scoring.
    Returns only jobs at or above RELEVANCE_THRESHOLD.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    results = []

    # Process in batches of 5 to keep token count manageable
    batch_size = 5
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i : i + batch_size]
        jobs_text = ""
        for idx, job in enumerate(batch):
            jobs_text += (
                f"\n---JOB {idx+1}---\n"
                f"Title: {job['title']}\n"
                f"Company: {job.get('company', '')}\n"
                f"Location: {job['location']}\n"
                f"URL: {job['url']}\n"
                f"Description (first 800 chars): {job['description'][:800]}\n"
            )

        user_message = (
            f"{jobs_text}\n\n"
            "For each job above, respond with a JSON array. Each element must have:\n"
            '  "job_index": (1-based),\n'
            '  "score": (1-10 integer),\n'
            '  "reason": (one sentence, max 20 words),\n'
            '  "remote": ("Yes", "No", or "Hybrid")\n'
            "Respond with ONLY the JSON array, no other text."
        )

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1000,
                system=base_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            scores = json.loads(raw)

            for item in scores:
                idx = item["job_index"] - 1
                if 0 <= idx < len(batch):
                    job = batch[idx]
                    job["score"] = item.get("score", 0)
                    job["reason"] = item.get("reason", "")
                    job["remote"] = item.get("remote", "")
                    if job["score"] >= RELEVANCE_THRESHOLD:
                        results.append(job)

        except Exception as e:
            log.warning(f"Claude batch {i//batch_size + 1} failed: {e}")
            # On failure, include jobs with score=0 so you can review
            for job in batch:
                job["score"] = 0
                job["reason"] = "Filter failed — review manually"
                job["remote"] = "Unknown"

        time.sleep(0.5)  # gentle rate limiting

    return results


# ── Google Sheets ──────────────────────────────────────────────────────────────

def get_sheet():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEETS_ID)
    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(SHEET_HEADERS))
        ws.append_row(SHEET_HEADERS)
    return ws


def get_existing_ids(ws) -> set[str]:
    """Returns set of job IDs already in the sheet (stored in a hidden Notes column)."""
    # We store the internal job ID in the last data column (col 11, after Status)
    try:
        col_data = ws.col_values(11)  # column K
        return set(col_data[1:])      # skip header
    except Exception:
        return set()


def write_jobs_to_sheet(ws, jobs: list[dict], existing_ids: set[str]) -> int:
    new_count = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows_to_append = []

    for job in jobs:
        if job["id"] in existing_ids:
            continue
        rows_to_append.append([
            today,
            job.get("company", ""),
            job["title"],
            job["location"],
            job.get("remote", ""),
            job["score"],
            job.get("reason", ""),
            job["url"],
            job.get("ats", ""),
            "To Review",      # default Status
            job["id"],        # hidden dedup key in col K
        ])
        new_count += 1

    if rows_to_append:
        ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")

    return new_count


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    """Naive HTML stripper — good enough for job descriptions."""
    import re
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── Main ───────────────────────────────────────────────────────────────────────

def is_free_to_apply(job: dict) -> bool:
    """Returns False if the job URL comes from a known paid job board."""
    url = job.get("url", "").lower()
    return not any(domain in url for domain in PAID_JOB_BOARD_DOMAINS)


def passes_hard_filters(job: dict, profile: dict) -> bool:
    title       = job.get("title", "").lower()
    location    = job.get("location", "").lower()
    description = job.get("description", "").lower()

    seniority = profile.get("seniority", {})
    too_senior  = seniority.get("too_senior", [])
    exceptions  = seniority.get("senior_exceptions", [])
    too_junior  = seniority.get("too_junior", [])

    # ── Geography hard filter ─────────────────────────────────────────────────
    loc_config = profile.get("locations", {})
    target_locs = [kw.lower() for kw in loc_config.get("target_cities", [])]
    if loc_config.get("remote_ok", True):
        target_locs += ["remote", "anywhere", "distributed", "work from home", "united states", "usa", "u.s.", "us-", ", us"]

    if target_locs and location and location.strip():
        if not any(kw in location for kw in target_locs):
            remote_signals = ["remote", "work from anywhere", "distributed team", "remote-first", "work from home"]
            if not any(kw in description for kw in remote_signals):
                return False

    # ── Seniority hard filter ─────────────────────────────────────────────────
    title_is_senior   = any(kw in title for kw in too_senior)
    title_has_except  = any(kw in title for kw in exceptions)
    if title_is_senior and not title_has_except:
        return False

    # ── Entry-level hard filter ───────────────────────────────────────────────
    if any(kw in title for kw in too_junior):
        return False

    return True


def main():
    # Validate secrets before doing any work
    global ANTHROPIC_API_KEY, GOOGLE_SHEETS_ID, GOOGLE_CREDS_JSON
    ANTHROPIC_API_KEY = _require_env("ANTHROPIC_API_KEY")
    GOOGLE_SHEETS_ID  = _require_env("GOOGLE_SHEETS_ID")
    GOOGLE_CREDS_JSON = _require_env("GOOGLE_CREDS_JSON")

    config  = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    profile = load_profile()
    base_prompt = build_filter_prompt(profile)
    ws = get_sheet()
    existing_ids = get_existing_ids(ws)

    all_jobs: list[dict] = []

    for company in config["companies"]:
        name = company["name"]
        ats  = company.get("ats", "custom")
        slug = company.get("slug", "")
        log.info(f"Fetching: {name} ({ats})")

        if ats == "greenhouse":
            jobs = fetch_greenhouse(slug)
        elif ats == "lever":
            jobs = fetch_lever(slug)
        elif ats == "ashby":
            jobs = fetch_ashby(slug)
        elif ats == "workday":
            jobs = fetch_workday(company.get("workday_url", ""), name)
        elif ats == "smartrecruiters":
            jobs = fetch_smartrecruiters(slug)
        elif ats == "custom":
            jobs = fetch_custom(company.get("careers_url", ""), name)
        else:
            log.warning(f"Unknown ATS '{ats}' for {name}, skipping.")
            jobs = []

        for job in jobs:
            job["company"] = name
            job["ats"] = ats

        all_jobs.extend(jobs)
        time.sleep(0.3)  # polite crawl delay

    log.info(f"Total raw postings fetched: {len(all_jobs)}")

    # Pre-filter: skip jobs already in sheet before hitting Claude
    new_jobs = [j for j in all_jobs if j["id"] not in existing_ids]
    new_jobs = [j for j in new_jobs if is_free_to_apply(j)]
    new_jobs = [j for j in new_jobs if passes_hard_filters(j, profile)]
    new_jobs = [j for j in new_jobs if is_target_location(j, profile)]
    log.info(f"New (not yet in sheet): {len(new_jobs)}")

    if not new_jobs:
        log.info("Nothing new — all done.")
        return

    log.info("Sending to Claude for relevance filtering…")
    relevant_jobs = filter_jobs_with_claude(new_jobs, base_prompt, profile)
    log.info(f"Relevant jobs (score ≥ {RELEVANCE_THRESHOLD}): {len(relevant_jobs)}")

    added = write_jobs_to_sheet(ws, relevant_jobs, existing_ids)
    log.info(f"✓ Added {added} new rows to Google Sheets.")


if __name__ == "__main__":
    main()
