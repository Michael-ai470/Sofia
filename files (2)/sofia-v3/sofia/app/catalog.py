"""
Sofia — tool catalog.

This is the single source of truth for what Sofia offers. The header menu,
the homepage grid, the category filters, the per-tool pages, the credit
costs and the engine dispatch all read from here. Add a tool by adding a
dict; nothing else needs editing.

Fields
------
slug        URL segment. /tool/<slug>. Stable — changing one breaks links.
name        Card title. Short. Two or three words.
blurb       One sentence, benefit-led, in the reader's language.
engine      E1..E7 — which engine module handles it (see the architecture spec).
task        Task ID within the engine (T1..T7).
category    Filter tab it appears under.
credits     Cost to run. 0 = free.
free_preview True when an anonymous user may run it without an account.
status      'live' | 'soon'. 'soon' renders the card greyed with a waitlist.
badge       Optional ribbon: 'New', 'Free', 'Beta'.
icon        Key into ICONS below.
accent      Tile colour token: indigo | amber | teal | rose | violet | slate
inputs      Field spec the tool page renders. Kept declarative so one
            template serves every tool.
"""

from __future__ import annotations

CATEGORIES = [
    {"id": "all",            "label": "All tools"},
    {"id": "career",         "label": "Career"},
    {"id": "recruiting",     "label": "Recruiting"},
    {"id": "business",       "label": "Business"},
    {"id": "tax",            "label": "Tax"},
    {"id": "contracts",      "label": "Contracts"},
    {"id": "finance",        "label": "Finance"},
    {"id": "correspondence", "label": "Correspondence"},
]

ENGINES = {
    "E1": {"name": "Career & CV",             "category": "career"},
    "E2": {"name": "Recruiter",               "category": "recruiting"},
    "E3": {"name": "Business Plans",          "category": "business"},
    "E4": {"name": "Tax & Compliance",        "category": "tax"},
    "E5": {"name": "Contracts",               "category": "contracts"},
    "E6": {"name": "Financial Documents",     "category": "finance"},
    "E7": {"name": "Correspondence",          "category": "correspondence"},
}


# --------------------------------------------------------------------------- #
#  Reusable input field specs
# --------------------------------------------------------------------------- #
_F_CV = {"key": "cv", "type": "file_or_text", "label": "Your CV",
         "hint": "PDF or Word, up to 8 MB — or paste the text.", "required": True}
_F_JD = {"key": "jd", "type": "textarea", "label": "Job description",
         "hint": "Optional. Paste it and Sofia tailors to the role.", "required": False, "rows": 6}
_F_COUNTRY = {"key": "country", "type": "select", "label": "Country",
              "options": ["Nigeria", "Ghana", "Kenya", "South Africa", "United Kingdom", "Other"],
              "required": True}


