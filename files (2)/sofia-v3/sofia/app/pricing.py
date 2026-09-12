"""
Sofia — packages, gateway fees, and the arithmetic behind them.

Everything commercial lives here so a price change is one file. The numbers
come from the June 2026 financial analysis; the gateway routing follows its
dual-gateway recommendation.

Money is stored in kobo (minor units) as integers. Never floats — a rounding
drift of a tenth of a kobo across ten thousand transactions is a real
reconciliation problem, and float arithmetic on money is how it starts.
"""

from __future__ import annotations

from config import Config


# --------------------------------------------------------------------------- #
#  Packages
# --------------------------------------------------------------------------- #
# `strike_minor` is the "original" price shown struck through. It is a real
# anchor, not a fake one: these are the pre-restructure list prices, and the
# sale price is the current offer.
PACKAGES = [
    {
        "id": "starter",
        "label": "Starter",
        "tagline": "A full application cycle",
        "credits": 50,
        "strike_minor": 480_000,      # ₦4,800
        "amount_minor": 250_000,      # ₦2,500
        "tier": "starter",
        "blurb": "Enough for a full application cycle — a rewritten CV, "
                 "cover letters, and interview prep.",
    },
    {
        "id": "pro",
        "label": "Pro",
        "tagline": "Several documents at once",
        "credits": 200,
        "strike_minor": 1_000_000,    # ₦10,000
        "amount_minor": 450_000,      # ₦4,500
        "tier": "pro",
        "popular": True,
        "blurb": "For founders and job seekers running several documents "
                 "at once. Best value per credit under 500.",
    },
    {
        "id": "business-500",
        "label": "Business 500",
        "tagline": "For teams, month after month",
        "credits": 500,
        "strike_minor": 1_800_000,    # ₦18,000
        "amount_minor": 1_000_000,    # ₦10,000
        "tier": "business",
        "blurb": "For teams producing plans, proposals and recruitment "
                 "documents month after month.",
    },
]

FREE_SIGNUP_CREDITS = 3

# The free tier is a card on the pricing page, not a package. It is kept
# out of PACKAGES on purpose: that list is what checkout, the gateways and
# the ledger reason about, and none of them should ever meet an amount of
# zero. Nothing here is purchasable; it describes the signup grant.
FREE_TIER = {
    "id": "free",
    "label": "Free",
    "tagline": "Try 3 documents",
    "credits": FREE_SIGNUP_CREDITS,
    "amount_minor": 0,
    "tier": "free",
}


def package(package_id: str) -> dict | None:
    return next((p for p in PACKAGES if p["id"] == package_id), None)


# --------------------------------------------------------------------------- #
#  Gateways
# --------------------------------------------------------------------------- #
# Monnify for Nigerian users, Paystack for everyone else. The reason is fees:
# on Sofia's price points Monnify's flat-free 1% saves ₦113–₦200 per sale
# against Paystack's 1.5% + ₦100. On a hundred local sales a month that is
# real money for a routing rule that costs nothing to implement.
GATEWAYS = {
    "monnify": {
        "label": "Monnify",
        "for": "Nigerian users",
        "methods": ["Bank transfer", "Card", "USSD", "Virtual account"],
        "rate": 0.01,
        "flat_minor": 0,
        "cap_minor": 100_000,          # ₦1,000
    },
    "paystack": {
        "label": "Paystack",
        "for": "International users",
        "methods": ["Visa", "Mastercard", "Verve", "Amex"],
        "rate": 0.039,
        "flat_minor": 10_000,          # ₦100
        "cap_minor": None,             # no cap on international
    },
}


def gateway_for(country: str | None) -> str:
    """
    Nigerian users go to Monnify, everyone else to Paystack.

    Falls back to Paystack when the country is unknown: charging a slightly
    higher fee is a smaller failure than routing an international card to a
    gateway that will decline it.
    """
    code = (country or "").strip().upper()
    if code in ("NG", "NGA", "NIGERIA"):
        return "monnify"
    return "paystack"


def gateway_fee(amount_minor: int, gateway: str) -> int:
    """Fee in kobo. Integer arithmetic throughout."""
    spec = GATEWAYS[gateway]
    fee = int(amount_minor * spec["rate"]) + spec["flat_minor"]
    if spec["cap_minor"] is not None:
        fee = min(fee, spec["cap_minor"])
    return fee


# --------------------------------------------------------------------------- #
#  Display helpers
# --------------------------------------------------------------------------- #
def naira(minor: int) -> str:
    return f"₦{minor / 100:,.0f}"


