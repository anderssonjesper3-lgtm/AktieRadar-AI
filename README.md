# AktieRadar AI – Saab B v0.2

En webbaserad Streamlit-prototyp som översätter användarens **Saab B Momentum Scanner v1** från Pine Script v6 till Python.

## Vad den gör
- EMA 9/21, Wilder RSI 14, MACD 12/26/9 och volym-SMA 20.
- Bullish engulfing, hammer, 15-minuterstrend och poängsystemet 0–100.
- VAKTA-händelser och KÖP på avslutade femminutersstaplar.
- Graf och export av signaler.
- Syntetisk demodata, eller valfri CSV med femminuterskurser.

## Starta lokalt
Installera Python (helst 3.10+) och kör i projektmappen:

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

## Publicera som webbsida
Lägg `app.py`, `scanner.py` och `requirements.txt` i ett privat eller publikt GitHub-repo. Skapa sedan en app på Streamlit Community Cloud och välj `app.py` som startfil. Publicering och kostnader beror på tjänstens aktuella villkor. Ladda inte upp privata kontouppgifter eller känsliga CSV-filer i ett publikt repo.

## CSV-format
```csv
timestamp,open,high,low,close,volume
2026-11-12 09:00:00,100.0,100.2,99.8,100.1,5000
2026-11-12 09:05:00,100.1,100.5,100.0,100.4,7200
```

Använd verkliga **5-minuters OHLCV-staplar**, där `timestamp` är stapelns **starttid** i svensk lokal börstid. Behåll minst några dagars historik för indikatoruppvärmning. Ladda bara upp avslutade staplar för att jämföra signalerna med TradingView. Marknadsdata och rättigheter måste kontrolleras separat.

## Viktiga begränsningar
Ingen realtidskälla, ingen Avanza-inloggning, ingen orderläggning och inga historiska vinst-/förlustberäkningar. Syntetiska kurser och signaler är enbart test. TradingViews exakta indikatorstartvärden och sessionsregler kan ge små skillnader; jämför mot Pine innan användning. VAKTA kan intrabar fladdra i TradingView; den här versionen beräknar endast avslutade staplar.