TOOLS: list[dict] = [
    # ---------------------------------------------------------------- E1 --
    {
        "slug": "cv-analysis", "name": "CV Analysis", "engine": "E1", "task": "T1",
        "category": "career", "credits": 0, "free_preview": True, "status": "live",
        "badge": "Free", "icon": "scan", "accent": "indigo",
        "blurb": "Score your CV against what recruiters actually screen for, and see exactly what is costing you interviews.",
        "inputs": [_F_CV, _F_JD],
    },
    {
        "slug": "cv-rewrite", "name": "CV Rewrite", "engine": "E1", "task": "T2",
        "category": "career", "credits": 3, "free_preview": False, "status": "live",
        "icon": "pen", "accent": "indigo",
        "blurb": "Rewrite every line to lead with the achievement and carry a number. Never invents a thing you did not do.",
        "inputs": [_F_CV, _F_JD,
                   {"key": "template", "type": "select", "label": "Layout",
                    "options": ["Clean single column", "Sidebar"], "required": False}],
    },
    {
        "slug": "cover-letter", "name": "Cover Letter", "engine": "E1", "task": "T3",
        "category": "career", "credits": 2, "free_preview": False, "status": "live",
        "icon": "mail", "accent": "indigo",
        "blurb": "A letter that opens with why you fit this role, not with how excited you are to apply.",
        "inputs": [_F_CV,
                   {"key": "jd", "type": "textarea", "label": "Job description", "required": True, "rows": 6},
                   {"key": "company", "type": "text", "label": "Company name", "required": True}],
    },
    {
        "slug": "interview-prep", "name": "Interview Prep", "engine": "E1", "task": "T4",
        "category": "career", "credits": 2, "free_preview": False, "status": "live",
        "icon": "chat", "accent": "indigo",
        "blurb": "The questions this role will actually ask, answers built from your own evidence, and what to ask them back.",
        "inputs": [_F_CV, {"key": "jd", "type": "textarea", "label": "Job description", "required": True, "rows": 6}],
    },
    {
        "slug": "linkedin-profile", "name": "LinkedIn Profile", "engine": "E1", "task": "T5",
        "category": "career", "credits": 1, "free_preview": False, "status": "live",
        "icon": "profile", "accent": "indigo",
        "blurb": "Headline, About section and experience bullets rewritten for how recruiters search.",
        "inputs": [_F_CV, {"key": "target_role", "type": "text", "label": "Target role", "required": True}],
    },

    # ---------------------------------------------------------------- E2 --
    {
        "slug": "rank-candidates", "name": "Rank Candidates", "engine": "E2", "task": "T1",
        "category": "recruiting", "credits": 2, "free_preview": False, "status": "live",
        "icon": "rank", "accent": "teal",
        "blurb": "Score two to twenty CVs against one role on the same axes, with the line from each CV that justifies the score.",
        "inputs": [{"key": "cvs", "type": "multifile", "label": "Candidate CVs",
                    "hint": "2–20 files. PDF or Word.", "required": True},
                   {"key": "jd", "type": "textarea", "label": "Job description", "required": False, "rows": 6}],
    },
    {
        "slug": "job-description", "name": "Job Description", "engine": "E2", "task": "T2",
        "category": "recruiting", "credits": 1, "free_preview": False, "status": "live",
        "icon": "doc", "accent": "teal",
        "blurb": "A JD that describes the job instead of the ideal human, so the right people self-select in.",
        "inputs": [{"key": "role", "type": "text", "label": "Role title", "required": True},
                   {"key": "level", "type": "select", "label": "Level",
                    "options": ["Intern", "Junior", "Mid", "Senior", "Lead", "Head of"], "required": True},
                   {"key": "context", "type": "textarea", "label": "Team and context", "rows": 4, "required": True}],
    },
    {
        "slug": "screening-questions", "name": "Screening Questions", "engine": "E2", "task": "T3",
        "category": "recruiting", "credits": 1, "free_preview": False, "status": "live",
        "icon": "list", "accent": "teal",
        "blurb": "Questions that separate candidates, each with what a strong answer contains.",
        "inputs": [{"key": "jd", "type": "textarea", "label": "Job description", "required": True, "rows": 6}],
    },

    # ---------------------------------------------------------------- E3 --
    {
        "slug": "business-plan", "name": "Business Plan", "engine": "E3", "task": "T1",
        "category": "business", "credits": 8, "free_preview": False, "status": "live",
        "icon": "plan", "accent": "amber",
        "blurb": "An investor-ready plan where the use of funds adds up and every projection states the assumption behind it.",
        "inputs": [{"key": "business_name", "type": "text", "label": "Business name", "required": True},
                   {"key": "industry", "type": "text", "label": "Industry", "required": True},
                   _F_COUNTRY,
                   {"key": "stage", "type": "select", "label": "Stage",
                    "options": ["Idea", "Pre-revenue", "Revenue-generating", "Scaling"], "required": True},
                   {"key": "funding_amount", "type": "text", "label": "Funding sought", "required": True},
                   {"key": "use_of_funds", "type": "textarea", "label": "How you will spend it", "rows": 3, "required": False},
                   {"key": "description", "type": "textarea", "label": "What does the business do?",
                    "hint": "The problem, who you serve, what makes you different. Specificity is what makes the plan strong.",
                    "rows": 5, "required": True}],
    },
    {
        "slug": "business-proposal", "name": "Business Proposal", "engine": "E3", "task": "T1",
        "category": "business", "credits": 4, "free_preview": False, "status": "live",
        "icon": "handshake", "accent": "amber",
        "blurb": "For a client or partner, not an investor. Leads with what they gain, and reads as written for them alone.",
        "inputs": [{"key": "business_name", "type": "text", "label": "Your business", "required": True},
                   {"key": "target_org", "type": "text", "label": "Who is it for?", "required": True},
                   {"key": "offer", "type": "textarea", "label": "What are you proposing?", "rows": 5, "required": True}],
    },
    {
        "slug": "grant-application", "name": "Grant Application", "engine": "E3", "task": "T2",
        "category": "business", "credits": 4, "free_preview": False, "status": "live",
        "icon": "award", "accent": "amber",
        "blurb": "Answers written to the grant's own scoring criteria, in the funder's own vocabulary.",
        "inputs": [{"key": "grant_name", "type": "text", "label": "Grant name", "required": True},
                   {"key": "organisation", "type": "text", "label": "Awarding organisation", "required": True},
                   {"key": "questions", "type": "textarea", "label": "The questions", "rows": 8, "required": True},
                   {"key": "business", "type": "textarea", "label": "About your business", "rows": 5, "required": True}],
    },
    {
        "slug": "pitch-deck", "name": "Pitch Deck", "engine": "E3", "task": "T6",
        "category": "business", "credits": 4, "free_preview": False, "status": "live",
        "badge": "New", "icon": "slides", "accent": "amber",
        "blurb": "Ten to fifteen slides whose only job is earning the next meeting, with speaker notes for each.",
        "inputs": [{"key": "business_name", "type": "text", "label": "Business name", "required": True},
                   {"key": "audience", "type": "select", "label": "Pitching to",
                    "options": ["Investors", "Demo day / grant panel", "Client or partner"], "required": True},
                   {"key": "stage", "type": "select", "label": "Stage",
                    "options": ["Pre-seed", "Seed", "Series A", "Later"], "required": True},
                   {"key": "description", "type": "textarea", "label": "The business, the traction, the ask", "rows": 6, "required": True}],
    },
    {
        "slug": "document-review", "name": "Document Review", "engine": "E3", "task": "T3",
        "category": "business", "credits": 3, "free_preview": False, "status": "live",
        "icon": "check", "accent": "amber",
        "blurb": "Upload a plan or proposal and get it scored on eight dimensions, with the five weaknesses that cost you most.",
        "inputs": [{"key": "document", "type": "file_or_text", "label": "Your document", "required": True},
                   {"key": "audience", "type": "text", "label": "Who will read it?", "required": True}],
    },
    {
        "slug": "partner-research", "name": "Partner Research", "engine": "E3", "task": "T4",
        "category": "business", "credits": 3, "free_preview": False, "status": "live",
        "icon": "search", "accent": "amber",
        "blurb": "An intelligence profile on the organisation you want to approach, and the one hook that makes the case.",
        "inputs": [{"key": "target_org", "type": "text", "label": "Target organisation", "required": True},
                   {"key": "relationship", "type": "select", "label": "What are you seeking?",
                    "options": ["Investment", "Sponsorship", "Strategic partnership",
                                "Distribution", "Integration", "Community partnership"], "required": True},
                   {"key": "offer", "type": "textarea", "label": "What you bring", "rows": 4, "required": True}],
    },

    # ---------------------------------------------------------------- E4 --
    {
        "slug": "tax-obligations", "name": "Tax Obligations", "engine": "E4", "task": "T1",
        "category": "tax", "credits": 1, "free_preview": False, "status": "soon",
        "badge": "New", "icon": "shield", "accent": "rose",
        "blurb": "Which taxes apply to you and which do not, each with the section of law it comes from.",
        "inputs": [_F_COUNTRY,
                   {"key": "entity_type", "type": "select", "label": "You are",
                    "options": ["Employee", "Freelancer / consultant", "Sole trader",
                                "Partnership", "Limited company"], "required": True},
                   {"key": "period", "type": "text", "label": "Tax period", "required": True}],
    },
    {
        "slug": "tax-computation", "name": "Tax Computation", "engine": "E4", "task": "T2",
        "category": "tax", "credits": 3, "free_preview": False, "status": "soon",
        "badge": "New", "icon": "calc", "accent": "rose",
        "blurb": "A line-by-line liability computation with the arithmetic shown and every rate cited to statute.",
        "inputs": [],
    },
    {
        "slug": "tax-calendar", "name": "Tax Calendar", "engine": "E4", "task": "T4",
        "category": "tax", "credits": 1, "free_preview": False, "status": "soon",
        "icon": "calendar", "accent": "rose",
        "blurb": "Every filing and remittance date for your year, with what happens if you miss each one.",
        "inputs": [],
    },
    {
        "slug": "filing-pack", "name": "Filing Pack", "engine": "E4", "task": "T3",
        "category": "tax", "credits": 2, "free_preview": False, "status": "soon",
        "icon": "folder", "accent": "rose",
        "blurb": "Your computation mapped onto the actual fields of the actual return, in the order the portal asks.",
        "inputs": [],
    },
    {
        "slug": "notice-explainer", "name": "Notice Explainer", "engine": "E4", "task": "T6",
        "category": "tax", "credits": 2, "free_preview": False, "status": "soon",
        "icon": "alert", "accent": "rose",
        "blurb": "Upload a letter from the revenue service and get what it demands, by when, and your options in plain English.",
        "inputs": [],
    },

    # ---------------------------------------------------------------- E5 --
    {
        "slug": "draft-agreement", "name": "Draft Agreement", "engine": "E5", "task": "T1",
        "category": "contracts", "credits": 3, "free_preview": False, "status": "soon",
        "badge": "New", "icon": "contract", "accent": "violet",
        "blurb": "NDAs, service agreements, contractor terms — drafted for your side, in the shortest enforceable form.",
        "inputs": [],
    },
    {
        "slug": "review-agreement", "name": "Review Agreement", "engine": "E5", "task": "T2",
        "category": "contracts", "credits": 3, "free_preview": False, "status": "soon",
        "badge": "New", "icon": "magnify", "accent": "violet",
        "blurb": "Clause by clause, what each one does to you, flagged red, amber or green — plus the clauses that are missing.",
        "inputs": [],
    },
    {
        "slug": "clause-explainer", "name": "Clause Explainer", "engine": "E5", "task": "T3",
        "category": "contracts", "credits": 1, "free_preview": False, "status": "soon",
        "icon": "book", "accent": "violet",
        "blurb": "Paste a clause you do not understand and see what it actually does in practice.",
        "inputs": [],
    },

    # ---------------------------------------------------------------- E6 --
    {
        "slug": "invoice", "name": "Invoice", "engine": "E6", "task": "T1",
        "category": "finance", "credits": 0, "free_preview": True, "status": "soon",
        "badge": "Free", "icon": "receipt", "accent": "slate",
        "blurb": "A compliant invoice with the right tax lines, sequential numbering, and totals that reconcile.",
        "inputs": [],
    },
    {
        "slug": "quotation", "name": "Quotation", "engine": "E6", "task": "T2",
        "category": "finance", "credits": 0, "free_preview": True, "status": "soon",
        "icon": "tag", "accent": "slate",
        "blurb": "A priced quotation with validity dates and terms, ready to convert to an invoice when accepted.",
        "inputs": [],
    },
    {
        "slug": "projections", "name": "Financial Projections", "engine": "E6", "task": "T5",
        "category": "finance", "credits": 3, "free_preview": False, "status": "soon",
        "icon": "chart", "accent": "slate",
        "blurb": "Three statements that reconcile, actuals separated from forecast, every growth assumption named.",
        "inputs": [],
    },
    {
        "slug": "statement-of-account", "name": "Statement of Account", "engine": "E6", "task": "T4",
        "category": "finance", "credits": 1, "free_preview": False, "status": "soon",
        "icon": "ledger", "accent": "slate",
        "blurb": "What each customer owes you and how long it has been outstanding.",
        "inputs": [],
    },

    # ---------------------------------------------------------------- E7 --
    {
        "slug": "business-letter", "name": "Business Letter", "engine": "E7", "task": "T1",
        "category": "correspondence", "credits": 1, "free_preview": False, "status": "soon",
        "icon": "envelope", "accent": "indigo",
        "blurb": "Formal correspondence that states the ask in the first two sentences.",
        "inputs": [],
    },
    {
        "slug": "investor-update", "name": "Investor Update", "engine": "E7", "task": "T2",
        "category": "correspondence", "credits": 1, "free_preview": False, "status": "soon",
        "badge": "New", "icon": "trend", "accent": "indigo",
        "blurb": "Leads with the number, names the problem before the wins, ends with a specific ask.",
        "inputs": [],
    },
    {
        "slug": "difficult-message", "name": "Difficult Message", "engine": "E7", "task": "T3",
        "category": "correspondence", "credits": 1, "free_preview": False, "status": "soon",
        "icon": "balance", "accent": "indigo",
        "blurb": "Escalations, chasers and bad news — three strategies to choose from, not three tones of the same one.",
        "inputs": [],
    },
]


