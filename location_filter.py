"""
Location filter for India job postings.
Ensures automation only applies to and processes companies/roles located in India.
"""
import re


INDIAN_CITIES_AND_REGIONS = {
    # All States & UTs
    "india", "karnataka", "maharashtra", "telangana", "tamil nadu", "uttar pradesh",
    "gujarat", "rajasthan", "kerala", "madhya pradesh", "punjab", "haryana", "bihar",
    "west bengal", "odisha", "andhra pradesh", "assam", "goa", "himachal pradesh",
    "uttarakhand", "jharkhand", "chhattisgarh", "delhi", "chandigarh", "jammu", "kashmir",

    # Major Tech Metros & Cities (Any city in India)
    "bengaluru", "bangalore", "whitefield", "electronic city", "koramangala", "indiranagar",
    "bellandur", "marathahalli", "hyderabad", "secunderabad", "cyberabad", "hitec city",
    "gachibowli", "madhapur", "kondapur", "pune", "hinjewadi", "magarpatta", "baner",
    "wakad", "pimpri", "chinchwad", "kharadi", "mumbai", "navi mumbai", "thane", "andheri",
    "powai", "goregaon", "bandra", "bkc", "malad", "airoli", "chennai", "madras", "omr",
    "taramani", "guindy", "sholinganallur", "velachery", "ambattur", "porur", "delhi",
    "new delhi", "ncr", "delhi ncr", "gurgaon", "gurugram", "cyber city", "dlf",
    "noida", "greater noida", "kolkata", "calcutta", "sector v", "salt lake sector", "new town", "rajarhat",
    "ahmedabad", "gandhinagar", "gift city", "jaipur", "sitapura", "kochi", "cochin",
    "kakkanad", "infopark", "smartcity", "ernakulam", "thiruvananthapuram", "trivandrum",
    "technopark", "indore", "bhopal", "chandigarh", "mohali", "panchkula", "lucknow",
    "kanpur", "nagpur", "vadodara", "baroda", "surat", "coimbatore", "visakhapatnam",
    "vizag", "vijayawada", "mysuru", "mysore", "bhubaneswar", "patna", "ranchi", "raipur",
    "dehradun", "nashik", "aurangabad", "sambhajinagar", "mangalore", "mangaluru", "madurai",
    "trichy", "tiruchirappalli", "salem", "hubli", "dharwad", "belgaum", "belagavi",
    "gwalior", "jabalpur", "varanasi", "agra", "meerut", "ghaziabad", "faridabad",
    "amritsar", "jalandhar", "ludhiana", "udaipur", "jodhpur", "kota", "guwahati",
    "shillong", "siliguri", "cuttack", "rourkela", "warangal", "guntur", "nellore",
    "tirupati", "kurnool", "kozhikode", "calicut", "thrissur", "kollam", "goa", "panaji"
}

FOREIGN_PATTERNS = [
    r"\bunited states\b", r"\busa\b", r"\bu\.s\.\b", r"\bnew york\b", r"\bsan francisco\b",
    r"\bchicago\b", r"\bseattle\b", r"\baustin\b", r"\bboston\b", r"\blos angeles\b",
    r"\batlanta\b", r"\bdallas\b", r"\bdenver\b", r"\bmiami\b", r"\bsanta clara\b",
    r"\bchantilly\b", r"\bsunnyvale\b", r"\bpalo alto\b", r"\bmountain view\b", r"\bredmond\b",
    r"\bbellevue\b", r"\bportland\b", r"\bwashington dc\b", r"\bbaltimore\b", r"\bcharlotte\b",
    r"\braleigh\b", r"\bcleveland\b", r"\bcolumbus\b", r"\bpittsburgh\b", r"\bdetroit\b",
    r"\bminneapolis\b", r"\btampa\b", r"\borlando\b", r"\blas vegas\b", r"\bsalt lake city\b",
    r"\brichmond\b", r"\barlington\b", r"\bfairfax\b", r"\breston\b", r"\bmclean\b",
    r"\bgreenwich\b", r"\bstamford\b", r"\bfoster city\b", r"\bannapolis junction\b",
    r"\bbulverde\b", r"\bcanada\b", r"\btoronto\b", r"\bvancouver\b", r"\bmontreal\b",
    r"\bunited kingdom\b", r"\blondon\b", r"\bmanchester\b", r"\baustralia\b", r"\bsydney\b",
    r"\bmelbourne\b", r"\bgermany\b", r"\bberlin\b", r"\bmunich\b", r"\bfrankfurt\b",
    r"\bsingapore\b", r"\bdubai\b", r"\buae\b", r"\babu dhabi\b", r"\beurope\b",
    r"\b,\s*(?:ca|ny|tx|va|wa|fl|ga|il|oh|nc|pa|ma|co|md|ct|mi|mn|nj|az|or|mo|wi|ut)\b",
    r"\b(?:ca|ny|tx|va|wa|fl|ga|il|oh|nc|pa|ma|co|md|ct|mi|mn|nj|az|or|mo|wi|ut)\s+metropolitan area\b"
]


def is_india_job(location: str = "", title: str = "", company: str = "", notes: str = "", url: str = "") -> bool:
    """
    Returns True if the job is explicitly in India (any city/state in India or remote India).
    Returns False if the job is located outside India or has explicit foreign markers.
    """
    loc_lower = location.lower().strip()
    full_text = f"{location} {company} {notes} {title}".lower()

    # 1. Reject if location explicitly matches a foreign country or US state pattern
    if loc_lower and any(re.search(p, loc_lower) for p in FOREIGN_PATTERNS):
        return False

    # 2. Accept if any Indian city / state mentioned anywhere in location or card text
    for ind in INDIAN_CITIES_AND_REGIONS:
        if re.search(rf"\b{re.escape(ind)}\b", full_text):
            return True

    # 3. Currency or salary in Indian Rupees
    if re.search(r"\b(?:inr|lpa|lakhs?|rupees?)\b", full_text):
        return True

    # 4. Naukri domestic listing (unless explicit foreign keyword found)
    if "naukri.com" in url.lower():
        if not any(re.search(p, full_text) for p in FOREIGN_PATTERNS):
            return True

    return False
