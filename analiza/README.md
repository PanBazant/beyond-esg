# Analiza

Katalog `analiza/` buduje warstwe interpretacyjna i decyzyjna nad danymi zebranymi w `scrapper/`.

## Kolejnosc

1. `python 01_flatten_stocktwits_messages.py`
2. `python 02_build_social_features.py`
3. `python 10_discover_comment_topics.py`
4. `python 11_build_comment_derived_esg.py`
5. `python 06_export_fundamentals_worklist.py`
6. `python 05_import_fundamentals_raw.py --input-file analiza/input/raw/<twoj_eksport>.csv`
7. `python 04_build_profitability_features.py`
8. `python 08_import_technicals_raw.py --input-file analiza/input/raw/<twoj_eksport_techniczny>.csv`
9. `python 07_build_technical_features.py`
10. `python 12_import_esg_benchmark_csv.py --input-file analiza/input/raw/<twoj_eksport_esg>.csv --source-name RealEsgProvider --as-of-date 2026-04-11`
11. `python 03_build_company_master_dataset.py`
12. `python 09_generate_portfolio_report.py --preset-id balanced_signal`

Etap `05` sluzy do normalizacji surowego eksportu finansowego do pliku `analiza/input/company_fundamentals.csv`.
Etap `04` liczy `profitability_score` na podstawie znormalizowanego CSV. Jesli nie ma jeszcze pliku `analiza/input/company_fundamentals.csv`, skrypt wygeneruje szablon `analiza/input/company_fundamentals_template.csv`.
Etap `08` sluzy do normalizacji surowego eksportu technicznego do pliku `analiza/input/company_technicals.csv`.
Etap `07` liczy `technical_score` na podstawie znormalizowanego CSV. Jesli nie ma jeszcze pliku `analiza/input/company_technicals.csv`, skrypt wygeneruje szablon `analiza/input/company_technicals_template.csv`.

## Tryb walidacyjny

Kazdy etap moze byc uruchomiony na ograniczonej probce:

```bash
python 01_flatten_stocktwits_messages.py --limit-symbols 25
python 02_build_social_features.py --input-file analiza/out/posts_flat_sample.jsonl --limit-posts 5000 --sample
python 10_discover_comment_topics.py --input-file analiza/out/posts_scored.jsonl --limit-posts 8000 --sample
python 11_build_comment_derived_esg.py --company-topics-file analiza/out/company_topic_features_sample.jsonl --topic-summary-file analiza/out/comment_topic_summary_sample.json --sample
python 06_export_fundamentals_worklist.py --min-posts 30 --limit 100 --only-missing
python 05_import_fundamentals_raw.py --input-file analiza/input/raw/fundamentals_export.csv --source-name ManualExport --as-of-date 2026-04-10
python 04_build_profitability_features.py --input-file analiza/input/company_fundamentals.csv --limit-rows 50 --sample
python 08_import_technicals_raw.py --input-file analiza/input/raw/technicals_export.csv --source-name ManualTechnicalExport --as-of-date 2026-04-10
python 07_build_technical_features.py --input-file analiza/input/company_technicals.csv --limit-rows 50 --sample
python 12_import_esg_benchmark_csv.py --input-file analiza/input/raw/esg_export.csv --source-name RealEsgProvider --as-of-date 2026-04-11
python 03_build_company_master_dataset.py --social-features-file analiza/out/company_social_features_sample.jsonl --comment-esg-file analiza/out/company_comment_esg_features_sample.jsonl --profitability-features-file analiza/out/company_profitability_features_sample.jsonl --technical-features-file analiza/out/company_technical_features_sample.jsonl --real-esg-features-file analiza/out/company_real_esg_benchmark.jsonl --sample
python 09_generate_portfolio_report.py --preset-id balanced_signal --output-name balanced-signal-report
```

## Wyjscia

