# Naukri & LinkedIn AI Job Automation Suite

A production-ready personal automation suite that searches **Naukri.com** and **LinkedIn** for target roles, automatically applies, answers complex screening questionnaires using facts from your profile, tailors ATS-compliant PDF resumes, conducts automated cold outreach to hiring recruiters on LinkedIn posts, and tracks all applications and obstacles in a live Google Sheet.

Features:
- **Naukri Auto-Apply (`naukri_apply.py`)**: Automated search, filtering, and multi-step screening question handling with unattended mode support.
- **LinkedIn Easy Apply (`linkedin_apply.py`)**: Automated Easy Apply application flow, contact form completion, and profile gap detection.
- **LinkedIn Hiring Posts Cold Outreach (`linkedin_posts_outreach.py`)**: Scrapes recent hiring posts, extracts recruiter email and phone, compiles a tailored PDF resume, drafts high-converting cold pitches via Gemini (Groq fallback), provides interactive terminal review (`[Y/s/e/q]`), and delivers emails via Gmail SMTP SSL.
- **Google Sheets Tracker (`google_sheets_logger.py`)**: Real-time sync for applied jobs, unapplied external links, and recruiter obstacles (`PENDING_MANUAL_DM`) with direct post URLs and resume paths.
- **Human-Presentable PDF Resume Pipeline**: Automatically converts tailored resumes into single-page, universally readable `.pdf` files. Delivered to recruiters with clean, human names (e.g. `Abhishek_Anand_React_Developer.pdf`) with zero AI or bot tags.
- **macOS Morning Scheduler (`launchd`)**: Runs unattended applications automatically Monday through Friday at 09:00 AM IST with a daily limit of 10 applications.
- **Daily Naukri Headline Updater (`naukri_update_headline.py`)**: Rotates and updates your Resume Headline every day (Monday to Sunday) at 09:30 AM IST, ensuring your profile is always marked as "Updated Today" for recruiter search algorithms (Resdex).
- **Naukri Resdex Profile Optimizer & Synchronizer (`naukri_sync_profile.py`)**: Configuration-driven profile synchronizer that keeps your live Naukri profile (Current CTC, Preferred CTC, 29+ Key Skills tags, structured IT Skills matrix with versions and 2026 recency, and GitHub Work Sample) synchronized with `profile.yaml`, maximizing recruiter search appearances.

## Read this before you use it

**Automated applying interacts with platform interfaces.** Both Naukri and LinkedIn have anti-bot protections. This suite reduces risk by running authentic logged-in browser contexts (not raw scrapers), pacing actions with human-like delays, stopping on security checkpoints, and saving state locally. You run this against your own authenticated accounts at your own discretion.

**The scripts never see or store your passwords.** You log into Naukri and LinkedIn once via `login_capture.py`. The resulting session cookies are saved locally (`session_naukri.json`, `session_linkedin.json`) and gitignored.

**Datacenter IPs get blocked.** Platforms block cloud provider IP ranges (AWS, GCP, DigitalOcean). Always run this tool from a residential machine (your Mac / home network).

## What it does

### 1. Automated Job Applying (Naukri & LinkedIn)
- Searches for configured target roles (React Developer, Frontend Engineer, Next.js, etc.) up to the daily cap (default: 10 applications).
- Filters out jobs by experience floor/ceiling, excluded companies, and title requirements.
- Automatically handles screening questions from your `profile.yaml`:
  - Standard fields (experience, notice period, current/expected CTC, location, shifts) are auto-filled directly.
  - Open-ended technical questions are answered by Gemini / Groq strictly using your real achievements.
  - `--unattended` mode fast-skips unanswered screening questions, logging the reason and job link to Google Sheets without pausing the automated run.
- Verifies application submission on the confirmation page before logging.

### 2. LinkedIn Hiring Posts Cold Outreach
- Discovers recent hiring posts for your target roles on LinkedIn.
- Recovers recruiter/HR emails, phone numbers, and company names.
- Dynamically tailors your resume for the post and compiles a pixel-perfect **PDF** (`Abhishek_Anand_{Role}.pdf`).
- Drafts a hyper-personalized cold email pitch highlighting candidate metrics and immediate availability.
- Displays an interactive preview in the terminal:
  - `[Y]es`: Sends email with PDF attached via Gmail SMTP.
  - `[s]kip`: Skips this post and logs to Google Sheets.
  - `[e]dit`: Allows manual editing of email body in terminal.
  - `[q]uit`: Exits the run.
- **Obstacle Handling:** If a hiring post has no direct email address (requires LinkedIn DM), the bot logs it to Google Sheets as `PENDING_MANUAL_DM` with the recruiter's profile URL so you can reach out directly.

