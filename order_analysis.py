"""Order significance calculations: confirmed values only; no inferred revenue."""
import re

def order_ratio(order_sek, annual_revenue_sek):
    if order_sek is None or annual_revenue_sek is None or annual_revenue_sek <= 0 or order_sek < 0:
        return None
    return round(100 * order_sek / annual_revenue_sek, 2)

def parse_order_amount(text):
    """Conservative Swedish SEK amount extraction; ambiguous currencies are ignored."""
    pattern = r'(?<!\w)(\d+(?:[,.]\d+)?)\s*(miljoner|miljon|mkr|miljarder|miljard|mdkr)\s*(?:sek|kronor|kr)?\b'
    matches = re.findall(pattern, text.casefold())
    if len(matches) != 1:
        return None
    value, unit = matches[0]
    amount = float(value.replace(',', '.'))
    multiplier = 1_000_000_000 if unit.startswith('miljard') or unit == 'mdkr' else 1_000_000
    return round(amount * multiplier)
