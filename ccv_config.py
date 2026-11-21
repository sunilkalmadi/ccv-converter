"""Small, editable settings shared by the PDF and DOCX outputs.

Edit this file for labels, numbering prefixes and which supervision fields
are shown. Page layout lives in cv_tmpl.html (PDF) and render_docx.py (DOCX).
"""

# --- Publications -----------------------------------------------------------
# Categories listed here are numbered in reverse: with N entries, the first
# displayed entry is PREFIX N and the last is PREFIX 1. Display order is the
# XML order (newest first). Categories not listed are numbered 1., 2., 3., ...
PUBLICATION_PREFIXES = {
    "Journal Articles": "J",
    "Conference Publications": "C",
    "Book Chapters": "BC",
    "Magazine Entries": "M",
    "Reports": "R",
}

# Publication categories shown, in this order (same order as the upstream CV).
PUBLICATION_ORDER = [
    "Journal Articles",
    "Book Chapters",
    "Encyclopedia Entries",
    "Magazine Entries",
    "Reports",
    "Conference Publications",
]

# --- Student/Postdoctoral Supervision -----------------------------------------
# Group headings come from the XML field below, shown as "<value> [n=<count>]".
SUPERVISION_GROUP_FIELD = "Degree Type or Postdoctoral Status"
SUPERVISION_GROUP_MISSING = "Level Not Specified"

# Groups listed here are shown first, in this order (matching ignores case and
# straight vs curly apostrophes). Any other group found in the XML (Diploma,
# Research Associate, ...) follows in the order it first appears.
SUPERVISION_GROUP_ORDER = [
    "Bachelor's",
    "Master's Thesis",
    "Master's non-Thesis",
    "Doctorate",
    "Post-doctorate",
    "Intern",
]

# Optional extra lines under each student's name. Blank fields are skipped.
SUPERVISION_TITLE_FIELD = "Thesis/Project Title"      # 2nd line, indented
SUPERVISION_POSITION_FIELD = "Present Position"       # 3rd line, indented
SUPERVISION_ORG_FIELD = "Present Organization"        # appended to 3rd line
SUPERVISION_SHOW_ORGANIZATION = True
SUPERVISION_POSITION_MARKER = ">> "

# --- Research funding ----------------------------------------------------------
# Grants are grouped by the CCV "Funding Status" field, in this order, with these headings.
FUNDING_STATUS_ORDER = ["Awarded", "Under Review", "Completed", "Declined", "Withdrawn"]
FUNDING_STATUS_TITLES = {"Awarded": "Awarded (active)"}

# --- Other -------------------------------------------------------------------
# Employment records with these position titles are left out (upstream rule).
EMPLOYMENT_HIDE_TITLES = ["Consultant"]

# =============================================================================
# "Reviewer" style (python xml2html_cv.py --style reviewer). Content rules are in
# style_reviewer.py; layout in cv_tmpl_reviewer.html (PDF) and render_docx.py (Word).
# =============================================================================

# Funding roles counted as "principal" (everything else is listed as co-investigator etc.).
REVIEWER_PI_ROLES = ["Principal Investigator", "Principal Applicant"]

# The CV owner's name is bolded in author lists. Forms such as "Russ Greiner",
# "R. Greiner" and "Greiner R" are found automatically from the CCV name; add any
# other spellings here (regular expressions), e.g. [r"Greiner, Russell"].
REVIEWER_EXTRA_NAME_PATTERNS = []

# Legend printed above the publications.
REVIEWER_PUBLICATION_LEGEND = ("Bold: CV holder. (*): trainee co-author, as marked in the CCV. "
                               "Numbers (J214 … J1) match the full CV.")

# Long lists get small year dividers.
REVIEWER_YEAR_DIVIDERS = ["Journal Articles", "Conference Publications"]

# Publishing statuses shown as a tag after the citation (others, e.g. "Published", are not).
REVIEWER_STATUS_TAGS = ["Accepted", "In Press", "Submitted", "Revision Requested"]