### 3. Google Sheets Unified Tracking
- Synchronizes every action to your Google Sheet:
  - `APPLIED` / `EMAILED`: Successful applications and outreach.
  - `PENDING_MANUAL_DM`: Hiring posts requiring direct messaging.
  - `PENDING` / `SKIPPED`: External application portals or skipped jobs.
  - `TAILORED_MANUAL`: Jobs tailored requiring manual submission.
  - Direct links to recruiter profiles, job postings, and tailored PDF resumes.

## Requirements

- Python 3.10+
- A Naukri account with a resume already uploaded
- A free Gemini API key (and optionally a free Groq key as a fallback) --
  see below
- A residential IP (your own computer/phone/home network -- see the
  warning above)

## Setup

```bash
git clone <this-repo-url>
cd naukri-auto-apply
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### Get your free API keys

**Gemini (primary):**

1. Go to <https://aistudio.google.com/apikey>
2. Sign in, click "Create API key" -- no card required for the free tier
3. Free tier is generous (roughly 10 requests/minute, 1,500/day as of
   writing) -- check current limits there, they change

**Groq (optional fallback, recommended):**

1. Go to <https://console.groq.com/keys>
2. Sign in, create a key -- also genuinely free, no card, runs open models
   like Llama
3. If Gemini's quota runs out mid-run, the script automatically switches to
   Groq instead of stopping

### Configure your secrets

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```text
GEMINI_API_KEY=your-gemini-api-key
GROQ_API_KEY=your-groq-api-key                  # fallback LLM
GOOGLE_SHEETS_SPREADSHEET_ID=your-sheet-id      # Google Sheets tracker ID
GMAIL_USER=your-email@gmail.com                 # for cold outreach
GMAIL_APP_PASSWORD=your-16-char-app-password    # Google Account App Password
```

### Configure your profile

```bash
cp profile.example.yaml profile.yaml
```

Edit `profile.yaml` with your real facts: target roles, current CTC, notice period, work history, skills, contact info, etc. This file is the single source of truth for all form answers.

Key parameters in `profile.yaml`:
```yaml
stop_after_n_applications: 10          # Daily cap for applications
pace_seconds_between_actions: 15       # Pacing between browser actions
browser_mode: "minimized"              # minimized | visible | headless
resume_file_name: "Abhishek_Anand_Resume.docx"
```

### Capture your login sessions

Capture your authenticated cookies for both platforms:

```bash
# 1. Naukri session
python login_capture.py naukri

# 2. LinkedIn session
python login_capture.py linkedin
```

A browser window will open. Complete login (password + OTP). Once on your home feed, press Enter in the terminal to save `session_naukri.json` and `session_linkedin.json`.

---

## Running the Automation

### 1. Daily Job Applications (Naukri & LinkedIn)

Run manually or test with the interactive terminal:
```bash
# Naukri apply (interactive or unattended)
.venv/bin/python naukri_apply.py
.venv/bin/python naukri_apply.py --unattended

# LinkedIn Easy Apply (interactive or unattended)
.venv/bin/python linkedin_apply.py
.venv/bin/python linkedin_apply.py --unattended
```

### 2. LinkedIn Hiring Posts Cold Outreach

Discover hiring posts, extract recruiter emails, tailor PDF resumes, and send cold emails:

```bash
# Interactive review mode (prompts [Y/s/e/q] before sending):
.venv/bin/python linkedin_posts_outreach.py --role "React Developer"

# Dry run mode (scrapes, tailors, drafts, and logs without sending):
.venv/bin/python linkedin_posts_outreach.py --role "React Developer" --dry-run

# Custom cap:
.venv/bin/python linkedin_posts_outreach.py --max-emails 10
```

### 3. LinkedIn Frontend & React Interview Prep Scraper

Scrapes real interview experiences and technical questions shared on LinkedIn, parses them into topics, specific questions, coding/machine coding tasks, system design, and tips, saving directly to the **"Frontend Interview Prep"** worksheet in Google Sheets:

```bash
# Default search (React & Frontend questions):
.venv/bin/python linkedin_interview_scraper.py

# Search a specific query:
.venv/bin/python linkedin_interview_scraper.py --query "React interview questions"
.venv/bin/python linkedin_interview_scraper.py --query "Frontend machine coding round"