def usd_to_ngn_minor(usd: float) -> int:
    return int(round(usd * Config.USD_NGN * 100))


def per_credit_minor(pkg: dict) -> int:
    return int(round(pkg["amount_minor"] / pkg["credits"]))


def discount_pct(pkg: dict) -> int:
    if not pkg.get("strike_minor"):
        return 0
    return int(round((1 - pkg["amount_minor"] / pkg["strike_minor"]) * 100))


def for_display(country: str | None = None) -> list[dict]:
    """Packages decorated for the pricing page."""
    gateway = gateway_for(country)
    out = []
    for pkg in PACKAGES:
        out.append({
            **pkg,
            "price": naira(pkg["amount_minor"]),
            "strike": naira(pkg["strike_minor"]) if pkg.get("strike_minor") else None,
            "discount": discount_pct(pkg),
            "per_credit": naira(per_credit_minor(pkg)),
            "gateway": gateway,
            "gateway_label": GATEWAYS[gateway]["label"],
            "features": features(pkg),
        })
    return out


# --------------------------------------------------------------------------- #
#  Feature lines for the pricing cards
# --------------------------------------------------------------------------- #
# Any package can run any tool; credits are credits. So these lines describe
# what each size realistically covers, not what it unlocks. The counts are
# computed from the live costs in catalog.py so a change to what a rewrite
# costs is reflected on the pricing page without anyone remembering to edit
# it here. Every tier gets the two lines that are true of all of them first,
# then what grows as the size does.
def _cost(slug: str) -> int:
    from app import catalog
    return catalog.credit_cost(slug)


def _base_lines(pkg: dict) -> list[str]:
    return [
        f"{pkg['credits']} credits, never expire",
        "Works across all three engines",
    ]


def features(pkg: dict) -> list[str]:
    tier = pkg["tier"]
    credits = pkg["credits"]

    if tier == "free":
        return [
            f"{credits} credits, no card required",
            "Works across all three engines",
            "Unlimited free CV analysis",
            "Enough for one full CV rewrite",
        ]

    if tier == "starter":
        return _base_lines(pkg) + [
            "CV rewrites, cover letters & interview prep",
            f"Around {credits // _cost('cv-rewrite')} CV rewrites, "
            f"or {credits // _cost('cover-letter')} cover letters",
        ]

    if tier == "pro":
        return _base_lines(pkg) + [
            "Everything in Starter",
            "Recruiter batch ranking, up to 20 CVs a run",
            "Proposals, grant applications & pitch decks",
        ]

    # business
    return _base_lines(pkg) + [
        "Everything in Pro",
        "Full business plans, document review & partner research",
        f"Rank up to {credits // _cost('rank-candidates')} candidate CVs",
    ]


def tiers(country: str | None = None) -> list[dict]:
    """
    Every card on the public pricing page: the free tier first, then the
    packages. Only the marketing pages use this. The buy page and checkout
    use for_display(), which knows nothing about the free tier — there is
    nothing to buy there.
    """
    free = {
        **FREE_TIER,
        "price": naira(0),
        "meta": f"{FREE_TIER['credits']} credits · included on signup",
        "features": features(FREE_TIER),
    }
    paid = [
        {**pkg, "meta": f"{pkg['credits']} credits · {pkg['per_credit']} per credit"}
        for pkg in for_display(country)
    ]
    return [free] + paid


# --------------------------------------------------------------------------- #
#  Margin — used by the admin panel, not by checkout
# --------------------------------------------------------------------------- #
def margin(pkg: dict, ai_cost_usd_per_credit: float, gateway: str = "monnify") -> dict:
    """
    What a sale of this package actually earns, after AI cost and gateway fee.

    `ai_cost_usd_per_credit` should come from measured job telemetry, not from
    a guess. The admin dashboard computes it from the last 30 days of jobs, so
    the margin shown reflects the provider mix actually in use — which is the
    whole point of tracking it after a model migration.
    """
    revenue = pkg["amount_minor"]
    ai_cost = usd_to_ngn_minor(ai_cost_usd_per_credit * pkg["credits"])
    fee = gateway_fee(revenue, gateway)
    net = revenue - ai_cost - fee
    return {
        "revenue_minor": revenue,
        "ai_cost_minor": ai_cost,
        "fee_minor": fee,
        "net_minor": net,
        "margin_pct": round(net / revenue * 100, 1) if revenue else 0.0,
    }
