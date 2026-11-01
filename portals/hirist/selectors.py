"""
Hirist.tech Portal DOM Selectors & Endpoints
"""

BASE_URL = "https://www.hirist.tech"
JOBS_URL = "https://www.hirist.tech/c/frontend-developer-jobs.html"
LOGIN_URL = "https://www.hirist.tech/login"

# Authentication
PROFILE_BADGE = ".user-profile, .profile-name, .nav-user, a[href*='/candidate/']"
LOGIN_CHECKPOINT = "input[name='email'], button:has-text('Login'), a[href*='/login']"

# Job Listings
JOB_CARDS = ".job-card, .job-box, [class*='jobCard'], article.job"
JOB_TITLE = "h2, h3, .job-title, [class*='title']"
COMPANY_NAME = ".company-name, .recruiter-company, [class*='company']"
LOCATION = ".job-location, [class*='location']"
EXPERIENCE = ".job-exp, [class*='experience']"

# Application Triggers
APPLY_BUTTON = "button:has-text('Apply'), a:has-text('Apply'), .apply-btn"
SUCCESS_INDICATOR = "text='Applied', text='Application Sent', .applied-tag, button:has-text('Applied')"
