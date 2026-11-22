# AktieRadar AI 6.0 – utvecklingsversion

AktieRadar AI är ett analys- och bevakningsverktyg för svenska aktier. Det visar indikativa VAKTA- och KÖP-KANDIDAT-signaler baserade på verifierade Avanza-kurser. Verktyget lägger **inga riktiga order** och signaler är inte investeringsråd.

## Funktioner
- Översikt för tio konfigurerade aktier med femminutersstaplar.
- EMA 9/21, RSI 14, MACD och candlestick-/volymanalys.
- Kontroll av instrument-ID, kompletta staplar, datakvalitet och handelstid.
- Nyhetsmodul som bara klassificerar nyheter från uttryckligen konfigurerade HTTPS RSS/Atom-flöden. Utan verifierade flöden visas nyhetsstatus som ej ansluten/okänd; den får inte tolkas som att inga risknyheter finns.
- Telegramnotiser med dubblettskydd och historikreserv före utskick.
- Simulerad signaljournal: 5 000 kr per affär, mål +2 %, stop -1 %, courtage 0,25 % (minst 1 kr) och slippage 0,10 % per sida. Journalen är pappershandel, inte backtest eller faktisk portföljhistorik.

## Starta
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Tester
```bash
python -m pytest -q
python -m compileall -q .
```
GitHub Actions kör tester, kompilering och release-audit på grenen `aktieradar-6.0`.

## Viktiga driftkrav före live
1. Verifiera varje Avanza-ID och att data är aktuell under ordinarie handelstid. Ett lyckat API-anrop bevisar inte i sig realtidsdata.
2. Konfigurera och provkör officiella/auktoriserade nyhetsflöden för respektive bolag. Nuvarande watchlist saknar verifierade RSS/Atom-URL:er; inga feed-adresser ska gissas.
3. Kör Telegram-test, därefter dry-run och kontrollera Secrets samt signalhistorik innan live-läge.
4. Signaljournalen skrivs till `signal_journal.json` på appens filsystem. Den filen kan försvinna vid omstart/omdeploy på ephemerala värdar. Exportera CSV eller anslut beständig lagring innan den används som långsiktig statistik.
5. Bekräfta börskalender, courtage, slippage och signalernas beteende med historiska data och i skuggläge. Simulerade affärer är förenklade: mål/stop avgörs av senast hämtade färdiga femminutersstängning och kan inte modellera intrabar ordningsföljd.
6. Ingen automatisk orderläggning ingår.

## Konfiguration av nyhetsflöden
Redigera `news_watchlist.json`. Lägg bara till HTTPS RSS/Atom-adresser som har verifierats mot bolagets officiella investerar-/pressida eller annan uttryckligen godkänd källa. Alias ska vara bolagsspecifika för att minska felmatchningar.

## Säkerhet
Lägg aldrig in Avanza-inloggning, Telegram-token eller andra hemligheter i koden. Använd GitHub Secrets/variabler där så krävs. Behåll produktionens 5.0-gren orörd tills utvecklingsversionen är verifierad.
