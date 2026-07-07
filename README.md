# Magisterka

Repozytorium pracy **"Inzynieria selekcji wartosci w inwestowaniu poza normami ESG"**.

Aplikacja odkrywa oddolne osie wartosci z komentarzy inwestorow (StockTwits),
laczy je z fundamentami i technikaliami spolek i buduje z tego selekcje
ETF-opodobna. Warstwa po warstwie: scraper, potok analizy (BERTopic, model
jezykowy jako ekstraktor jakosciowy, ablacja dwoch modeli), API FastAPI,
frontend React.

## Dane i tryb demo

Repozytorium **nie zawiera** realnych danych ze StockTwits ani z yfinance ze
wzgledu na ich pochodzenie (scraping i serwisy finansowe). Zamiast nich w
`demo/` sa male, w pelni syntetyczne fikstury: fikcyjne spolki
(`DEMO01`..`DEMO10`), bez realnych nazw i bez cytatow z komentarzy, o schemacie
identycznym z realnym. Backend uzywa `demo/` automatycznie, gdy nie ma wynikow
potoku w `analiza/out/`, wiec po `git clone` aplikacja odpala sie i daje sie
pokazac od reki, na danych demo.

Zeby uruchomic na realnych danych, wygeneruj je lokalnie: scrapery w
`scrapper/` buduja universe i korpus, a ponumerowany potok w `analiza/` tworzy
`analiza/out/company_master_dataset.jsonl`. Realne dane pozostaja lokalne i nie
sa publikowane (zob. `.gitignore`).

## Struktura

- `scrapper/`
  Zachowana warstwa pozyskania danych do pracy. Ten katalog pozostaje czescia dokumentacji i implementacji mgr.
- `analiza/`
  Miejsce na skrypty budujace finalny zbior analityczny, komentarzowe ESG, odkrywanie osi z tematow komentarzy, scoring i agregacje, w tym lokalny import fundamentow do rentownosci.
- `backend/`
  API FastAPI dla logiki selekcji, rankingu i budowy portfela ETF-opodobnego.
- `frontend/`
  Aplikacja React pozwalajaca uzytkownikowi skonfigurowac profil wartosci i zobaczyc wynik selekcji.
- `docs/`
  Dokumentacja architektury, modelu domenowego i decyzji projektowych.

## Aktualny stan

- `scrapper/` zawiera dzialajacy pipeline do pozyskania danych z CompaniesMarketCap i StockTwits.
- `analiza/` buduje `company_master_dataset`, odkrywa globalne tematy komentarzy i wylicza autorski `custom_esg_proxy_score` na bazie standaryzowanych osi komentarzowego ESG.
- `analiza/input/` sluzy jako lokalny punkt wejscia dla danych fundamentalnych i technicznych w CSV.
- `analiza/input/raw/` sluzy jako lokalny zrzut surowych eksportow CSV z serwisow finansowych przed normalizacja.
- backend wystawia katalog kategorii, odkrytych osi komentarzowego ESG, presety aksjologiczne, preview portfela i eksport raportu `.md/.json`.
- backend wystawia tez status danych, worklisty brakujacych fundamentals/technicals oraz endpointy do importu surowych CSV.
- backend utrzymuje lokalna biblioteke zapisanych profili uzytkownika w `backend/data/custom_profiles.json`.
- frontend pozwala wybrac preset, ustawic wagi, sterowac osiami komentarzowego ESG, przegladac ich rodziny semantyczne i przyklady komentarzy, kontrolowac dywersyfikacje, zapisywac wlasne profile, generowac ETF-opodobny preview oraz wgrywac CSV z fundamentals/technicals.
- scraper nie jest usuwany ani upraszczany "na sile" - pozostaje artefaktem pracy i warstwa danych.

## Docelowy przeplyw

1. `scrapper/` buduje universe spolek i korpus postow.
2. `analiza/` wylicza cechy spoleczne, eksportuje workliste do fundamentow, normalizuje surowe eksporty finansowe i techniczne oraz dolacza rentownosc i technikalia.
3. `backend/` laczy cechy ze zdefiniowanym profilem wartosci, presetami, osiami komentarzowego ESG, wagami scoringu i ograniczeniami dywersyfikacji.
4. `frontend/` udostepnia konfiguracje, eksploracje osi i wynik koncowy jako aplikacje webowa.

## Szybki start

### Najprostszy start na Windows

Z katalogu glownego projektu:

```powershell
cd path\to\magister
.\start_app.ps1
```

Potem otworz:

```text
http://127.0.0.1:8000
```

Jesli port `8000` jest zajety, uruchom na innym porcie:

```powershell
.\start_app.ps1 -Port 8010
```

albo pozwol skryptowi samemu znalezc wolny port:

```powershell
.\start_app.ps1 -AutoPort
```

Jesli chcesz zatrzymac aplikacje:

```powershell
.\stop_app.ps1
```

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Szybki smoke test backendu:

```bash
python backend/scripts/smoke_test_api.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend domyslnie zaklada API pod `http://localhost:8000/api/v1`. Dla czytelnego lokalnego setupu skopiuj [frontend/.env.example](frontend/.env.example) do `.env` i w razie potrzeby zmien `VITE_API_BASE`.

Build produkcyjny:

```bash
cd frontend
npm run build
```

Po zbudowaniu frontendu backend umie serwowac gotowa aplikacje bez osobnego serwera Vite, bezposrednio z:

```text
http://127.0.0.1:8000
```