# Dry run (analyze and preview in terminal without sheet sync):
.venv/bin/python linkedin_interview_scraper.py --dry-run
```

### 4. Naukri Profile Resdex Optimization & Sync (`naukri_sync_profile.py`)

Recruiter searches on Naukri (Resdex) prioritize profiles with complete salary information (to avoid ₹0 CTC filter disqualification), recency (IT Skills "Last Used: 2026"), high keyword coverage (up to 30 Key Skills), and project links. `naukri_sync_profile.py` automatically synchronizes these sections on your live portal directly from `profile.yaml`.

```bash
# Dry run mode: inspect live portal against profile.yaml without making changes
.venv/bin/python naukri_sync_profile.py --dry-run

# Full live sync: update Basic Details CTC, Preferred CTC, Key Skills, IT Skills, and GitHub Work Sample
.venv/bin/python naukri_sync_profile.py

# Sync a specific section only:
.venv/bin/python naukri_sync_profile.py --section salary         # Current CTC & Preferred CTC
.venv/bin/python naukri_sync_profile.py --section key_skills     # Up to 30 prioritized tags
.venv/bin/python naukri_sync_profile.py --section it_skills      # Structured IT Skills table
.venv/bin/python naukri_sync_profile.py --section work_sample    # GitHub Accomplishment link
```

### 5. Daily Naukri Headline Rotation (`naukri_update_headline.py`)

Rotates your headline every morning across candidate variants in `naukri_headline_pool` (defined in `profile.yaml`), ensuring your profile is continuously stamped as "Updated: Today" on recruiter searches.

```bash
# Preview next headline rotation (dry run):
.venv/bin/python naukri_update_headline.py --dry-run

