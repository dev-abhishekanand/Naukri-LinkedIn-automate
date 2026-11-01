"""
Wellfound (AngelList) Portal DOM Selectors & Endpoints
"""

BASE_URL = "https://wellfound.com"
JOBS_URL = "https://wellfound.com/jobs"
LOGIN_URL = "https://wellfound.com/login"

# Authentication Indicators
USER_MENU = "[data-test='UserAvatar'], [data-test='user-menu'], a[href*='/profile'], button[aria-label*='user menu' i]"
LOGIN_CHECKPOINT = "input[name='email'], button:has-text('Log In'), a[href*='/login']"

# Jobs Feed & Listings
JOB_CARDS = "[data-test='JobSearchResult'], .styles_result__wrap, article[data-test='JobListing'], div[class*='styles_jobListing']"
JOB_TITLE = "a[data-test='JobTitle'], h2, h3, a[class*='styles_title']"
COMPANY_NAME = "a[data-test='StartupName'], h4, a[class*='styles_startupName']"
LOCATION = "[data-test='JobLocation'], [class*='styles_location']"
SALARY = "[data-test='JobCompensation'], [class*='styles_compensation']"

# Application Modal
APPLY_TRIGGER = "button:has-text('Apply'), button[data-test='ApplyButton'], button:has-text('Quick Apply')"
APPLICATION_MODAL = "[data-test='JobApplicationModal'], [role='dialog'], .styles_modal__content"
NOTE_INPUT = "textarea[name='note'], textarea[placeholder*='note' i], textarea[placeholder*='cover letter' i]"
SUBMIT_BUTTON = "button:has-text('Send application'), button[data-test='SubmitButton'], button:has-text('Submit')"
SUCCESS_INDICATOR = "text='Application sent', text='Applied', button:has-text('Applied')"
