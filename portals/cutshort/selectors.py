"""
Cutshort Portal DOM Selectors & Endpoints
"""

BASE_URL = "https://cutshort.io"
JOBS_URL = "https://cutshort.io/profile/jobs"
PUBLIC_JOBS_URL = "https://cutshort.io/jobs/frontend-developer-jobs"
LOGIN_URL = "https://cutshort.io/login"

# Auth Indicators
PROFILE_BADGE = "[data-test='user-profile-menu'], .user-avatar, a[href*='/profile'], .nav-profile"
LOGIN_CHECKPOINT = "input[name='email'], button:has-text('Sign In'), button:has-text('Log In')"

# Jobs Feed
JOB_CARDS = "[data-test='job-card'], .job-card, .job-listing-card, article.job"
JOB_TITLE = "h2, h3, [data-test='job-title'], .job-title"
COMPANY_NAME = "[data-test='company-name'], .company-name, .company-title"
LOCATION = "[data-test='job-location'], .location, .job-location"
EXPERIENCE = "[data-test='experience'], .experience"
SALARY = "[data-test='salary'], .salary, .compensation"

# Application Modal
APPLY_BUTTON = "button:has-text('Apply'), [data-test='apply-btn'], button.apply-btn"
APPLICATION_MODAL = ".modal, [role='dialog'], .application-modal"
CUSTOM_MESSAGE_INPUT = "textarea[name='message'], textarea[placeholder*='message' i], textarea[placeholder*='note' i], textarea#coverLetter"
SUBMIT_APPLICATION_BUTTON = "button:has-text('Send Application'), button:has-text('Submit'), button[type='submit']"
SUCCESS_INDICATOR = "text='Application sent', text='Applied successfully', .application-success, button:has-text('Applied')"
