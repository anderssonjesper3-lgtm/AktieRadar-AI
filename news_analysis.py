"""Deterministic, auditable first-pass news analysis. Not an LLM."""
from datetime import datetime, timezone
import re
from order_analysis import parse_order_amount, order_ratio

POSITIVE = ("ny order", "order", "kontrakt", "avtal", "ramavtal", "kund", "leverans",
            "expansion", "strategiskt", "upphandling", "award", "contract")
NEGATIVE = ("vinstvarning", "förlust", "försen", "avbok", "konkurs", "emission",
            "nedskriv", "återkall", "profit warning", "cancellation")
UNCERTAINTY = ("avsiktsförklaring", "memorandum of understanding", "icke-bindande",
               "letter of intent", "potential", "kan komma att")

def analyze_news(item, company):
    title = item.get("title", "")
    description = item.get("description", "")
    text = (title + " " + description).casefold()
    positive = [w for w in POSITIVE if w in text]
    negative = [w for w in NEGATIVE if w in text]
    uncertainty = [w for w in UNCERTAINTY if w in text]
    amount = parse_order_amount(title + " " + description)
    revenue = company.get("annual_revenue_sek")
    ratio = order_ratio(amount, revenue)
    analyst = analyze_analyst_revision(text)
    if analyst["direction"] == "NEGATIV":
        view, impact = "NEGATIV", "Negativ analytikerändring – invänta kursreaktion"
    elif analyst["direction"] == "POSITIV" and not negative:
        view, impact = "POSITIV", "Positiv analytikerändring – invänta kursreaktion"
    elif negative and len(negative) >= len(positive):
        view, impact = "NEGATIV", "Möjlig negativ kurspåverkan"
    elif positive and not negative:
        view, impact = "POSITIV" if not uncertainty else "PRELIMINÄRT POSITIV", "Möjlig positiv kurspåverkan"
    else:
        view, impact = "NEUTRAL / OTILLRÄCKLIG INFORMATION", "Riktning kan inte fastställas"
    if ratio is not None:
        magnitude = "mycket betydande" if ratio >= 20 else "betydande" if ratio >= 5 else "begränsad"
    else:
        magnitude = "kan inte verifieras – ordervärde eller omsättning saknas"
    caveats = []
    if amount is None: caveats.append("Ordervärde kunde inte säkert extraheras ur texten.")
    if revenue is None: caveats.append("Verifierad årsomsättning saknas; ingen order/omsättningskvot visas.")
    if uncertainty: caveats.append("Texten innehåller osäkerhetsformuleringar: " + ", ".join(uncertainty))
    caveats.append("Detta är regelbaserad första analys, inte AI-läsning av hela originalartikeln.")
    return {
        "analyst_revision": analyst,
        "company": company.get("name"), "title": title, "url": item.get("url") or item.get("link"),
        "published": item.get("published") or item.get("date"),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "view": view, "impact": impact, "order_amount_sek": amount,
        "annual_revenue_sek": revenue, "order_revenue_pct": ratio,
        "order_magnitude": magnitude, "positive_terms": positive,
        "negative_terms": negative, "caveats": caveats,
        "forward_hypothesis": ("Om marknaden bekräftar nyheten med stigande kurs och högre volym kan momentum fortsätta. "
          "Om kursen inte reagerar eller volymen avtar ska nyhetssignalen nedgraderas. "
          "Detta är en hypotes, inte en kursprognos.")
    }

def analyze_analyst_revision(text):
    """Conservative detection of analyst changes, not a price forecast."""
    t = text.casefold()
    target = bool(re.search(r"\b(riktkurs(?:en|er)?|price target|target price|kursmål(?:et)?)\b", t))
    raised = bool(re.search(r"\b(höjer|höjt|höjd|höjdes|raised|raises|raise|increased|increases|uppjusterar|uppjusterad)\b", t))
    lowered = bool(re.search(r"\b(sänker|sänkt|sänktes|lowered|lowers|lower|cut|cuts|reduced|nedjusterar|nedjusterad)\b", t))
    upgrade = bool(re.search(r"\b(höjer|höjt|uppgraderar|uppgraderad|upgrades|upgraded)\s+(rekommendationen|rekommendation|rating|recommendation)\b", t))
    downgrade = bool(re.search(r"\b(sänker|sänkt|nedgraderar|nedgraderad|downgrades|downgraded)\s+(rekommendationen|rekommendation|rating|recommendation)\b", t))
    positive = (target and raised) or upgrade
    negative = (target and lowered) or downgrade
    direction = "POSITIV" if positive and not negative else "NEGATIV" if negative and not positive else "OKLAR"
    return {"direction": direction, "target_changed": target and (raised or lowered),
            "recommendation_changed": upgrade or downgrade,
            "note": "Ändrad riktkurs är inte samma sak som ändrad rekommendation."}
