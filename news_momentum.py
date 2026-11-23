"""News-triggered momentum confirmation using only observed delayed candles.

A candidate is informational, never an executable quote or order.
"""
from datetime import datetime, timedelta, timezone
from news_analysis import analyze_news

NEWS_WINDOW_HOURS = 8
MAX_BAR_AGE_MINUTES = 20
MIN_CONFIRMATION_BARS = 2
MIN_MOVE_PCT = 0.7
MAX_CHASE_PCT = 5.0

def evaluate_news_momentum(company, articles, candles, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not candles:
        return {"kind": "DATA SAKNAS", "reason": "Inga observerade kursljus", "news": None}
    relevant = []
    for article in articles:
        if article.get("company") != company.get("name"):
            continue
        published = article.get("published")
        if isinstance(published, str):
            try:
                published = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                continue
        if not isinstance(published, datetime) or published.tzinfo is None:
            continue
        age = now - published
        if not timedelta(0) <= age <= timedelta(hours=NEWS_WINDOW_HOURS):
            continue
        analysis = analyze_news(article, company)
        relevant.append((published, article, analysis))
    if not relevant:
        return {"kind": "AVVAKTA", "reason": "Ingen färsk bolagsnyhet", "news": None}
    published, article, analysis = max(relevant, key=lambda row: row[0])
    base = {"news": article, "analysis": analysis, "published": published.isoformat(),
            "checked_at": now.isoformat(), "kind": "NYHET-VAKTA"}
    if analysis["view"] not in ("POSITIV", "PRELIMINÄRT POSITIV"):
        return dict(base, reason="Nyheten är inte verifierat positiv")
    bars = sorted(candles, key=lambda c: c["time"])
    def bar_end(c):
        return c.get("last_trade_time") or (c["time"] + timedelta(minutes=5))
    after = [c for c in bars if bar_end(c) >= published]
    before = [c for c in bars if bar_end(c) < published]
    if not before or len(after) < MIN_CONFIRMATION_BARS:
        return dict(base, reason="Väntar på kursljus efter nyheten")
    last = after[-1]
    end = bar_end(last)
    age_minutes = (now - end).total_seconds() / 60
    if not 0 <= age_minutes <= MAX_BAR_AGE_MINUTES:
        return dict(base, reason="Kursdata är äldre än 20 minuter", age_minutes=round(age_minutes, 1))
    reference = float(before[-1]["close"])
    close = float(last["close"])
    if reference <= 0:
        return dict(base, reason="Ogiltig referenskurs")
    move = (close / reference - 1) * 100
    recent = after[-MIN_CONFIRMATION_BARS:]
    rising = all(float(c["close"]) > float(c["open"]) for c in recent) and float(recent[-1]["close"]) > float(recent[0]["close"])
    prior_volumes = [float(c["volume"]) for c in (before[-10:] + after[:-1]) if isinstance(c.get("volume"), (int,float)) and c["volume"] > 0]
    volume_ok = len(prior_volumes) >= 3 and isinstance(last.get("volume"), (int,float)) and float(last["volume"]) >= sum(prior_volumes)/len(prior_volumes)*1.2
    base.update(move_pct=round(move, 2), age_minutes=round(age_minutes, 1),
                volume_confirmed=bool(volume_ok), rising=bool(rising),
                last_bar_time=end.isoformat())
    if move > MAX_CHASE_PCT:
        return dict(base, reason="Rörelsen är redan kraftig – jaga inte kursen")
    if move >= MIN_MOVE_PCT and rising and volume_ok:
        return dict(base, kind="KÖP-KANDIDAT", reason="Positiv nyhet bekräftad av stigande observerade ljus och volym; fördröjd kurs – kontrollera Avanza")
    return dict(base, reason="Nyhet identifierad; inväntar fortsatt momentum och volym")
