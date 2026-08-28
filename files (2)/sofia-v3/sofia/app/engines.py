"""
Sofia — engine dispatch.

One entry point: `run(tool, inputs)`. It picks the model and temperature for
the task, assembles the system message from the cached Core plus the engine
module, builds the tagged user message, calls Kimi, and returns a result the
route layer can render.

Adding an engine means adding a handler here and a prompt module in
ai/prompts/engines.py. Nothing else changes — the catalog already drives the
routing, the pricing and the UI.
"""

from __future__ import annotations

import html
import logging
import re

from app.ai import kimi
from app.ai.prompts.core import build_system
from app.ai.prompts.engines import module_for
from config import Config

log = logging.getLogger("sofia.engines")

# Built once at import. These are the stable cached prefixes — one per
# engine, per mode. Do not build them per request.
_SYSTEM_CACHE: dict[tuple[str, bool], str] = {}


def system_for(engine: str, machine: bool = False) -> str:
    key = (engine, machine)
    if key not in _SYSTEM_CACHE:
        _SYSTEM_CACHE[key] = build_system(module_for(engine), machine=machine)
    return _SYSTEM_CACHE[key]


class EngineError(Exception):
    def __init__(self, message: str, code: str = "engine_error"):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- #
#  Input helpers
# --------------------------------------------------------------------------- #
MAX_FIELD_CHARS = 60_000


def tag(name: str, value: str) -> str:
    """
    Wrap a value in an XML tag for the user message.

    The closing-tag scrub matters: a user could paste a CV containing
    '</cv>' followed by instructions, and without this the model would see
    them as a new top-level section rather than as data.
    """
    text = (value or "").strip()[:MAX_FIELD_CHARS]
    text = re.sub(rf"</?\s*{re.escape(name)}\s*>", "", text, flags=re.IGNORECASE)
    return f"<{name}>\n{text}\n</{name}>"


def require(inputs: dict, key: str, label: str) -> str:
    value = (inputs.get(key) or "").strip()
    if not value:
        raise EngineError(f"{label} is required.", code="missing_input")
    return value


# --------------------------------------------------------------------------- #
#  E1 — Career & CV
# --------------------------------------------------------------------------- #
def _e1_analysis(tool: dict, inputs: dict) -> tuple[dict, dict]:
    cv = require(inputs, "cv", "Your CV")
    jd = (inputs.get("jd") or "").strip()

    shape = {
        "overallScore": "number 0-100",
        "grade": "one of A B C D F",
        "headline": "one sentence: the single most important thing about this CV",
        "killIssues": ["string — things that get this CV rejected before it is read"],
        "contentQuality": [{"dimension": "str", "score": "number 0-10",
                            "finding": "str, quoting the line it refers to", "fix": "str"}],
        "strategicFit": [{"dimension": "str", "score": "number 0-10",
                          "finding": "str", "fix": "str"}],
        "presentationTrust": [{"dimension": "str", "score": "number 0-10",
                               "finding": "str", "fix": "str"}],
        "atsNotes": ["string"],
        "missingEvidence": ["string — the [NEEDS INPUT: ...] items worth chasing"],
    }

    user = "\n\n".join([
        "Task: T1 — CV analysis.",
        tag("cv", cv),
        tag("job_description", jd) if jd else
            "<job_description>None supplied. Omit strategicFit entirely.</job_description>",
        _json_instruction(shape),
    ])

    data, usage = kimi.complete_json(
        system=system_for("E1", machine=True),
        user=user,
        role="scoring",
        temperature=0.2,
        max_tokens=3500,
        required_keys=["overallScore", "grade", "killIssues"],
    )
    return {"kind": "scorecard", "data": data}, usage


def _e1_rewrite(tool: dict, inputs: dict) -> tuple[dict, dict]:
    cv = require(inputs, "cv", "Your CV")
    jd = (inputs.get("jd") or "").strip()

    user = "\n\n".join([
        "Task: T2 — Rewrite this CV in full under the rewrite rules.",
        tag("cv", cv),
        tag("job_description", jd) if jd else
            "<job_description>None supplied. Rewrite for general strength, not a specific role.</job_description>",
        "Output the complete rewritten CV as Markdown. Use ## for section headings "
        "and bullet lists for role achievements. Preserve every fact. Where a bullet "
        "needs a number that was not supplied, insert the [NEEDS INPUT: ...] "
        "placeholder rather than inventing one. End with a short section titled "
        "'What to fill in before you send this', listing every placeholder.",
    ])

    text, usage = kimi.complete(
        system=system_for("E1"),
        user=user,
        role="writing",
        temperature=0.6,
        max_tokens=4000,
    )
    return {"kind": "document", "markdown": text}, usage


def _e1_cover_letter(tool: dict, inputs: dict) -> tuple[dict, dict]:
    cv = require(inputs, "cv", "Your CV")
    jd = require(inputs, "jd", "The job description")
    company = require(inputs, "company", "Company name")

    user = "\n\n".join([
        "Task: T3 — Cover letter.",
        tag("cv", cv),
        tag("job_description", jd),
        tag("company", company),
        "Three to four paragraphs. Open with why this candidate fits this role. "
        "One specific piece of evidence per paragraph, drawn from the CV. Close "
        "with a concrete next step. Do not restate the CV. Output Markdown.",
    ])

    text, usage = kimi.complete(
        system=system_for("E1"), user=user,
        role="writing", temperature=0.6, max_tokens=1600,
    )
    return {"kind": "document", "markdown": text}, usage


