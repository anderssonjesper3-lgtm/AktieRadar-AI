# Avanza SSE – experimentell datakoppling

Denna modul är **inte aktiverad i produktionsappen**. Den är en separat brygga för att testa en autentiserad Avanza-session med det **inofficiella** CLI-verktyget [avanza-ts](https://antewall.github.io/avanza-ts/docs/cli/live-data/).

## Test på en säker separat maskin
1. Installera och autentisera avanza-ts enligt dess egen dokumentation. Kontrollera Avanzas villkor innan användning. Lägg aldrig lösenord, BankID-uppgifter, sessionskakor eller TOTP-hemligheter i GitHub.
2. Verifiera instrumentets Avanza orderbook-ID oberoende.
3. Kör `python avanza_stream_bridge.py --orderbook-ids <VERIFIERAT_ID>` på en maskin som kan hålla en process igång.
4. Programmet skriver råa mottagna händelser till `avanza_quotes.ndjson`, med källa och mottagningstid.

## Viktiga begränsningar
- Att ett meddelande tas emot nu innebär **inte** att börskursen är ofördröjd. `realtime_verified` och `latency_verified` är alltid false tills källans tidsstämpel och rättigheter har verifierats separat.
- Börsstängning, illikvid handel och tyst SSE-ström är inte automatiskt fel.
- Appens befintliga signaler och 0/10-status påverkas inte av detta experiment.
- En persistent server och säker sessionshantering behövs innan produktion. GitHub Actions är inte avsett som permanent SSE-server.
- NDJSON-filen är lokal och får inte checkas in; ordna säker transport och lagring före integration.
- Ingen orderläggning eller åtkomst till konton ingår.
