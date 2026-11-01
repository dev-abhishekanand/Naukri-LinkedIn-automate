"""
Instahyre DOM Selectors
Stable CSS and XPath selectors for Instahyre job opportunities, modals, and apply triggers,
inspired by Sachin Shukla's (imsks) Instahyre automation implementation.
"""

# URLs
LOGIN_URL = "https://www.instahyre.com/login/"
OPPORTUNITIES_URL = "https://www.instahyre.com/candidate/opportunities/?matching=true"

# Opportunity Cards and Initial Trigger
VIEW_JOB_BUTTON = (
    "button.btn-interested, "
    "button.btn-success, "
    "button:has-text('View job'), "
    "a:has-text('View job'), "
    "button:has-text('Interested')"
)

EMPLOYER_ROW = (
    ".employer-row, "
    ".opportunity-card, "
    "div[ng-repeat*='opportunity'], "
    ".candidate-opportunity-card"
)

OPPORTUNITY_CARD = EMPLOYER_ROW

ANNOUNCEMENT_MODAL = (
    "#new-ui-announcement-modal button, "
    "button:has-text('Got it!'), "
    ".announcement-modal button"
)

# Apply Triggers (From Sachin Shukla's Automation)
BULK_APPLY_BUTTON = (
    "button[ng-click='applyBulk()'], "
    "button[ng-click*='applyBulk'], "
    "button:has-text('Apply to all'), "
    "button:has-text('Apply to')"
)

NORMAL_APPLY_BUTTON = (
    ".application-modal button:has-text('Apply'), "
    "[ng-controller='employerProfileModalCtrl'] button:has-text('Apply'), "
    ".modal-dialog button:has-text('Apply'), "
    "button.btn-primary:has-text('Apply'), "
    "button[ng-click*='submitChoice(opp, true)']"
)

DECLINE_BUTTON = (
    ".application-modal button:has-text('Not interested'), "
    "[ng-controller='employerProfileModalCtrl'] button:has-text('Not interested'), "
    "button.decline:has-text('Not interested'), "
    "button[ng-click*='submitChoice(opp, false)']"
)

NEXT_JOB_BUTTON = (
    "button[ng-click*='nextJob'], "
    "button:has-text('Next job'), "
    "a:has-text('Next job')"
)

CLOSE_MODAL_BUTTON = (
    "button[aria-label='Close'], "
    "button.close, "
    ".modal-header .close"
)

# Metadata Extraction
MODAL_CONTAINER = "div.modal-content, div.job-modal, div#job-modal"
JOB_TITLE = ".job-title, .position-title, h4.position, .modal-title, h3"
COMPANY_NAME = ".company-name, .employer-name, h5.employer, .employer"
LOCATION = ".job-locations, .location, span.locations"
EXPERIENCE = ".job-experience, .experience"
SKILLS = ".job-skills, .skills, div.tags"