def _e1_interview(tool: dict, inputs: dict) -> tuple[dict, dict]:
    cv = require(inputs, "cv", "Your CV")
    jd = require(inputs, "jd", "The job description")

    user = "\n\n".join([
        "Task: T4 — Interview preparation.",
        tag("cv", cv),
        tag("job_description", jd),
        "Produce, as Markdown: (1) the eight questions this specific role will "
        "ask, each with the evidence from this candidate's own history that "
        "answers it; (2) the two hardest questions their CV invites, and how to "
        "handle each honestly; (3) five questions the candidate should ask, "
        "chosen to reveal something worth knowing rather than to look engaged.",
    ])

    text, usage = kimi.complete(
        system=system_for("E1"), user=user,
        role="writing", temperature=0.5, max_tokens=3200,
    )
    return {"kind": "document", "markdown": text}, usage


def _e1_profile(tool: dict, inputs: dict) -> tuple[dict, dict]:
    cv = require(inputs, "cv", "Your CV")
    role = require(inputs, "target_role", "Target role")

    user = "\n\n".join([
        "Task: T5 — Profile rewrite.",
        tag("cv", cv),
        tag("target_role", role),
        "Produce, as Markdown: a headline stating what they do and for whom "
        "(not an aspiration), an About section of three short paragraphs written "
        "in the first person, and rewritten bullets for each recent role.",
    ])

    text, usage = kimi.complete(
        system=system_for("E1"), user=user,
        role="scoring", temperature=0.5, max_tokens=2000,
    )
    return {"kind": "document", "markdown": text}, usage


# --------------------------------------------------------------------------- #
#  Registry
# --------------------------------------------------------------------------- #
HANDLERS = {
    "cv-analysis": _e1_analysis,
    "cv-rewrite": _e1_rewrite,
    "cover-letter": _e1_cover_letter,
    "interview-prep": _e1_interview,
    "linkedin-profile": _e1_profile,
    # E2-E7 handlers land here as each engine is built. The catalog already
    # marks their tools 'soon', so the UI will not route to a missing handler.
}


def _json_instruction(shape: dict) -> str:
    import json
    return (
        "Return a JSON object with exactly these keys and value types:\n"
        + json.dumps(shape, indent=2)
    )


def run(tool: dict, inputs: dict) -> tuple[dict, dict]:
    """
    Execute a tool. Returns (result, usage).

    Raises EngineError for anything the user should see as a clear message,
    and kimi.AIError for AI-side failures. Both cause a refund upstream.
    """
    handler = HANDLERS.get(tool["slug"])
    if handler is None:
        raise EngineError(
            f"{tool['name']} is not available yet.", code="not_implemented"
        )
    return handler(tool, inputs)


# --------------------------------------------------------------------------- #
#  Minimal Markdown renderer
# --------------------------------------------------------------------------- #
_MD_NEEDS_INPUT = re.compile(r"\[NEEDS INPUT:([^\]]*)\]")


def render_markdown(text: str) -> str:
    """
    Render a safe subset of Markdown to HTML.

    Deliberately small and deliberately escape-first: the input is model
    output derived from user-supplied documents, so it is treated as
    untrusted. Everything is HTML-escaped before any tag is introduced.

    [NEEDS INPUT: ...] placeholders get their own class so they are
    impossible to miss in the rendered document — which is the entire
    point of the Evidence Tiering Protocol reaching the screen.
    """
    if not text:
        return ""

    out: list[str] = []
    in_list = False
    in_table = False

    for raw in text.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            if in_list:
                out.append("</ul>"); in_list = False
            if in_table:
                out.append("</tbody></table>"); in_table = False
            continue

        esc = html.escape(stripped)

        # inline: bold, italic, code
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", esc)
        esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        esc = _MD_NEEDS_INPUT.sub(
            lambda m: f'<span class="needs-input">NEEDS INPUT:{m.group(1)}</span>', esc
        )

        # tables
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in esc.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c.replace("&#45;", "-")) for c in cells if c):
                continue  # separator row
            if not in_table:
                out.append("<table><thead><tr>")
                out.extend(f"<th>{c}</th>" for c in cells)
                out.append("</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>")
                out.extend(f"<td>{c}</td>" for c in cells)
                out.append("</tr>")
            continue
        if in_table:
            out.append("</tbody></table>"); in_table = False

        # headings
        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            if in_list:
                out.append("</ul>"); in_list = False
            level = min(len(heading.group(1)) + 1, 5)
            body = html.escape(heading.group(2))
            body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body)
            out.append(f"<h{level}>{body}</h{level}>")
            continue

        # lists
        if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+[.)]\s+", stripped):
            if not in_list:
                out.append("<ul>"); in_list = True
            item = re.sub(r"^([-*+]|\d+[.)])\s+", "", esc)
            out.append(f"<li>{item}</li>")
            continue

        if in_list:
            out.append("</ul>"); in_list = False

        if stripped.startswith("---") or stripped.startswith("___"):
            out.append("<hr>")
            continue

        out.append(f"<p>{esc}</p>")

    if in_list:
        out.append("</ul>")
    if in_table:
        out.append("</tbody></table>")

    return "\n".join(out)
