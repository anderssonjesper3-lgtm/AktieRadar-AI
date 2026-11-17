import requests

url = "https://www.avanza.se/_api/market-guide/stock/"

print("AktieRadar AI – testar Avanza")

try:
    response = requests.get(url, timeout=10)

    print("HTTP-status:", response.status_code)

    if response.ok:
        print("Kontakt med servern lyckades!")
        print("Svarstyp:", response.headers.get("Content-Type"))
    else:
        print("Servern svarade, men anropet godkändes inte.")

except requests.RequestException as error:
    print("Kunde inte ansluta:", error)