Pliki trafiaja do `analiza/out/`.
Pelny run zapisuje `posts_flat.jsonl`, `company_social_features.jsonl`, `comment_topic_summary.json`, `company_comment_esg_features.jsonl`, `company_profitability_features.jsonl`, `company_technical_features.jsonl`, `company_real_esg_benchmark.jsonl` i `company_master_dataset.jsonl`.
Tryb walidacyjny zapisuje osobne pliki z sufiksem `_sample`.

## Komentarzowe wymiary wartosci i ESG-like

- `10_discover_comment_topics.py` odkrywa globalne tematy komentarzy przez `TF-IDF + NMF`, mocniej usuwa boilerplate i domenowy szum oraz zapisuje tematy i agregacje per spolka.
- `11_build_comment_derived_esg.py` buduje z tych tematow kilkadziesiat organicznych wymiarow wartosci, a dopiero potem streszcza je do warstwy `ESG-like`.
- Finalny `custom_esg_proxy_score` w master datasecie jest skrotem nad wieloma wymiarami komentarzowymi, a nie z gory narzuconym modelem 3 osi.
- `comment_esg_axes_summary.json` jest katalogiem wymiarow dla backendu i frontendu: zawiera etykiety, rodziny, slowa-klucze, przyklady i metadane jakosci.

## Benchmark real ESG

- `12_import_esg_benchmark_csv.py` importuje zewnetrzny benchmark prawdziwego ESG do `analiza/out/company_real_esg_benchmark.jsonl`.
- Jesli nie masz jeszcze eksportu, uruchom `python 12_import_esg_benchmark_csv.py --write-template`.
- Finalny master dataset przechowuje wtedy rownolegle:
  - komentarzowy `custom_esg_proxy_score`
  - zewnetrzny `real_esg_total_score`
  - skladniki `environment/social/governance`
  - `source` oraz `as_of_date`

## Import fundamentow

- `analiza/input/raw/`:
  miejsce na surowe eksporty CSV z zewnetrznych serwisow
- `analiza/input/company_fundamentals.csv`:
  znormalizowany plik roboczy uzywany przez pipeline
- `analiza/input/company_fundamentals_template.csv`:
  pelny szablon uniwersum spolek
- `analiza/input/company_technicals.csv`:
  znormalizowany plik roboczy dla metryk technicznych
- `analiza/input/company_technicals_template.csv`:
  pelny szablon uniwersum spolek dla metryk technicznych
- `analiza/input/fundamentals_worklist.csv`:
  lista spolek, dla ktorych warto zebrac fundamenty w pierwszej kolejnosci

Importer `05_import_fundamentals_raw.py` probuje automatycznie wykryc kolumny typu `Ticker`, `Net Income Margin %`, `Return on Equity`, `Revenue Growth %` itd. i zmapowac je do docelowego CSV.
Importer `08_import_technicals_raw.py` probuje automatycznie wykryc kolumny typu `Ticker`, `Change 1M %`, `Change 3M %`, `Volatility 30D`, `Drawdown 90D` itd. i zmapowac je do docelowego CSV.

Ta sama sciezka jest teraz dostepna rowniez przez aplikacje webowa: backend potrafi przyjac surowy CSV, zapisac go do `analiza/input/raw/uploads/`, uruchomic importer, przebudowac cechy i odswiezyc `company_master_dataset`.

## Raport Portfela

Skrypt `09_generate_portfolio_report.py` generuje:
- raport `Markdown` do pracy lub notatek
- pelny zrzut `JSON` z parametrami, warningami, holdings i summary

Przyklady:

```bash
python 09_generate_portfolio_report.py --preset-id balanced_signal
python 09_generate_portfolio_report.py --preset-id anti_esg_contrarian --output-name anti-esg-report
python 09_generate_portfolio_report.py --preset-id balanced_signal --profile-file analiza/profiles/anti_esg_diversified.json --output-name anti-esg-diversified
```
