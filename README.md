# AktieRadar News AI – pilot

Nyhetsdriven Streamlit-prototyp för Nasdaq Stockholm Mid Cap och Small Cap. Inga automatiska order.

## Starta lokalt

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Funktioner
- `news_watchlist.json`: bolag, segmentverifiering och konfigurerade nyhetskällor. Endast verifierade segment aktiveras.
- `news_scanner.py`: nyhetsinsamling, tidsfilter, källdiagnostik och dubblettfilter.
- `news_ai_pilot.py`: regelbaserad katalysatorbedömning, ekonomisk motivering, risk och villkorade köpkandidater. Kursfel blockerar inte nyhetsbedömningen.
- `multi_engine.py`: återanvänd kursmotor; kursdata hämtas för relevanta kandidater och öppna simulerade positioner.
- `app.py`: nyhetskort, källkontroll och experimentell sessionsjournal.

## Begränsningar före publicering

Bolagslistan är inte fullständig. Källornas faktiska täckning och användningsvillkor måste verifieras. Regelpoäng är inte sannolikheter och analysen omfattar inte nödvändigtvis hela pressmeddelandet. Kursdata kan vara fördröjd; köp kräver kursobservation efter publicering och högst 20 minuters ålder. Simulerade resultat är inte exekverbara priser. Smart Exit har riskstopp och följer uppgångar över 2 procent utan fast vinsthemtagning. Journalen är sessionsbaserad, inte permanent. Automatisk bakgrundsbevakning och Telegram är ännu inte anslutna till piloten.

## Test och driftsättning

Kör `python -m pytest` lokalt; äldre tester kan fortfarande finnas i grenen. Kontrollera pilotens GitHub Actions-resultat separat. För Streamlit Community Cloud ska pilotgrenen `news-ai-pilot` och startfilen `app.py` väljas. Detta dokument bekräftar inte att en driftsättning har genomförts. Publicera inga autentiseringsuppgifter eller privata data. Äldre scannerjobb måste avvecklas separat vid övergången.
