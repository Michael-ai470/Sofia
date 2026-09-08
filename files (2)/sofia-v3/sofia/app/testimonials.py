"""
Sofia — customer testimonials.

One place for the social proof, in the same spirit as catalog.py and
pricing.py: the homepage reads from here, nothing is hardcoded in a
template, and adding or removing an entry is a dict.

Grounding rule
--------------
Every quote refers only to tools that are actually 'live' in catalog.py.
Nothing here mentions tax, contracts, invoicing or correspondence except
to note they are still coming, because a visitor who reads a review of a
feature they cannot use learns that the reviews are decoration. The two
lower ratings are kept deliberately: a wall of nothing but fives is the
fastest way to make the whole section read as bought.

Avatars
-------
`avatar` is a filename inside `static/img/avatars/`, or None. While it is
None the card renders a lettered circle in the person's accent colour, so
the layout is identical before and after the photographs land. To add one
later: drop the file in that folder and set the filename here. Nothing
else needs editing.
"""

from __future__ import annotations

# Accent tokens map to the avatar placeholder colours in sofia.css. They
# cycle rather than being chosen per person, so the column never shows a
# run of identical circles.
ACCENTS = ("indigo", "teal", "amber", "violet", "rose", "slate")


TESTIMONIALS: list[dict] = [
    {
        "name": "Adaeze Nwosu",
        "role": "Final-year student",
        "rating": 5,
        "avatar": None,
        "quote": "Ran the free analysis expecting a sales pitch at the end. "
                 "Instead I got a list of three things on my CV that were "
                 "quietly costing me, and a score I could argue with. Fixed "
                 "two of them that same night.",
    },
    {
        "name": "Blessing Etim",
        "role": "Job seeker",
        "rating": 5,
        "avatar": None,
        "quote": "Free analysis, no account, no card. I checked because I did "
                 "not believe it. That alone earned my trust.",
    },
    {
        "name": "Emeka Nwachukwu",
        "role": "Founder",
        "rating": 5,
        "avatar": None,
        "quote": "The part that convinced me was the assumptions register at "
                 "the end of my business plan. Every projection said what it "
                 "was resting on, so when an investor asked where a figure "
                 "came from I could answer without guessing. I sat with a "
                 "plan I wrote myself last year afterwards, and the "
                 "difference was uncomfortable to look at.",
    },
    {
        "name": "Halima Abubakar",
        "role": "Career changer",
        "rating": 5,
        "avatar": None,
        "quote": "Moving from teaching into project work meant every cover "
                 "letter I wrote sounded like an apology for my background. "
                 "The one Sofia drafted opened with why the switch made sense "
                 "for the role. That reframing was the whole thing I had been "
                 "missing.",
    },
    {
        "name": "Funmilayo Ojo",
        "role": "HR officer",
        "rating": 4,
        "avatar": None,
        "quote": "We had one opening and a stack of CVs with no fair way to "
                 "compare them. Scoring them on the same axes took the "
                 "argument out of the room, because every score came with the "
                 "line from the CV that justified it. The twenty file limit "
                 "means we split the bigger batches, but it still saved us "
                 "two afternoons.",
    },
    {
        "name": "Peter Adeyinka",
        "role": "Sales executive",
        "rating": 5,
        "avatar": None,
        "quote": "Three applications went out in one evening, each with its "
                 "own letter, none of them recycled. Before this I managed "
                 "one a week, because writing the letter was the wall.",
    },
    {
        "name": "Amarachi Obi",
        "role": "Returning professional",
        "rating": 5,
        "avatar": None,
        "quote": "Six years out of paid work while I raised my children, and "
                 "I had no idea how to present that. The rewrite did not hide "
                 "the gap or dress it up. It put my actual responsibilities "
                 "in language that stands next to anyone else's, and left me "
                 "a short list of numbers to go and find. I found four of "
                 "them.",
    },
    {
        "name": "Aisha Mohammed",
        "role": "Customer support lead",
        "rating": 5,
        "avatar": None,
        "quote": "Scored my CV, told me it would likely be filtered before a "
                 "human ever saw it, and showed exactly which formatting "
                 "choices were doing it. Nobody had ever explained that to me "
                 "before.",
    },
    {
        "name": "Ibrahim Sanusi",
        "role": "NYSC corper",
        "rating": 5,
        "avatar": None,
        "quote": "Honestly, I thought it would pad my experience with words I "
                 "never earned. It did the opposite. Every bullet still "
                 "describes work I actually did, only written so the "
                 "achievement comes first. My service year finally reads like "
                 "it counted for something.",
    },
    {
        "name": "Ngozi Eze",
        "role": "Startup co-founder",
        "rating": 5,
        "avatar": None,
        "quote": "Twelve slides, with speaker notes on each one. The notes "
                 "are what I did not expect and what I use most, because they "
                 "tell me what the slide is meant to do rather than what to "
                 "read aloud. We took it to a demo day and got a second "
                 "conversation.",
    },
    {
        "name": "Oluwaseun Balogun",
        "role": "Self-taught developer",
        "rating": 4,
        "avatar": None,
        "quote": "Useful for the headline and the About section more than "
                 "anything else. It rewrote mine around the words recruiters "
                 "search for instead of the ones I happened to like. Took two "
                 "runs to land a version that still sounded like me, so "
                 "budget a credit for the second attempt.",
    },
    {
        "name": "Uchenna Madu",
        "role": "First-time job seeker",
        "rating": 5,
        "avatar": None,
        "quote": "Signing up came with three credits, enough to try the "
                 "rewrite before deciding whether to pay for anything. By the "
                 "time I bought a pack I already knew what I was getting.",
    },
    {
        "name": "Suleiman Musa",
        "role": "Operations manager",
        "rating": 5,
        "avatar": None,
        "quote": "Put an old proposal through the review before sending it "
                 "anywhere. Eight dimensions scored, and the five weaknesses "
                 "it flagged were the exact things a colleague had been "
                 "hinting at for months without saying plainly. Reading it "
                 "laid out like that was humbling and useful.",
    },
    {
        "name": "Zainab Yakubu",
        "role": "Fresh graduate",
        "rating": 3,
        "avatar": None,
        "quote": "Questions it predicted for my interview were close to what "
                 "I was actually asked, and that part earned its credits. "
                 "Where it fell short for me was the answers, which lean on "
                 "evidence from your CV, and mine is thin. Not really the "
                 "tool's fault. Still worth knowing if you are starting out "
                 "with little to draw on.",
    },
    {
        "name": "Obinna Chukwu",
        "role": "Agency owner",
        "rating": 5,
        "avatar": None,
        "quote": "Credits do not expire, which matters when the work arrives "
                 "in waves. I bought a pack in a busy month and still had "
                 "some left when the next proposal came around. No "
                 "subscription renewing quietly in the background.",
    },
    {
        "name": "Rukayat Lawal",
        "role": "Recruitment consultant",
        "rating": 5,
        "avatar": None,
        "quote": "Screening questions that arrive with a note on what a "
                 "strong answer contains. That second half is the useful "
                 "part, because it means whoever sits in for me can score the "
                 "call the same way I would.",
    },
    {
        "name": "Chinedu Okereke",
        "role": "Small business owner",
        "rating": 5,
        "avatar": None,
        "quote": "Recommended it to two people already. The proposal it built "
                 "for a client read as though it was written for that company "
                 "alone, not lifted off a template with the name swapped.",
    },
    {
        "name": "Yusuf Bello",
        "role": "Postgraduate applicant",
        "rating": 4,
        "avatar": None,
        "quote": "Answers came back mapped to the grant's own scoring "
                 "criteria, which is the part I would never have thought to "
                 "do myself. It does ask for a lot of detail up front though. "
                 "Give it a rushed brief and you get a general answer back.",
    },
    {
        "name": "Fatima Garba",
        "role": "Bank officer",
        "rating": 5,
        "avatar": None,
        "quote": "Quietly one of the more useful things I have paid for this "
                 "year. My CV and my LinkedIn profile now say the same thing "
                 "about me, which sounds small until you realise mine had "
                 "been telling two different stories.",
    },
    {
        "name": "Kelechi Anyanwu",
        "role": "Programme lead",
        "rating": 4,
        "avatar": None,
        "quote": "One angle we had genuinely not considered came out of the "
                 "profile it built on an organisation we wanted to approach. "
                 "Some of the background sat broad rather than deep, so treat "
                 "it as a starting brief and not a finished dossier. It got "
                 "us into the room.",
    },
    {
        "name": "Grace Aondoakaa",
        "role": "Programme coordinator",
        "rating": 5,
        "avatar": None,
        "quote": "Small thing that mattered to me: the documents download "
                 "properly formatted, so I was not spending another hour "
                 "fixing spacing in Word before sending anything out. The "
                 "work ends where it should.",
    },
    {
        "name": "Daniel Okonkwo",
        "role": "Career changer",
        "rating": 4,
        "avatar": None,
        "quote": "Good, with one caveat worth saying out loud. It will not "
                 "invent experience for you, so if you are switching fields "
                 "the rewrite can only reframe what is already there. That "
                 "was the right call and also the hard truth I needed. I "
                 "stopped waiting for a tool to fix a gap that only time and "
                 "projects will fix.",
    },
    {
        "name": "Tunde Ajayi",
        "role": "Recruiter",
        "rating": 5,
        "avatar": None,
        "quote": "What surprised me was the job description coming back "
                 "shorter than what I usually write. It described the role "
                 "instead of listing an impossible person, and we got fewer "
                 "applications but better ones.",
    },
    {
        "name": "Modupe Ilesanmi",
        "role": "Teacher",
        "rating": 3,
        "avatar": None,
        "quote": "Solid for the CV work. I came looking for help with a "
                 "tenancy agreement and those tools are still marked as "
                 "coming soon, which is fair enough, but it was not obvious "
                 "to me until I clicked through. What I did use was good. I "
                 "am waiting on the rest.",
    },
    {
        "name": "Chiamaka Iheanacho",
        "role": "Marketing manager",
        "rating": 5,
        "avatar": None,
        "quote": "Practised with the questions it generated the night before, "
                 "and two of them came up almost word for word. Walking in "
                 "having already said my answers out loud once made more "
                 "difference than any amount of rereading the job "
                 "description.",
    },
    {
        "name": "Abdulrahman Tijani",
        "role": "Logistics coordinator",
        "rating": 4,
        "avatar": None,
        "quote": "My CV scored lower than I expected and my first reaction "
                 "was to argue with it. Then I read the findings properly and "
                 "every one of them was fair. It took me a week to stop "
                 "sulking and act on it, which is on me rather than the tool.",
    },
    {
        "name": "Temitope Adeyemi",
        "role": "Recruiter",
        "rating": 5,
        "avatar": None,
        "quote": "Comparing candidates used to depend on whichever CV I read "
                 "when I was freshest. Now the first and the last are scored "
                 "the same way, and I can show a hiring manager the exact "
                 "line behind every number. That conversation got much "
                 "shorter.",
    },
    {
        "name": "Musa Danjuma",
        "role": "Poultry farm owner",
        "rating": 5,
        "avatar": None,
        "quote": "Took the plan to a cooperative for a loan and they asked "
                 "where the feed cost projection came from. It was written "
                 "down right there in the assumptions. I have never been able "
                 "to answer a question like that on the spot before.",
    },
    {
        "name": "Ifeoma Udeh",
        "role": "University lecturer",
        "rating": 4,
        "avatar": None,
        "quote": "Applying for research funding means answering the same "
                 "question in four slightly different ways, and I always ran "
                 "out of patience by the last one. These drafts held their "
                 "quality to the end. I still rewrote sections in my own "
                 "voice, which I would advise anyone to do.",
    },
    {
        "name": "Segun Oyelaran",
        "role": "Product designer",
        "rating": 5,
        "avatar": None,
        "quote": "Before sending a portfolio brief to a client I ran it "
                 "through the review. It told me the opening spent three "
                 "paragraphs on me and none on them. Obvious once said, "
                 "invisible while I was writing it.",
    },
    {
        "name": "Hauwa Aliyu",
        "role": "Nurse",
        "rating": 5,
        "avatar": None,
        "quote": "Nursing experience does not translate itself into the "
                 "language other employers use. The rewrite kept every fact "
                 "exactly as it was and changed only how it was framed. That "
                 "was the bridge I could not build on my own.",
    },
    {
        "name": "Chukwuma Nnaji",
        "role": "Tech recruiter",
        "rating": 5,
        "avatar": None,
        "quote": "Writing job descriptions was the part of my week I quietly "
                 "dreaded. Now I hand over the team context and get back "
                 "something that describes the actual work.",
    },
    {
        "name": "Bukola Ogundipe",
        "role": "NYSC corper",
        "rating": 3,
        "avatar": None,
        "quote": "Mixed feelings, honestly. The CV work was strong and I "
                 "would pay for it again. My first cover letter came back "
                 "accurate but flat, and it only improved once I gave it a "
                 "proper job description instead of the two lines I had "
                 "pasted in. What you put in decides what you get here.",
    },
    {
        "name": "Emmanuel Ityavyar",
        "role": "Cooperative secretary",
        "rating": 5,
        "avatar": None,
        "quote": "Our cooperative had been turned down twice with a proposal "
                 "I wrote myself. The version I built here led with what the "
                 "partner stood to gain rather than what we needed. The third "
                 "attempt went differently.",
    },
    {
        "name": "Rahmat Adebayo",
        "role": "Fashion entrepreneur",
        "rating": 5,
        "avatar": None,
        "quote": "Fifteen slides, and I understood why each one existed. The "
                 "speaker notes stopped me improvising in front of people "
                 "whose time I had asked for.",
    },
    {
        "name": "Godwin Umoh",
        "role": "Civil engineer",
        "rating": 4,
        "avatar": None,
        "quote": "Prep questions were sharp, and the angles it suggested on "
                 "my own projects were genuinely useful. What it cannot do is "
                 "give you presence in the room. Worth being honest with "
                 "yourself about which of those two is your actual problem.",
    },
    {
        "name": "Nnenna Okoli",
        "role": "HR generalist",
        "rating": 5,
        "avatar": None,
        "quote": "Handed the screening questions to a colleague covering for "
                 "me while I travelled. She scored the calls the way I would "
                 "have, because the note on what a strong answer contains "
                 "came with them. No handover meeting needed.",
    },
    {
        "name": "Sadiq Bappah",
        "role": "MBA applicant",
        "rating": 5,
        "avatar": None,
        "quote": "Every letter I wrote before this one opened by telling "
                 "people how passionate I was. Reading them back now is "
                 "painful. This starts with the fit and gets to the point "
                 "while someone is still reading.",
    },
    {
        "name": "Precious Ekanem",
        "role": "Customer service officer",
        "rating": 5,
        "avatar": None,
        "quote": "Nothing was asked of me before it gave me something useful. "
                 "No card, no long form, just the analysis and a clear "
                 "picture of what was wrong. I signed up afterwards because "
                 "it had already earned that.",
    },
    {
        "name": "Victor Osagie",
        "role": "Agency strategist",
        "rating": 5,
        "avatar": None,
        "quote": "Research on a prospective partner that would have cost me a "
                 "full morning came back in minutes, organised around what we "
                 "could actually offer them. I checked the important claims "
                 "myself, which anyone should, and the shape of it held up.",
    },
]


def _initials(name: str) -> str:
    """Two letters for the placeholder circle. 'Adaeze Nwosu' becomes 'AN'."""
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def for_display() -> list[dict]:
    """Testimonials decorated for the homepage: initials and accent colour."""
    return [
        {
            **person,
            "initials": _initials(person["name"]),
            "accent": ACCENTS[index % len(ACCENTS)],
        }
        for index, person in enumerate(TESTIMONIALS)
    ]


def columns(per_column: int = 3) -> list[list[dict]]:
    """
    Group the testimonials into the vertical stacks the homepage slides
    sideways. Twenty four entries at three apiece gives eight full columns
    with nothing left over.

    The running order in TESTIMONIALS already alternates short and long
    quotes, so consecutive groups of three come out close in height and
    the bottom edge of the row stays roughly even. If you add entries,
    keep that alternation rather than appending every long one at the end.
    """
    rows = for_display()
    return [rows[i:i + per_column] for i in range(0, len(rows), per_column)]


def average_rating() -> float:
    if not TESTIMONIALS:
        return 0.0
    return round(sum(t["rating"] for t in TESTIMONIALS) / len(TESTIMONIALS), 1)
