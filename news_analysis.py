"""Deterministic, auditable first-pass news analysis. Not an LLM."""
from datetime import datetime, timezone
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
    if negative and len(negative) >= len(positive):
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
