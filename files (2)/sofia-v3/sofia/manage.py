#!/usr/bin/env python3
"""
Sofia — management commands.

    python manage.py check-db          Verify the database and schema
    python manage.py create-admin      Create the first admin (prompts for password)
    python manage.py smoke             Boot the app and hit every public route
    python manage.py routes            List every registered URL

The admin is created here rather than seeded in schema.sql so the password is
hashed properly and never sits in plaintext in a .sql file you might later
paste into a support ticket.
"""

import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_db():
    from app.db import init_db
    try:
        init_db()
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1
    print("OK: database reachable and schema complete.")
    return 0


def create_admin():
    from werkzeug.security import generate_password_hash
    from app.auth_service import validate_email, validate_password
    from app.db import execute, query_one

    email = validate_email(input("Admin email: ").strip())
    if not email:
        print("That email is not valid.")
        return 1

    if query_one("SELECT id FROM admins WHERE email = %s", (email,)):
        print("An admin with that email already exists.")
        return 1

    password = getpass.getpass("Password (min 10 chars): ")
    error = validate_password(password)
    if error:
        print(error)
        return 1
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match.")
        return 1

    name = input("Full name: ").strip() or None

    admin_id = execute(
        "INSERT INTO admins (email, password_hash, full_name, role) "
        "VALUES (%s, %s, %s, 'owner')",
        (email, generate_password_hash(password, method="pbkdf2:sha256:600000"), name),
    )
    print(f"OK: admin #{admin_id} created. Sign in at /admin")
    return 0


def smoke():
    """Boot the app and request every public route. Catches template and
    url_for errors that would otherwise be found by a visitor."""
    from app import create_app
    from app import catalog

    application = create_app()
    client = application.test_client()

    paths = ["/", "/pricing", "/contact", "/health", "/robots.txt", "/sitemap.xml",
             "/auth/login", "/auth/signup", "/auth/forgot", "/admin/",
             "/p/terms", "/p/privacy", "/p/security", "/p/disclaimer",
             "/nope-should-404"]
    paths += [f"/tool/{t['slug']}" for t in catalog.TOOLS]

    failures = 0
    for path in paths:
        response = client.get(path)
        expected = 404 if path == "/nope-should-404" else 200
        ok = response.status_code == expected
        if not ok:
            failures += 1
        print(f"{'ok  ' if ok else 'FAIL'} {response.status_code}  {path}")

    print(f"\n{len(paths) - failures}/{len(paths)} routes OK")
    return 1 if failures else 0


def routes():
    from app import create_app
    application = create_app()
    for rule in sorted(application.url_map.iter_rules(), key=lambda r: str(r)):
        methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        print(f"{methods:<18} {rule}")
    return 0


def sweep_jobs():
    """
    Refund jobs stranded in 'running'.

    A job gets stranded when the app process dies mid-generation — a deploy,
    Passenger recycling an idle app, an out-of-memory kill. The user was
    charged and will never get output, so the credits go back.

    Add to cPanel → Cron Jobs, every five minutes:

        cd ~/sofia_app && \\
          /home/cpuser/virtualenv/sofia_app/3.11/bin/python manage.py sweep-jobs
    """
    from app import create_app
    from app.worker import sweep_stale

    create_app()
    swept = sweep_stale()
    print(f"Swept {swept} stalled job(s).")
    return 0


COMMANDS = {
    "check-db": check_db,
    "create-admin": create_admin,
    "smoke": smoke,
    "routes": routes,
    "sweep-jobs": sweep_jobs,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    sys.exit(COMMANDS[sys.argv[1]]() or 0)
