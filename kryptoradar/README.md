# KryptoRadar – separat experiment

KryptoRadar är en nyhetsfri momentum- och volymradar för BTC/USD, ETH/USD och SOL/USD med offentliga OHLC-data från Kraken. Ingen API-nyckel behövs för läsning.

## Starta

```bash
pip install -r kryptoradar/requirements.txt
streamlit run kryptoradar/app.py
```

Vid Streamlit Cloud: välj `kryptoradar/app.py` som main file och grenen `kryptoradar-v1`. Det skapar en separat app och ändrar inte befintlig AktieRadar-deployment.

## Strategi
Endast stängda enminutersljus. EMA9 > EMA21, stigande kurs, 10-ljusutbrott, volym >= 1,5 gånger föregående 20 ljus och RSI 52–75 ger KÖP-KANDIDAT. Svag EMA/RSI ger SÄLJ/VARNING. Övrigt VAKTA/AVVAKTA. Detta är experimentella regler, inte verifierat lönsamma signaler.

## Begränsningar
- Endast Krakens handelsplats, inte hela kryptomarknadens volym.
- HTTP-pollning ungefär en gång per minut, inte ett WebSocket-flöde; ingen garanterad exekveringslatens.
- Fiktiva affärer med avgift och slippage, aldrig riktiga order.
- Journalen är lokal och inte beständig på alla molnplattformar.
- Utvärdera med backtest och forward-test före någon riktig handel.
