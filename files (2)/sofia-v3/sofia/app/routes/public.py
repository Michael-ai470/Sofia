"""Sofia — public pages: home, tool pages, pricing, contact, legal."""

from __future__ import annotations

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)

from app import catalog
from app.auth_service import client_ip, rate_limited, validate_email
from app.db import execute
from app import pricing as pricing_data
from app import testimonials as testimonials_data
from config import Config

bp = Blueprint("public", __name__)


def _packages():
    return pricing_data.for_display()


@bp.route("/")
def home():
    return render_template(
        "index.html",
        tools=catalog.TOOLS,
        packages=_packages(),
        testimonial_columns=testimonials_data.columns(10),
    )


@bp.route("/tool/<slug>")
def tool(slug):
    item = catalog.get(slug)
    if not item:
        abort(404)

    related = [
        t for t in catalog.TOOLS
        if t["engine"] == item["engine"] and t["slug"] != slug
    ][:5]

    return render_template("tool.html", tool=item, related=related)


@bp.route("/pricing")
def pricing():
    return render_template("pricing.html", packages=_packages(), tools=catalog.TOOLS)


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        if rate_limited(f"contact:{client_ip()}", limit=5, window_seconds=3600):
            flash("Too many messages from this address. Try again later.", "err")
            return redirect(url_for("public.contact"))

        email = validate_email(request.form.get("email", ""))
        body = (request.form.get("body") or "").strip()
        if not email or len(body) < 10:
            flash("Please give a valid email and a message.", "err")
            return redirect(url_for("public.contact"))

        execute(
            "INSERT INTO contact_messages (name, email, subject, body, ip) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                (request.form.get("name") or "").strip()[:120] or "Unknown",
                email,
                (request.form.get("subject") or "").strip()[:200] or None,
                body[:8000],
                client_ip(),
            ),
        )
        flash("Message received. We will reply to the address you gave.", "ok")
        return redirect(url_for("public.contact"))

    return render_template("contact.html")


@bp.route("/waitlist", methods=["POST"])
def waitlist():
    slug = (request.form.get("tool") or "").strip()[:64]
    email = validate_email(request.form.get("email", ""))
    if not email:
        flash("That email does not look right.", "err")
        return redirect(url_for("public.tool", slug=slug) if catalog.get(slug) else url_for("public.home"))

    if not rate_limited(f"waitlist:{client_ip()}", limit=10, window_seconds=3600):
        execute(
            "INSERT INTO contact_messages (name, email, subject, body, ip) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("Waitlist", email, f"waitlist:{slug}",
             f"Requested notification for {slug}.", client_ip()),
        )

    flash("You are on the list. We will email you the day it opens.", "ok")
    return redirect(url_for("public.tool", slug=slug))


LEGAL_PAGES = {
    "terms": {
        "title": "Terms of Service",
        "updated": "21 August 2026",
        "body": """
<p>These terms govern your use of Sofia. Replace this placeholder with terms
reviewed by a qualified lawyer before launch.</p>
<h2>What Sofia does</h2>
<p>Sofia prepares documents. It does not provide legal, tax, financial or
investment advice, does not file returns on your behalf, does not act as your
agent before any authority, and does not act as your counsel.</p>
<h2>Your responsibility</h2>
<p>You are responsible for checking every document Sofia produces before you
rely on it, send it, sign it, or submit it. Where Sofia marks a figure as
requiring input, that figure is not present and you must supply it.</p>
<h2>Credits</h2>
<p>Credits are consumed when a tool runs. If a tool fails, the credits are
returned automatically. Credits do not expire.</p>
""",
    },
    "privacy": {
        "title": "Privacy Policy",
        "updated": "21 August 2026",
        "body": """
<p>Replace this placeholder with a policy reviewed against the Nigeria Data
Protection Act and any other regime that applies to you.</p>
<h2>What we store</h2>
<p>Your account details, your credit balance and history, and the documents you
generate. Uploaded files are converted to text and the original file is
discarded; the extracted text is stored with the job so you can reopen it.</p>
<h2>Processing</h2>
<p>Document generation is performed by Moonshot AI's Kimi models. The text you
submit is sent to that service to produce your document.</p>
<h2>Deletion</h2>
<p>You can delete any document from your account, and you can request deletion
of your account and all associated documents at any time.</p>
""",
    },
    "security": {
        "title": "Security",
        "updated": "21 August 2026",
        "body": """
<h2>Your data in transit</h2>
<p>Every connection is HTTPS. Files are converted to text on our server and the
binary is discarded immediately.</p>
<h2>Passwords and sessions</h2>
<p>Passwords are hashed with PBKDF2-SHA256. Sessions are stored server-side and
can be revoked. Changing your password ends every existing session.</p>
<h2>Payments</h2>
<p>Card details are handled entirely by our payment provider. Sofia never
receives or stores them.</p>
""",
    },
    "disclaimer": {
        "title": "Disclaimer",
        "updated": "21 August 2026",
        "body": """
<h2>Sofia prepares. It does not practise.</h2>
<p>Sofia is a document preparation tool. It is not a law firm, an accountancy
practice, a tax agent, or a financial adviser, and using it does not create any
professional relationship.</p>
<h2>Tax</h2>
<p>Sofia does not file returns and cannot represent you before any revenue
authority. Where your jurisdiction requires an accredited agent to act for a
taxpayer, Sofia is not one. Computations must be reviewed by a qualified
practitioner before you file.</p>
<h2>Contracts</h2>
<p>Drafts and reviews produced by Sofia are a starting point, not legal advice.
Have anything of value reviewed by a qualified lawyer in the governing
jurisdiction before you sign.</p>
<h2>Figures</h2>
<p>Where Sofia marks a figure <strong>[NEEDS INPUT]</strong>, that figure is
absent and must be supplied by you. Sofia does not fill such gaps with
estimates.</p>
""",
    },
}


@bp.route("/p/<slug>")
def page(slug):
    content = LEGAL_PAGES.get(slug)
    if not content:
        abort(404)
    return render_template("legal/page.html", page=content)


@bp.route("/robots.txt")
def robots():
    from flask import Response
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /account\n"
        "Disallow: /api\n"
        f"Sitemap: {Config.SITE_URL}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    from flask import Response
    urls = [Config.SITE_URL + "/", Config.SITE_URL + "/pricing", Config.SITE_URL + "/contact"]
    urls += [f"{Config.SITE_URL}/tool/{t['slug']}" for t in catalog.TOOLS]
    urls += [f"{Config.SITE_URL}/p/{s}" for s in LEGAL_PAGES]
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
        + "</urlset>\n"
    )
    return Response(body, mimetype="application/xml")


@bp.route("/health")
def health():
    from app.db import query_one
    try:
        query_one("SELECT 1 AS ok")
        db_ok = True
    except Exception:
        db_ok = False
    from flask import jsonify
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "service": "sofia",
        "database": db_ok,
        "aiConfigured": bool(Config.KIMI_API_KEY),
        "tools": len(catalog.TOOLS),
        "live": len(catalog.live_tools()),
    }), (200 if db_ok else 503)