# Rotate and update live headline:
.venv/bin/python naukri_update_headline.py
```

### 6. Resume refresh (optional)

```bash
python naukri_refresh_resume.py
```

Removes and re-uploads your resume to keep your profile showing recent activity.

---

## macOS Weekday Morning Scheduler (`launchd`)

The project includes a configured macOS `launchd` service that runs the full job application pipeline every morning unattended.

### Schedule

- **Days:** Monday through Friday
- **Time:** 09:00 AM IST
- **Sequence:** Runs `naukri_apply.py --unattended` followed by `linkedin_apply.py --unattended`
- **Cap:** 10 applications per platform per morning
- **Safety:** Built-in lock protection prevents overlapping runs; skips personal questions safely to avoid stalling.


### Scheduler command reference

All scheduler operations are controlled through the following commands.

Run them from the project root:

#### Install / start the scheduler

```bash
scripts/install_naukri_scheduler.sh
```

This installs the macOS LaunchAgent at:

```text
~/Library/LaunchAgents/com.naukri.linkedin-ai.naukri.plist
```

and loads it into macOS `launchd`.

#### Check scheduler status

```bash
scripts/naukri_scheduler_status.sh
```

Expected output when the scheduler is active:

```text
=== Naukri Scheduler Status ===
Installed: YES
Loaded: YES
```

#### Pause the scheduler

```bash
scripts/pause_naukri_scheduler.sh
```

This temporarily unloads the scheduler.

Pausing does **not** delete the installed scheduler configuration or
application/runtime data.

#### Resume the scheduler

```bash
scripts/resume_naukri_scheduler.sh
```

This loads the already-installed scheduler again.

#### View scheduler logs

Scheduled runs write their logs to:

```text
scheduler_logs/
```

List all scheduler logs:

```bash
ls -lah scheduler_logs/
```

Show the newest scheduler log:

```bash
ls -t scheduler_logs/*.log | head -1
```

Show the last 100 lines of the newest scheduler log:

```bash
tail -n 100 "$(ls -t scheduler_logs/*.log | head -1)"
```

#### Manually run Naukri

The scheduler is optional. You can always run the existing Naukri flow
manually:

```bash
.venv/bin/python naukri_apply.py
```

This does not require the scheduler to be installed.

#### Safely test the scheduler wrapper

To verify the scheduler wrapper without starting Naukri:

```bash
scripts/run_naukri_scheduled.sh --check
```

This checks the project directory, Python executable, and scheduler log
directory.

It does **not** search for jobs or submit applications.

#### Completely uninstall the scheduler

```bash
scripts/uninstall_naukri_scheduler.sh
```

This unloads the LaunchAgent and removes:

```text
~/Library/LaunchAgents/com.naukri.linkedin-ai.naukri.plist
```

It does **not** delete:

- `applications_log.csv`
- `processed_jobs.csv`
- `external_jobs.csv`
- `tailored_jobs.csv`
- Google Sheets data
- Naukri session data
- LinkedIn session data
- generated resumes
- scheduler logs
- project source files
- any other application/runtime history

#### Reinstall the scheduler later

If the scheduler was completely removed and you later want it again:

```bash
scripts/install_naukri_scheduler.sh
```

No application history or previous job data needs to be recreated.

### Scheduler files

The scheduler implementation is stored inside the project:

```text
scripts/
├── run_naukri_scheduled.sh
├── install_naukri_scheduler.sh
├── pause_naukri_scheduler.sh
├── resume_naukri_scheduler.sh
├── naukri_scheduler_status.sh
└── uninstall_naukri_scheduler.sh

launchd/
└── com.naukri.linkedin-ai.naukri.plist
```

The installed macOS LaunchAgent is separate from the Git repository:

```text
~/Library/LaunchAgents/com.naukri.linkedin-ai.naukri.plist
```

### Scheduler runtime files

The scheduler uses these local runtime paths:

```text
scheduler_logs/
.scheduler.lock/
```

`scheduler_logs/` contains scheduler execution logs.

`.scheduler.lock/` is used to prevent overlapping Naukri runs.

These runtime files should remain local and should not be committed to Git.

### Important macOS behavior

This scheduler is a local macOS user LaunchAgent.

The Mac needs to be available for scheduled automation to run reliably, and
browser-based automation may require an active logged-in desktop session.

The scheduler does not bypass:

- CAPTCHA
- OTP
- security verification
- anti-bot controls
- authentication protections
- other human-action requirements

If the existing Naukri application flow stops for human intervention,
the scheduler does not attempt to bypass that protection.

Pausing or uninstalling the scheduler only changes the scheduling mechanism.
It does not remove application history or project data.

## Project structure

```text
naukri_apply.py              Main Naukri search + apply loop (supports --unattended)
naukri_sync_profile.py       Configuration-driven Naukri profile synchronizer (Resdex optimizer)
naukri_update_headline.py    Daily Naukri headline rotation updater (Updated Today stamp)
linkedin_apply.py            LinkedIn Easy Apply bot (supports --unattended)
linkedin_posts_outreach.py   LinkedIn hiring posts scraper, resume tailor & cold emailer
linkedin_interview_scraper.py Frontend & React interview experiences scraper
google_sheets_logger.py      Unified Google Sheets logging for applications & obstacles
naukri_refresh_resume.py     Resume remove/re-upload to maintain freshness
login_capture.py             Interactive session cookie capturer (Naukri & LinkedIn)
schedule_daemon.py           Fallback time-based runner daemon
mobile_dashboard.py          Flask status dashboard, phone-friendly
profile.example.yaml         Profile facts & preferences template -> profile.yaml
.env.example                 Secrets template -> .env

scripts/
  run_naukri_scheduled.sh    Master scheduler script (runs Naukri + LinkedIn sequentially at 09:00 AM)
  install_naukri_scheduler.sh
  pause_naukri_scheduler.sh
  resume_naukri_scheduler.sh
  naukri_scheduler_status.sh
  uninstall_naukri_scheduler.sh
  run_headline_scheduled.sh  Daily headline updater scheduler script (runs at 09:30 AM Mon-Sun)
  install_headline_scheduler.sh

launchd/
  com.naukri.linkedin-ai.naukri.plist    macOS LaunchAgent for morning job applications (09:00 AM Mon-Fri)
  com.naukri.linkedin-ai.headline.plist  macOS LaunchAgent for daily headline rotation (09:30 AM Mon-Sun)

common/
  profile.py                 Loads and validates profile.yaml & answer libraries
  ats_pipeline.py            ATS resume tailoring pipeline orchestrator
  ats_tailoring.py           Deterministic keyword & skill matching engine
  resume_tailor.py           DOCX resume reordering & generator
  pdf_converter.py           Subprocess-isolated DOCX to pixel-perfect PDF converter
  cold_email_drafter.py      Gemini / Groq cold email pitch drafter
  email_sender.py            Gmail SMTP SSL sender with humanized attachment names
  llm.py                     Dispatches to Gemini, falls back to Groq
  gemini.py / groq_llm.py    Provider-specific clients
  human_input.py             Terminal prompts for questions the AI can't answer
  learned_answers.py         Remembers past answers to recurring questions
```

## Known limitations

- Naukri's page markup changes periodically; CSS selectors in
  `naukri_apply.py` may need updating when they do. If something stops
  working, compare against the real page's HTML (right-click the relevant
  element -> Inspect -> Copy outerHTML) and adjust the matching selector.
- LinkedIn support (`linkedin_apply.py`) exists but has had far less
  real-world testing than the Naukri path.
- Radio/checkbox auto-answering only covers a small set of common
  yes/no-style questions out of the box (relocate, night shift, weekend
  work, immediately available, currently employed) -- extend the rules in
  `naukri_apply.py`'s `_auto_decide_option` for your own common questions.
- Development workflow verified.

## License

MIT -- use, modify, and share freely. No warranty; see the risk notice
above.
