"""
Indeed Job Portal DOM Selectors & Endpoints
Supports both in.indeed.com (India) and indeed.com (Global).
"""

BASE_URL = "https://in.indeed.com"
SEARCH_URL = "https://in.indeed.com/jobs"

# Authentication & Header
PROFILE_BADGE = "[aria-label*='Account'], [aria-label*='Profile'], #gnav-account-filter, .gnav-AccountMenu, [data-gnav-element-name='AccountMenu'], button[aria-label*='user menu']"

# Job Page Header & Metadata
JOB_TITLE = "h1[data-testid='jobsearch-JobInfoHeader-title'], h1.jobsearch-JobInfoHeader-title, .jobsearch-JobInfoHeader-title, .jobsearch-JobInfoHeader-title-container h1, [data-testid='simpler-job-title']"
COMPANY_NAME = "[data-testid='inlineHeader-companyName'], [data-company-name='true'], .jobsearch-CompanyInfoContainer a, .jobsearch-InlineCompanyRating-companyHeader"
COMPANY_LOCATION = "[data-testid='inlineHeader-companyLocation'], [data-testid='jobsearch-JobInfoHeader-companyLocation'], div[data-testid='jobsearch-CompanyInfoContainer'] div"
JOB_DESCRIPTION = "#jobDescriptionText, [data-testid='jobDescriptionText'], div.jobsearch-jobDescriptionText"

# Application Buttons
EASILY_APPLY_BTN = "#indeedApplyButton, [data-testid='indeedApplyButton'], button:has-text('Apply now'), a:has-text('Apply now'), button:has-text('Easily apply'), a:has-text('Easily apply')"
EXTERNAL_APPLY_BTN = "button:has-text('Apply on company site'), a:has-text('Apply on company site'), [data-testid='apply-button-link']"
ALREADY_APPLIED_INDICATOR = "div:has-text('You applied'), span:has-text('Applied'), [data-testid='applied-badge']"

# Application Modal / Drawer / IFrame
APPLICATION_IFRAME = "iframe[title*='Indeed Apply'], iframe[id*='indeed-apply-widget'], iframe[name*='indeed-apply-widget']"
MODAL_CONTAINER = "#indeed-apply-widget, div[role='dialog'], .ia-BasePage, div[data-testid='ia-container']"

# Navigation & Actions inside Apply Flow
CONTINUE_BTN = "button:has-text('Continue'), button:has-text('Next'), button[type='submit']:has-text('Continue'), button[type='submit']:has-text('Next')"
REVIEW_BTN = "button:has-text('Review your application'), button:has-text('Review')"
SUBMIT_BTN = "button:has-text('Submit your application'), button:has-text('Submit'), button[type='submit']:has-text('Submit your application')"

# Success Confirmation
SUCCESS_HEADER = "h1:has-text('Your application has been submitted'), [data-testid='application-submitted-header'], h2:has-text('Application submitted'), text='Your application has been submitted'"