# --------------------------------------------------------------------------- #
#  Icons — 24×24 stroke paths, drawn inline so there is no sprite to cache-bust
# --------------------------------------------------------------------------- #
ICONS = {
    "scan":      "M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M3 12h18",
    "pen":       "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z",
    "mail":      "M4 4h16v16H4zM4 7l8 6 8-6",
    "chat":      "M21 11.5a8.4 8.4 0 0 1-9 8.4 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.1A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5Z",
    "profile":   "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
    "rank":      "M4 20V10M10 20V4M16 20v-7M22 20H2",
    "doc":       "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M9 13h6M9 17h6",
    "list":      "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    "plan":      "M3 3v18h18M7 15l4-4 3 3 5-6",
    "handshake": "m11 17 2 2a1 1 0 1 0 3-3M14 14l2.5 2.5a1 1 0 1 0 3-3l-3.9-3.9a2 2 0 0 1 0-2.8l.8-.8M4 12l4-4 3 3 3-3 5 5M3 9l3-3M18 21l3-3",
    "award":     "M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12ZM8.2 13.9 7 22l5-3 5 3-1.2-8.1",
    "slides":    "M3 4h18v12H3zM12 16v4M8 20h8",
    "check":     "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
    "search":    "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.3-4.3",
    "shield":    "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z",
    "calc":      "M5 2h14v20H5zM9 6h6M9 11h.01M12 11h.01M15 11h.01M9 15h.01M12 15h.01M15 15h.01M9 19h6",
    "calendar":  "M3 6h18v15H3zM3 10h18M8 3v4M16 3v4",
    "folder":    "M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z",
    "alert":     "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
    "contract":  "M15 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6ZM15 2v4h4M9 14l2 2 4-4",
    "magnify":   "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM21 21l-5-5M8 10h4M10 8v4",
    "book":      "M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 0 4 22ZM4 19.5h16",
    "receipt":   "M5 2v20l2.5-2 2.5 2 2-2 2 2 2.5-2L19 22V2ZM9 8h6M9 12h6M9 16h4",
    "tag":       "m20.6 13.4-7.2 7.2a2 2 0 0 1-2.8 0l-7.2-7.2a2 2 0 0 1-.6-1.4V4a1 1 0 0 1 1-1h8a2 2 0 0 1 1.4.6l7.4 7.4a2 2 0 0 1 0 2.8ZM7.5 7.5h.01",
    "chart":     "M3 3v18h18M8 17V10M13 17V6M18 17v-4",
    "ledger":    "M4 3h16v18H4zM8 3v18M12 8h5M12 12h5M12 16h5",
    "envelope":  "M3 5h18v14H3zM3 5l9 7 9-7",
    "trend":     "m3 17 6-6 4 4 8-8M15 7h6v6",
    "balance":   "M12 3v18M5 7h14M7 7 4 14h6ZM17 7l-3 7h6ZM8 21h8",
}


# --------------------------------------------------------------------------- #
#  Lookups
# --------------------------------------------------------------------------- #
BY_SLUG = {t["slug"]: t for t in TOOLS}


def get(slug: str) -> dict | None:
    return BY_SLUG.get(slug)


def live_tools() -> list[dict]:
    return [t for t in TOOLS if t["status"] == "live"]


def by_category(cat: str) -> list[dict]:
    if cat in (None, "", "all"):
        return TOOLS
    return [t for t in TOOLS if t["category"] == cat]


def grouped_for_nav() -> list[dict]:
    """Header mega-menu: one column per engine."""
    out = []
    for eid, meta in ENGINES.items():
        items = [t for t in TOOLS if t["engine"] == eid]
        if items:
            out.append({"id": eid, "name": meta["name"], "tools": items})
    return out


def credit_cost(slug: str) -> int:
    tool = BY_SLUG.get(slug)
    return int(tool["credits"]) if tool else 0
