from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_SCORED_PATH = OUT_DIR / "posts_scored.jsonl"
POSTS_SCORED_SAMPLE_PATH = OUT_DIR / "posts_scored_sample.jsonl"
COMPANY_TOPIC_FEATURES_PATH = OUT_DIR / "company_topic_features.jsonl"
COMPANY_TOPIC_FEATURES_SAMPLE_PATH = OUT_DIR / "company_topic_features_sample.jsonl"
TOPIC_SUMMARY_PATH = OUT_DIR / "comment_topic_summary.json"
TOPIC_SUMMARY_SAMPLE_PATH = OUT_DIR / "comment_topic_summary_sample.json"
COMMENT_ESG_FEATURES_PATH = OUT_DIR / "company_comment_esg_features.jsonl"
COMMENT_ESG_FEATURES_SAMPLE_PATH = OUT_DIR / "company_comment_esg_features_sample.jsonl"
COMMENT_ESG_SUMMARY_PATH = OUT_DIR / "comment_esg_axes_summary.json"
COMMENT_ESG_SUMMARY_SAMPLE_PATH = OUT_DIR / "comment_esg_axes_summary_sample.json"

URL_RE = re.compile(r"https?://\S+")
DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|co|ai|gov|edu|biz|info|me|ca|uk|de|fr|jp|cn|ly|gg)\b(?:/\S*)?",
    re.IGNORECASE,
)
CASHTAG_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9\.\-]*")
MENTION_RE = re.compile(r"@[A-Za-z0-9_]+")
NON_WORD_RE = re.compile(r"[^a-z\s]")
MULTISPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z]{3,}")

GENERIC_TOPIC_TERMS = {
    "add", "added", "ago", "article", "articles", "better", "big", "bounce", "bought", "bull",
    "buying", "close", "com", "comment", "days", "dip", "dips", "dont", "easy", "end", "finally",
    "fuck", "fuckin", "going", "gonna", "good", "got", "great", "guess", "guys", "happened",
    "happens", "hard", "higher", "hope", "hours", "interesting", "just", "know", "let", "lets",
    "like", "linkedin", "list", "loading", "look", "looking", "looks", "love", "low", "maybe",
    "money", "month", "months", "move", "moving", "need", "net", "nice", "org", "people", "pick",
    "play", "pop", "press", "ready", "really", "release", "releases", "right", "roll", "room",
    "run", "running", "seekingalpha", "selling", "shit", "small", "sold", "soon", "squeeze",
    "started", "starting", "stocksrunner", "stocktitan", "stuff", "sure", "thing", "things",
    "thought", "time", "tipranks", "undervalued", "wait", "waiting", "want", "watchlist", "way",
    "week", "weeks", "wow", "www", "wtf", "yahoo", "alert", "signal", "stockinvest", "pivotpoint",
    "contracts", "contract", "premium", "strike", "exp", "upside", "massive", "huge", "range",
    "tight", "bit", "little", "best", "far", "forget", "miss", "don", "doesn", "didn", "goes",
    "monday", "friday", "yesterday", "today", "tomorrow", "lot", "point", "points", "continue",
    "caps", "ooc", "pre", "otc", "tsx", "investing", "weeks", "month", "months", "potential",
}
DOMAIN_HINT_TERMS = {
    "article", "articles", "com", "finance", "gov", "investors", "linkedin", "newsfilecorp", "org",
    "press", "release", "releases", "seekingalpha", "sec", "stocktitan", "stocksrunner", "tipranks",
    "www", "yahoo",
}
NOISY_TOPIC_TERMS = {
    "briefing", "mergerbrief", "newsfile", "newsfilecorp", "newswire", "otcmarkets", "otcstocks",
    "otcmarketscom", "otcqb", "otcqx", "otcpk", "quarterlyresults", "stockhouse", "thefly", "tmx",
    "tsx", "tsxv", "nfne", "ws", "globenewswire",
}
NOISY_TOPIC_PATTERNS = (
    "otcmarkets",
    "otcstocks",
    "quarterlyresults",
    "newswire",
    "mergerbrief",
    "briefing.com",
    "globenewswire",
    "newsfile",
    "stockhouse",
    "tsx",
    "tmx",
    "nfne",
)
TOPIC_DOC_STOPWORDS = set(ENGLISH_STOP_WORDS).union(
    {
        "bullish", "bearish", "market", "price", "stock", "stocks", "trade", "trading", "share",
        "shares", "today", "tomorrow", "position", "positions", "watch", "watching",
    }
)

VALUE_DIMENSION_METRIC_VERSION = "value-dimensions-v3-organic-topic-nlp"
ESG_ABSTRACTION_METRIC_VERSION = "custom-esg-v7-normative-family-summary"

ESG_LIKE_BLUEPRINTS = [
    {
        "axis_id": 0,
        "axis_code": "E",
        "axis_label": "Environmental Externalities",
        "axis_summary": "Skrot E-like zbudowany z organicznych wymiarow wartosci. To warstwa podsumowujaca, a nie glowna reprezentacja modelu.",
        "descriptor": "renewable clean energy emissions waste recycling pollution oil gas coal mining uranium decarbonization environmental carbon water efficiency extraction climate toxic spill",
        "positive_anchor": "clean energy renewable decarbonization low emission sustainable battery solar wind recycling",
        "negative_anchor": "oil gas coal pollution toxic spill drilling contamination waste refinery uranium mining",
    },
    {
        "axis_id": 1,
        "axis_code": "S",
        "axis_label": "Social Impact & Stakeholder Treatment",
        "axis_summary": "Skrot S-like oparty na komentarzowych wymiarach wartosci. Opisuje, jak komentowany jest wplyw firmy na ludzi i interesariuszy.",
        "descriptor": "patient safety workers layoffs addiction gambling tobacco community health education customer harm public benefit stakeholder treatment employment discrimination pricing care access privacy",
        "positive_anchor": "patient care worker safety education affordability community support public health privacy inclusion",
        "negative_anchor": "layoffs unsafe injury addiction gambling tobacco exploitation discrimination recall community harm",
    },
    {
        "axis_id": 2,
        "axis_code": "G",
        "axis_label": "Governance & Trust",
        "axis_summary": "Skrot G-like nad organicznymi wymiarami z komentarzy. Dotyczy zaufania, transparentnosci, zgodnosci i ryzyk typu fraud lub insider selling.",
        "descriptor": "fraud scam dilution insider selling insider buying governance trust transparency compliance disclosure pump dump manipulation accounting lawsuit sec investigation board management bribery",
        "positive_anchor": "transparent disclosure accountability board compliance trustworthy management reliable reporting insider buying",
        "negative_anchor": "fraud scam dilution insider selling manipulation accounting lawsuit sec investigation pump dump",
    },
]

VALUE_FAMILY_BLUEPRINTS = [
    {
        "family_id": "norm-governance-management",
        "label": "Zarzad i odpowiedzialnosc decyzyjna",
        "summary": "Sygnały o jakości zarządu, radzie, odpowiedzialności strategicznej i tym, czy firma wygląda na sensownie prowadzoną.",
        "descriptor": "board management ceo leadership chairman governance execution strategy accountability board vote shareholder meeting capital allocation",
        "keywords": ["management", "board", "ceo", "shareholders", "capital allocation", "leadership"],
        "axis_weights": {0: 0.05, 1: 0.10, 2: 0.85},
        "base_relevance": 0.95,
        "sort_order": 10,
    },
    {
        "family_id": "norm-disclosure-compliance",
        "label": "Transparentnosc, disclosure i compliance",
        "summary": "Komentarze o raportowaniu, filingach, komunikacji z rynkiem, zgodności i jakości ujawnień.",
        "descriptor": "disclosure filing sec accounting audit reporting transparency statement restatement compliance guidance report communication",
        "keywords": ["disclosure", "filing", "accounting", "transparency", "sec", "reporting"],
        "axis_weights": {0: 0.05, 1: 0.10, 2: 0.85},
        "base_relevance": 0.92,
        "sort_order": 20,
    },
    {
        "family_id": "norm-insider-shareholder-alignment",
        "label": "Insiderzy i zgodnosc z akcjonariuszami",
        "summary": "Wymiar o insider buying/selling, relacji z akcjonariuszami i tym, czy interes insiders i rynku wygląda na spójny.",
        "descriptor": "insider buying insider selling ownership shareholder alignment compensation activist buyback shareholder value fairness",
        "keywords": ["insider", "insider buying", "insider selling", "ceo purchased", "shareholder", "buyback"],
        "axis_weights": {0: 0.00, 1: 0.05, 2: 0.95},
        "base_relevance": 0.98,
        "sort_order": 30,
    },
    {
        "family_id": "norm-dilution-capital-engineering",
        "label": "Rozwodnienie i inzynieria kapitalowa",
        "summary": "Komentarze o dilution, reverse splitach, warrantach i innych ruchach kapitałowych, które inwestorzy odczytują jako ostrzeżenie.",
        "descriptor": "dilution reverse split offering warrant toxic debt convertible financing capital raise shelf issuance float",
        "keywords": ["dilution", "reverse split", "offering", "warrant", "convertible", "capital raise"],
        "axis_weights": {0: 0.00, 1: 0.05, 2: 0.95},
        "base_relevance": 0.99,
        "sort_order": 40,
    },
    {
        "family_id": "norm-legal-regulatory-risk",
        "label": "Ryzyko regulacyjne i spory",
        "summary": "Sygnały o lawsuitach, settlementach, dochodzeniach i innych zdarzeniach, które obciążają zaufanie do spółki.",
        "descriptor": "lawsuit settlement claim sec investigation fine bribery complaint misconduct fraud legal regulatory court",
        "keywords": ["lawsuit", "settlement", "claim", "investigation", "fraud", "regulatory"],
        "axis_weights": {0: 0.00, 1: 0.15, 2: 0.85},
        "base_relevance": 0.97,
        "sort_order": 50,
    },
    {
        "family_id": "norm-product-safety-social-utility",
        "label": "Bezpieczenstwo produktu i pozytek spoleczny",
        "summary": "Komentarze o jakości produktu, opiece, bezpieczeństwie, dostępie i tym, czy firma wnosi realną użyteczność społeczną.",
        "descriptor": "patient safety product quality medical care access education reliability utility customer trust therapy recall health",
        "keywords": ["patient safety", "quality", "care", "access", "reliability", "recall"],
        "axis_weights": {0: 0.05, 1: 0.90, 2: 0.05},
        "base_relevance": 0.92,
        "sort_order": 60,
    },
    {
        "family_id": "norm-labor-stakeholder-treatment",
        "label": "Pracownicy i interesariusze",
        "summary": "Wymiar o layoffs, warunkach pracy, bezpieczeństwie pracowników, dyskryminacji i relacji firmy z interesariuszami.",
        "descriptor": "layoffs workers labor union wages injury workplace safety employee treatment discrimination supplier community stakeholder",
        "keywords": ["layoffs", "workers", "labor", "employee", "workplace safety", "discrimination"],
        "axis_weights": {0: 0.00, 1: 0.95, 2: 0.05},
        "base_relevance": 0.95,
        "sort_order": 70,
    },
    {
        "family_id": "norm-controversial-social-harm",
        "label": "Produkty kontrowersyjne i szkoda spoleczna",
        "summary": "Komentarze o uzależnieniach, hazardzie, broni, tytoniu, alkoholu i innych obszarach, które inwestorzy czytają jako społeczną kontrowersję.",
        "descriptor": "gambling tobacco alcohol casino betting addiction opioid cannabis weapon firearms adult harm controversy backlash",
        "keywords": ["gambling", "tobacco", "alcohol", "addiction", "casino", "weapon"],
        "axis_weights": {0: 0.05, 1: 0.95, 2: 0.00},
        "base_relevance": 0.93,
        "sort_order": 80,
    },
    {
        "family_id": "norm-environmental-footprint",
        "label": "Presja srodowiskowa i wydobycie",
        "summary": "Sygnały o emisjach, wydobyciu, odpadach, wyciekach i innych środowiskowych kosztach działalności.",
        "descriptor": "pollution emissions spill waste contamination drilling mining refinery oil gas coal extraction toxic disposal",
        "keywords": ["pollution", "emissions", "mining", "gold", "silver", "waste"],
        "axis_weights": {0: 0.95, 1: 0.05, 2: 0.00},
        "base_relevance": 0.98,
        "sort_order": 90,
    },
    {
        "family_id": "norm-clean-transition",
        "label": "Transformacja i efektywnosc zasobowa",
        "summary": "Komentarze o clean energy, recyklingu, efektywności i biznesach, które inwestorzy kojarzą z bardziej zieloną transformacją.",
        "descriptor": "renewable solar wind battery recycling efficiency decarbonization clean energy water efficiency climate transition",
        "keywords": ["renewable", "solar", "wind", "battery", "recycling", "efficiency"],
        "axis_weights": {0: 0.95, 1: 0.05, 2: 0.00},
        "base_relevance": 0.90,
        "sort_order": 100,
    },
]

FAMILY_NAMING_RULES = [
    {
        "family_id": "governance-disclosure-reporting",
        "label": "Disclosure, raportowanie i zgodnosc",
        "summary": "Rodzina o ujawnieniach, filingach, raportowaniu, audycie i transparentnosci wobec rynku.",
        "descriptor": "disclosure reporting filing sec audit accounting transparency filing delayed restatement guidance form 10k 10q proxy",
        "keywords": ["disclosure", "filing", "reporting", "audit", "accounting", "transparency"],
        "exclude_tokens": {"claims", "settlement", "investors", "lawsuit", "complaint"},
        "axis_weights": {0: 0.0, 1: 0.05, 2: 0.95},
        "tokens": {"disclosure", "filing", "reporting", "audit", "accounting", "transparency", "sec", "form", "restatement"},
        "sort_order": 10,
    },
    {
        "family_id": "governance-management-insiders",
        "label": "Zarzad, insiderzy i odpowiedzialnosc",
        "summary": "Motywy o zarzadzie, insider activity, boardzie i tym, czy kierownictwo wyglada na odpowiedzialne wobec akcjonariuszy.",
        "descriptor": "insider management board ceo leadership ownership conviction director executive insider buying insider selling buyback",
        "keywords": ["insider", "management", "board", "ceo", "leadership", "buyback"],
        "exclude_tokens": {"value", "book", "yield", "dividend", "screen", "mohanram", "piotroski", "low", "high", "volume", "reversal", "mid", "chance"},
        "axis_weights": {0: 0.0, 1: 0.05, 2: 0.95},
        "tokens": {"insider", "management", "board", "ceo", "buyback", "leadership", "director", "ownership", "executive"},
        "sort_order": 20,
    },
    {
        "family_id": "governance-capital-fairness",
        "label": "Rozwodnienie, reverse splity i finansowanie",
        "summary": "Sygnaly o dilution, reverse splitach, offeringach, warrantach i agresywnym finansowaniu.",
        "descriptor": "dilution reverse split offering warrant shelf convertible financing toxic debt capital raise issuance float",
        "keywords": ["dilution", "reverse split", "offering", "warrant", "convertible", "financing"],
        "axis_weights": {0: 0.0, 1: 0.05, 2: 0.95},
        "tokens": {"dilution", "reverse", "split", "offering", "warrant", "convertible", "financing", "debt", "issuance", "capital"},
        "sort_order": 30,
    },
    {
        "family_id": "governance-legal-compliance",
        "label": "Spory, dochodzenia i compliance",
        "summary": "Tematy o lawsuitach, settlementach, dochodzeniach, fines i ryzykach regulacyjnych.",
        "descriptor": "lawsuit settlement investigation complaint fine regulatory legal sec court compliance bribery misconduct claim",
        "keywords": ["lawsuit", "settlement", "investigation", "regulatory", "legal", "compliance"],
        "axis_weights": {0: 0.0, 1: 0.10, 2: 0.90},
        "tokens": {"lawsuit", "settlement", "investigation", "regulatory", "legal", "court", "compliance", "fine", "complaint", "claim"},
        "sort_order": 40,
    },
    {
        "family_id": "governance-market-integrity",
        "label": "Fraud, manipulacja i wiarygodnosc rynku",
        "summary": "Rodzina o fraudzie, pump and dump, manipulacji, nieuczciwej komunikacji i ryzyku utraty zaufania.",
        "descriptor": "fraud scam manipulation pump dump misleading trust credibility whistleblower accounting fraud market integrity",
        "keywords": ["fraud", "scam", "manipulation", "pump", "dump", "trust"],
        "axis_weights": {0: 0.0, 1: 0.05, 2: 0.95},
        "tokens": {"fraud", "scam", "manipulation", "pump", "dump", "misleading", "trust", "credibility"},
        "sort_order": 50,
    },
    {
        "family_id": "social-product-safety",
        "label": "Produkt, bezpieczenstwo i jakosc",
        "summary": "Motywy o recallach, safety, quality, awariach produktu i zaufaniu klienta do produktu.",
        "descriptor": "product safety quality recall defect reliability customer safety dangerous failure quality issue warning",
        "keywords": ["product safety", "quality", "recall", "reliability", "customer", "defect"],
        "axis_weights": {0: 0.05, 1: 0.90, 2: 0.05},
        "tokens": {"product", "safety", "quality", "recall", "defect", "reliability", "customer", "warning"},
        "sort_order": 60,
    },
    {
        "family_id": "social-workforce-stakeholders",
        "label": "Pracownicy i interesariusze",
        "summary": "Komentarze o layoffs, warunkach pracy, pracownikach, dyskryminacji i relacjach z interesariuszami.",
        "descriptor": "layoffs workers labor employee union wages workplace injury discrimination workforce supplier strike labor safety employer",
        "keywords": ["layoffs", "workers", "labor", "employee", "union", "stakeholder"],
        "exclude_tokens": {"bank", "regional", "bonds", "staples", "reit", "deposit", "footprint", "ipo", "flow", "strike", "premium", "contracts", "unusual", "options"},
        "axis_weights": {0: 0.0, 1: 0.95, 2: 0.05},
        "tokens": {"layoffs", "workers", "labor", "employee", "union", "wages", "workplace", "injury", "discrimination", "stakeholder", "supplier", "workforce", "strike"},
        "sort_order": 70,
    },
    {
        "family_id": "social-customer-privacy-access",
        "label": "Klient, prywatnosc i dostep",
        "summary": "Rodzina o customer treatment, privacy, affordability, access i bardziej codziennym wplywie firmy na odbiorce.",
        "descriptor": "customer privacy affordability pricing service outage data breach user trust surveillance subscriber service failure complaint",
        "keywords": ["customer", "privacy", "affordability", "pricing", "data breach", "service outage"],
        "exclude_tokens": {"bonds", "staples", "reit", "rankings", "ranked", "bank", "regional"},
        "axis_weights": {0: 0.0, 1: 0.95, 2: 0.05},
        "tokens": {"customer", "privacy", "affordability", "pricing", "breach", "surveillance", "service", "subscriber", "outage", "complaint"},
        "sort_order": 80,
    },
    {
        "family_id": "social-addiction-controversy",
        "label": "Uzywki, hazard i szkoda spoleczna",
        "summary": "Kategorie o hazardzie, uzaleznieniach, tytoniu, alkoholu, opioidach i kontrowersjach spolecznych.",
        "descriptor": "gambling casino betting addiction tobacco alcohol opioid vape cannabis firearm controversial social harm",
        "keywords": ["gambling", "casino", "addiction", "tobacco", "alcohol", "opioid"],
        "axis_weights": {0: 0.05, 1: 0.95, 2: 0.0},
        "tokens": {"gambling", "casino", "betting", "addiction", "tobacco", "alcohol", "opioid", "vape", "cannabis", "harm"},
        "sort_order": 90,
    },
    {
        "family_id": "social-healthcare-impact",
        "label": "Zdrowie, terapia i opieka",
        "summary": "Motywy o patient care, terapii, skutecznosci leczenia, dostepie do opieki i ryzyku zdrowotnym produktu.",
        "descriptor": "patient therapy treatment healthcare clinical hospital disease diagnosis medical drug efficacy adverse event trial safety",
        "keywords": ["patient", "therapy", "treatment", "healthcare", "clinical", "medical"],
        "exclude_tokens": {"care", "forget", "dont", "understand", "miss", "bank", "regional"},
        "axis_weights": {0: 0.05, 1: 0.95, 2: 0.0},
        "tokens": {"patient", "therapy", "treatment", "healthcare", "clinical", "hospital", "disease", "medical", "drug", "trial", "diagnosis"},
        "sort_order": 100,
    },
    {
        "family_id": "environment-extraction-footprint",
        "label": "Wydobycie, paliwa kopalne i presja zasobowa",
        "summary": "Tematy o wydobyciu, metalach, oil and gas, drillingu i modelach biznesu obciazonych zasobowo.",
        "descriptor": "mining metals extraction oil gas coal drilling refinery uranium gold silver fossil resource footprint",
        "keywords": ["mining", "metals", "oil", "gas", "coal", "extraction"],
        "axis_weights": {0: 0.95, 1: 0.05, 2: 0.0},
        "tokens": {"mining", "metals", "oil", "gas", "coal", "drilling", "refinery", "uranium", "gold", "silver", "extraction"},
        "sort_order": 110,
    },
    {
        "family_id": "environment-emissions-waste",
        "label": "Emisje, odpady i skazenie",
        "summary": "Rodzina o pollution, emissions, waste, contamination, spillach i innych kosztach srodowiskowych.",
        "descriptor": "emissions pollution waste contamination spill toxic disposal water soil environmental cleanup leakage",
        "keywords": ["emissions", "pollution", "waste", "contamination", "spill", "toxic"],
        "axis_weights": {0: 0.95, 1: 0.05, 2: 0.0},
        "tokens": {"emissions", "pollution", "waste", "contamination", "spill", "toxic", "disposal", "water", "soil", "cleanup"},
        "sort_order": 120,
    },
    {
        "family_id": "environment-transition-efficiency",
        "label": "Transformacja, recykling i efektywnosc",
        "summary": "Motywy o renewable energy, bateriach, recyklingu, water efficiency i bardziej zielonej transformacji.",
        "descriptor": "renewable solar wind battery recycling efficiency decarbonization clean energy transition water efficiency climate",
        "keywords": ["renewable", "solar", "wind", "battery", "recycling", "efficiency"],
        "axis_weights": {0: 0.95, 1: 0.05, 2: 0.0},
        "tokens": {"renewable", "solar", "wind", "battery", "recycling", "efficiency", "decarbonization", "clean", "transition", "water", "climate"},
        "sort_order": 130,
    },
]

NON_NORMATIVE_BLUEPRINTS = [
    {
        "label": "Earnings and guidance",
        "summary": "Czysto rynkowy motyw wynikow, guidance i oczekiwan analitykow.",
        "descriptor": "earnings revenue eps guidance yoy beat miss consensus estimate quarter annual forecast",
        "keywords": ["earnings", "revenue", "eps", "guidance", "consensus"],
    },
    {
        "label": "Price action and trading setup",
        "summary": "Motyw techniczny i tradingowy bez wyraznego znaczenia normatywnego.",
        "descriptor": "breakout support resistance chart swing trade volume setup target stop momentum bounce dip",
        "keywords": ["breakout", "support", "resistance", "chart", "volume"],
    },
    {
        "label": "Dividend valuation returns",
        "summary": "Motyw wyceny, dywidendy i dochodu inwestora.",
        "descriptor": "dividend yield valuation multiple upside downside return payout re rating undervalued overvalued",
        "keywords": ["dividend", "yield", "valuation", "payout", "return"],
    },
    {
        "label": "Deal and speculative flow",
        "summary": "M and A, rumor, takeover i spekulacyjne katalizatory niebedace ESG-like same w sobie.",
        "descriptor": "deal merger acquisition rumor bid catalyst squeeze partnership speculation",
        "keywords": ["deal", "merger", "acquisition", "rumor", "squeeze"],
    },
    {
        "label": "Generic business narrative",
        "summary": "Ogolna narracja biznesowa i sektorowa bez wyraznej normatywnej tresci.",
        "descriptor": "demand growth market expansion sector technology services infrastructure opportunity business",
        "keywords": ["demand", "growth", "market", "technology", "services"],
    },
]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def normalize_text(text: str) -> str:
    lowered = text.lower()
    lowered = URL_RE.sub(" ", lowered)
    lowered = DOMAIN_RE.sub(" ", lowered)
    lowered = CASHTAG_RE.sub(" ", lowered)
    lowered = MENTION_RE.sub(" ", lowered)
    lowered = NON_WORD_RE.sub(" ", lowered)
    lowered = MULTISPACE_RE.sub(" ", lowered).strip()
    return lowered


def trim_text(text: str, limit: int = 180) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(text) if token not in TOPIC_DOC_STOPWORDS]


def percentile_scale(values: list[float], target: float) -> float:
    if not values:
        return 50.0
    sorted_values = sorted(values)
    if sorted_values[0] == sorted_values[-1]:
        return 50.0
    less_than = sum(1 for value in sorted_values if value < target)
    equal_to = sum(1 for value in sorted_values if value == target)
    percentile = (less_than + 0.5 * equal_to) / len(sorted_values)
    return max(0.0, min(100.0, 100.0 * percentile))


def normalize_positive_weights(values: list[float]) -> list[float]:
    positive = [max(0.0, float(value)) for value in values]
    total = sum(positive)
    if total <= 0:
        return [0.0 for _ in positive]
    return [value / total for value in positive]


def topic_keywords(topic: dict, limit: int = 8) -> list[str]:
    keywords: list[str] = []
    for term in topic.get("top_terms", []):
        cleaned = str(term).strip()
        if not cleaned:
            continue
        if cleaned not in keywords:
            keywords.append(cleaned)
        if len(keywords) >= limit:
            break
    return keywords


def build_topic_document(topic: dict) -> str:
    parts: list[str] = [str(topic.get("label_hint") or "")]
    parts.extend(str(term) for term in topic.get("top_terms", []))
    for example in topic.get("example_messages", [])[:3]:
        parts.append(str(example.get("snippet") or ""))
    return normalize_text(" ".join(part for part in parts if part).strip())


def term_tokens(term: str) -> list[str]:
    return tokenize(normalize_text(term))


def is_domainish(term: str) -> bool:
    lowered = term.lower().strip()
    if "." in lowered:
        return True
    tokens = term_tokens(lowered)
    return bool(tokens) and all(token in DOMAIN_HINT_TERMS for token in tokens)


def is_generic_term(term: str) -> bool:
    tokens = term_tokens(term)
    if not tokens:
        return True
    return all(token in GENERIC_TOPIC_TERMS or token in DOMAIN_HINT_TERMS for token in tokens)


def is_noise_term(term: str) -> bool:
    lowered = str(term).lower().strip()
    if not lowered:
        return True
    if any(pattern in lowered for pattern in NOISY_TOPIC_PATTERNS):
        return True
    tokens = term_tokens(lowered)
    return bool(tokens) and all(token in NOISY_TOPIC_TERMS or token in DOMAIN_HINT_TERMS for token in tokens)


def prettify_phrase(phrase: str) -> str:
    return " ".join(word.capitalize() for word in phrase.split()[:4])


def token_overlap_score(left_tokens: set[str], right_tokens: set[str]) -> float:
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    if not intersection:
        return 0.0
    return len(intersection) / min(len(left_tokens), len(right_tokens))


def build_blueprint_document(blueprint: dict) -> str:
    parts = [
        str(blueprint.get("label") or ""),
        str(blueprint.get("summary") or ""),
        str(blueprint.get("descriptor") or ""),
        *[str(item) for item in blueprint.get("keywords", [])],
        *[str(item) for item in blueprint.get("tokens", [])],
    ]
    return normalize_text(" ".join(part for part in parts if part))


def blueprint_keyword_tokens(blueprint: dict) -> set[str]:
    tokens: set[str] = set()
    for term in [blueprint["label"], *blueprint.get("keywords", [])]:
        tokens.update(term_tokens(str(term)))
    return tokens


def family_rule_tokens(rule: dict) -> set[str]:
    tokens: set[str] = set()
    for raw_value in [
        rule.get("label"),
        rule.get("summary"),
        rule.get("descriptor"),
        *list(rule.get("keywords", [])),
        *list(rule.get("tokens", [])),
    ]:
        if raw_value is None:
            continue
        for token in term_tokens(str(raw_value)):
            tokens.add(token)
    return tokens


NORMATIVE_FAMILY_TOKEN_SET = {
    token
    for rule in FAMILY_NAMING_RULES
    for token in family_rule_tokens(rule)
}


def fallback_family_label(keywords: list[str]) -> str:
    phrases = [prettify_phrase(term) for term in keywords[:3] if str(term).strip()]
    if not phrases:
        return "Komentarzowy motyw ESG-like"
    if len(phrases) == 1:
        return f"Motyw: {phrases[0]}"
    return "Motyw: " + " / ".join(phrases[:2])


def fallback_family_summary(keywords: list[str]) -> str:
    if not keywords:
        return "Organiczna rodzina tematow wartosci wydobyta z komentarzy inwestorow."
    return (
        "Organiczna rodzina tematow wartosci wydobyta z komentarzy inwestorow. "
        f"Dominujace motywy: {', '.join(keywords[:5])}."
    )


def build_topic_normative_profiles(selected_topics: list[dict]) -> dict[int, dict]:
    if not selected_topics:
        return {}

    topic_documents = [build_topic_document(topic) for topic in selected_topics]
    axis_documents: list[str] = []
    axis_slots: list[tuple[int, str]] = []
    for axis in ESG_LIKE_BLUEPRINTS:
        axis_documents.extend([axis["descriptor"], axis["positive_anchor"], axis["negative_anchor"]])
        axis_slots.extend(
            [
                (int(axis["axis_id"]), "descriptor"),
                (int(axis["axis_id"]), "positive_anchor"),
                (int(axis["axis_id"]), "negative_anchor"),
            ]
        )

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        max_df=1.0,
        max_features=8000,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(topic_documents + axis_documents)
    topic_matrix = matrix[: len(selected_topics)]
    axis_matrix = matrix[len(selected_topics) :]

    profiles: dict[int, dict] = {}
    for topic_index, topic in enumerate(selected_topics):
        similarities = cosine_similarity(topic_matrix[topic_index], axis_matrix).ravel().tolist()
        axis_strengths: list[float] = []
        axis_strength_map: dict[int, float] = {}

        for axis in ESG_LIKE_BLUEPRINTS:
            axis_id = int(axis["axis_id"])
            slot_scores = [
                max(0.0, float(similarities[position]))
                for position, slot in enumerate(axis_slots)
                if slot[0] == axis_id
            ]
            axis_strength = max(slot_scores) if slot_scores else 0.0
            axis_strengths.append(axis_strength)
            axis_strength_map[axis_id] = axis_strength

        axis_mix = normalize_positive_weights(axis_strengths)
        normative_strength = max(axis_strengths) if axis_strengths else 0.0
        profiles[int(topic["topic_id"])] = {
            "axis_weights": {
                int(axis["axis_id"]): round(axis_mix[position], 6)
                for position, axis in enumerate(ESG_LIKE_BLUEPRINTS)
            },
            "axis_strengths": {axis_id: round(value, 6) for axis_id, value in axis_strength_map.items()},
            "normative_strength": round(normative_strength, 6),
        }

    return profiles


def build_topic_family_profiles(selected_topics: list[dict]) -> dict[int, dict]:
    if not selected_topics:
        return {}

    topic_documents = [build_topic_document(topic) for topic in selected_topics]
    family_documents = [build_blueprint_document(rule) for rule in FAMILY_NAMING_RULES]
    market_documents = [build_blueprint_document(rule) for rule in NON_NORMATIVE_BLUEPRINTS]

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        max_df=1.0,
        max_features=12000,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(topic_documents + family_documents + market_documents)
    topic_matrix = matrix[: len(selected_topics)]
    family_matrix = matrix[len(selected_topics) : len(selected_topics) + len(family_documents)]
    market_matrix = matrix[len(selected_topics) + len(family_documents) :]

    family_token_lookup = {
        str(rule["family_id"]): family_rule_tokens(rule)
        for rule in FAMILY_NAMING_RULES
    }

    profiles: dict[int, dict] = {}
    for topic_index, topic in enumerate(selected_topics):
        topic_id = int(topic["topic_id"])
        topic_tokens = set(topic.get("keyword_tokens", []))
        topic_sentiment_strength = float(topic.get("sentiment_strength") or 0.0)
        topic_value_relevance = float(topic.get("value_relevance") or 0.0)

        family_similarities = cosine_similarity(topic_matrix[topic_index], family_matrix).ravel().tolist()
        market_penalty = max(
            [max(0.0, float(value)) for value in cosine_similarity(topic_matrix[topic_index], market_matrix).ravel().tolist()],
            default=0.0,
        )

        scored_families: list[dict] = []
        for family_index, rule in enumerate(FAMILY_NAMING_RULES):
            semantic_similarity = max(0.0, float(family_similarities[family_index]))
            keyword_overlap = token_overlap_score(topic_tokens, family_token_lookup[str(rule["family_id"])])
            exclude_tokens = {token for token in rule.get("exclude_tokens", set()) if str(token).strip()}
            exclude_overlap = token_overlap_score(topic_tokens, exclude_tokens)
            adjusted_score = (
                (0.72 * semantic_similarity)
                + (0.20 * keyword_overlap)
                + (0.08 * min(1.0, topic_value_relevance + (0.35 * topic_sentiment_strength)))
                - (0.48 * market_penalty)
                - (0.34 * exclude_overlap)
            )
            scored_families.append(
                {
                    "family_id": str(rule["family_id"]),
                    "family_label": str(rule["label"]),
                    "family_summary": str(rule["summary"]),
                    "family_keywords": list(rule.get("keywords") or [])[:8],
                    "family_axis_weights": {
                        int(axis["axis_id"]): round(float((rule.get("axis_weights") or {}).get(int(axis["axis_id"]), 0.0)), 6)
                        for axis in ESG_LIKE_BLUEPRINTS
                    },
                    "dominant_axis_code": max(
                        ESG_LIKE_BLUEPRINTS,
                        key=lambda axis: float((rule.get("axis_weights") or {}).get(int(axis["axis_id"]), 0.0)),
                    )["axis_code"],
                    "dominant_axis_label": max(
                        ESG_LIKE_BLUEPRINTS,
                        key=lambda axis: float((rule.get("axis_weights") or {}).get(int(axis["axis_id"]), 0.0)),
                    )["axis_label"],
                    "family_sort_order": int(rule.get("sort_order") or 999),
                    "semantic_similarity": round(semantic_similarity, 6),
                    "keyword_overlap": round(keyword_overlap, 6),
                    "exclude_overlap": round(exclude_overlap, 6),
                    "market_penalty": round(market_penalty, 6),
                    "adjusted_score": round(adjusted_score, 6),
                }
            )

        scored_families.sort(
            key=lambda item: (
                float(item["adjusted_score"]),
                float(item["semantic_similarity"]),
                float(item["keyword_overlap"]),
            ),
            reverse=True,
        )
        best_family = scored_families[0]
        profiles[topic_id] = {
            "normative_strength": round(max(0.0, float(best_family["adjusted_score"])), 6),
            "market_penalty": round(market_penalty, 6),
            "best_family": best_family,
            "scored_families": scored_families[:4],
        }

    return profiles


def infer_family_rule(keywords: list[str], topic_labels: list[str]) -> tuple[dict | None, float]:
    joined_tokens: set[str] = set()
    for term in [*keywords, *topic_labels]:
        joined_tokens.update(term_tokens(str(term)))

    best_rule: dict | None = None
    best_score = 0.0
    for rule in FAMILY_NAMING_RULES:
        rule_tokens = family_rule_tokens(rule)
        if not rule_tokens or not joined_tokens:
            continue
        overlap_count = len(joined_tokens & rule_tokens)
        overlap_ratio = overlap_count / min(len(joined_tokens), len(rule_tokens))
        score = (0.70 * overlap_count) + (0.30 * overlap_ratio)
        if score > best_score:
            best_score = score
            best_rule = rule

    if best_rule is None:
        return None, 0.0
    if best_score < 1.25:
        return None, best_score
    return best_rule, best_score


def build_topic_quality(topic: dict) -> dict:
    keywords = topic_keywords(topic, limit=10)
    keyword_tokens = [token for term in keywords for token in term_tokens(term)]
    unique_keyword_tokens = list(dict.fromkeys(keyword_tokens))
    generic_hits = sum(1 for term in keywords if is_generic_term(term))
    domain_hits = sum(1 for term in keywords if is_domainish(term))
    noise_hits = sum(1 for term in keywords if is_noise_term(term))
    phrase_hits = sum(1 for term in keywords if " " in term)
    example_messages = topic.get("example_messages", [])[:3]
    example_token_lengths = [
        len([token for token in tokenize(str(example.get("snippet") or "")) if token not in GENERIC_TOPIC_TERMS])
        for example in example_messages
    ]
    avg_example_tokens = sum(example_token_lengths) / len(example_token_lengths) if example_token_lengths else 0.0
    example_noise_ratio = (
        sum(
            1
            for example in example_messages
            if any(pattern in str(example.get("snippet") or "").lower() for pattern in NOISY_TOPIC_PATTERNS)
        )
        / max(1, len(example_messages))
    )
    support = min(1.0, math.log1p(int(topic.get("posts_with_topic") or 0)) / math.log1p(3000))
    sentiment_strength = min(1.0, abs(float(topic.get("average_sentiment") or 0.0)) * 2.5)
    generic_ratio = generic_hits / max(1, len(keywords))
    domain_ratio = domain_hits / max(1, len(keywords))
    noise_ratio = noise_hits / max(1, len(keywords))
    specificity = (
        0.38 * (1.0 - generic_ratio)
        + 0.16 * (1.0 - domain_ratio)
        + 0.16 * (1.0 - noise_ratio)
        + 0.20 * min(1.0, avg_example_tokens / 8.0)
        + 0.15 * min(1.0, phrase_hits / max(1, len(keywords)))
    )
    value_relevance = (0.52 * specificity) + (0.30 * support) + (0.18 * sentiment_strength)
    value_relevance -= 0.30 * noise_ratio
    value_relevance -= 0.15 * example_noise_ratio
    value_relevance = max(0.0, min(1.0, value_relevance))

    filtered_keywords = [term for term in keywords if not is_generic_term(term) and not is_noise_term(term)]
    if not filtered_keywords:
        filtered_keywords = [term for term in keywords if not is_generic_term(term)]
    if not filtered_keywords:
        filtered_keywords = keywords[:3]
    display_label = " / ".join(prettify_phrase(term) for term in filtered_keywords[:3]) or f"Topic {topic.get('topic_id')}"

    return {
        "topic_id": int(topic["topic_id"]),
        "keywords": filtered_keywords[:8],
        "display_label": display_label,
        "specificity": round(max(0.0, min(1.0, specificity)), 4),
        "support": round(support, 4),
        "sentiment_strength": round(sentiment_strength, 4),
        "value_relevance": round(value_relevance, 4),
        "generic_ratio": round(generic_ratio, 4),
        "domain_ratio": round(domain_ratio, 4),
        "noise_ratio": round(noise_ratio, 4),
        "unique_keyword_tokens": unique_keyword_tokens,
    }


def select_value_topics(topics: list[dict]) -> tuple[list[dict], list[dict]]:
    enriched_topics: list[dict] = []
    for topic in topics:
        quality = build_topic_quality(topic)
        enriched_topics.append(
            {
                **topic,
                "display_label": quality["display_label"],
                "keywords": quality["keywords"],
                "specificity_score": quality["specificity"],
                "support_score": quality["support"],
                "sentiment_strength": quality["sentiment_strength"],
                "value_relevance": quality["value_relevance"],
                "generic_ratio": quality["generic_ratio"],
                "domain_ratio": quality["domain_ratio"],
                "noise_ratio": quality["noise_ratio"],
                "keyword_tokens": quality["unique_keyword_tokens"],
            }
        )

    enriched_topics.sort(
        key=lambda item: (
            float(item.get("value_relevance") or 0.0),
            float(item.get("corpus_weight") or 0.0),
            int(item.get("posts_with_topic") or 0),
        ),
        reverse=True,
    )

    candidates = [
        topic
        for topic in enriched_topics
        if float(topic.get("specificity_score") or 0.0) >= 0.22
        and float(topic.get("domain_ratio") or 0.0) < 0.55
        and float(topic.get("noise_ratio") or 0.0) < 0.50
        and int(topic.get("posts_with_topic") or 0) >= 25
        and len(list(topic.get("keywords", []))) >= 3
    ]
    target_dimensions = min(len(enriched_topics), max(36, round(len(enriched_topics) * 0.80)))
    if len(candidates) < min(24, target_dimensions):
        candidates = [topic for topic in enriched_topics if float(topic.get("domain_ratio") or 0.0) < 0.75]

    selected = candidates[:target_dimensions]
    if len(selected) < min(len(enriched_topics), 24):
        seen = {int(topic["topic_id"]) for topic in selected}
        for topic in enriched_topics:
            topic_id = int(topic["topic_id"])
            if topic_id in seen:
                continue
            selected.append(topic)
            seen.add(topic_id)
            if len(selected) >= min(len(enriched_topics), 24):
                break

    seen = {int(topic["topic_id"]) for topic in selected}
    normative_backfill = [
        topic
        for topic in enriched_topics
        if int(topic["topic_id"]) not in seen
        and float(topic.get("value_relevance") or 0.0) >= 0.62
        and float(topic.get("specificity_score") or 0.0) >= 0.55
        and set(topic.get("keyword_tokens", [])) & NORMATIVE_FAMILY_TOKEN_SET
    ]
    for topic in normative_backfill[:12]:
        selected.append(topic)
        seen.add(int(topic["topic_id"]))

    selected_ids = {int(topic["topic_id"]) for topic in selected}
    discarded = [topic for topic in enriched_topics if int(topic["topic_id"]) not in selected_ids]
    return selected, discarded


def build_topic_families(selected_topics: list[dict]) -> dict[int, dict]:
    if not selected_topics:
        return {}

    family_payload_by_topic_id: dict[int, dict] = {}
    family_profiles = build_topic_family_profiles(selected_topics)
    for topic in selected_topics:
        topic_id = int(topic["topic_id"])
        profile = family_profiles.get(topic_id, {})
        best_family = profile.get("best_family")
        if not best_family:
            continue

        assignment_score = float(best_family.get("adjusted_score") or 0.0)
        semantic_similarity = float(best_family.get("semantic_similarity") or 0.0)
        keyword_overlap = float(best_family.get("keyword_overlap") or 0.0)
        market_penalty = float(best_family.get("market_penalty") or 0.0)
        if assignment_score < 0.11:
            continue
        if semantic_similarity < 0.10 and keyword_overlap < 0.08:
            continue
        if market_penalty > semantic_similarity + keyword_overlap + 0.08:
            continue

        family_payload_by_topic_id[topic_id] = {
            "family_id": best_family["family_id"],
            "family_label": best_family["family_label"],
            "family_keywords": list(best_family.get("family_keywords") or [])[:8],
            "family_summary": best_family["family_summary"],
            "family_axis_weights": dict(best_family.get("family_axis_weights") or {}),
            "dominant_axis_code": best_family.get("dominant_axis_code"),
            "dominant_axis_label": best_family.get("dominant_axis_label"),
            "family_base_relevance": round(max(0.0, assignment_score), 4),
            "family_sort_order": int(best_family.get("family_sort_order") or 999),
            "family_assignment_score": round(max(0.0, assignment_score), 4),
            "family_semantic_similarity": round(semantic_similarity, 4),
            "family_keyword_overlap": round(keyword_overlap, 4),
        }

    return family_payload_by_topic_id


def build_value_dimension_catalog(selected_topics: list[dict], family_lookup: dict[int, dict]) -> list[dict]:
    catalog = []
    for topic in selected_topics:
        topic_id = int(topic["topic_id"])
        family = family_lookup.get(topic_id, {})
        examples = [
            str(example.get("snippet") or "").strip()
            for example in topic.get("example_messages", [])[:3]
            if str(example.get("snippet") or "").strip()
        ]
        keywords = list(topic.get("keywords") or topic_keywords(topic))
        catalog.append(
            {
                "axis_id": topic_id,
                "axis_label": str(topic.get("display_label") or topic.get("label_hint") or f"Topic {topic_id}"),
                "axis_display_label": str(topic.get("display_label") or topic.get("label_hint") or f"Topic {topic_id}"),
                "axis_summary": "Organiczny wymiar wartosci odkryty z komentarzy inwestorow. Glowne motywy: " + ", ".join(keywords[:5]) + ".",
                "axis_family_id": family.get("family_id"),
                "axis_family_label": family.get("family_label"),
                "axis_family_summary": family.get("family_summary"),
                "axis_family_dominant_axis_code": family.get("dominant_axis_code"),
                "axis_family_dominant_axis_label": family.get("dominant_axis_label"),
                "family_assignment_score": round(float(family.get("family_assignment_score") or 0.0), 4) if family else 0.0,
                "axis_family_axis_weights": dict(family.get("family_axis_weights") or {}) if family else {},
                "axis_family_base_relevance": round(float(family.get("family_base_relevance") or 0.0), 4) if family else 0.0,
                "axis_family_sort_order": int(family.get("family_sort_order") or 999) if family else 999,
                "keywords": keywords[:8],
                "topic_labels": [str(topic.get("label_hint") or f"Topic {topic_id}")],
                "examples": examples[:3],
                "topic_count": 1,
                "corpus_weight": round(float(topic.get("corpus_weight") or 0.0), 4),
                "average_sentiment": round(float(topic.get("average_sentiment") or 0.0), 4),
                "value_relevance": round(float(topic.get("value_relevance") or 0.0), 4),
                "specificity_score": round(float(topic.get("specificity_score") or 0.0), 4),
            }
        )
    return sorted(catalog, key=lambda item: int(item["axis_id"]))


def build_family_catalog(
    dimension_catalog: list[dict],
    selected_topics: list[dict],
) -> list[dict]:
    if not dimension_catalog:
        return []

    topic_lookup = {int(topic["topic_id"]): topic for topic in selected_topics}
    family_buckets: dict[str, list[dict]] = defaultdict(list)
    for dimension in dimension_catalog:
        family_id = str(dimension.get("axis_family_id") or "").strip()
        if not family_id:
            continue
        family_buckets[family_id].append(dimension)

    family_rows: list[dict] = []
    for family_id, dimensions in family_buckets.items():
        sorted_dimensions = sorted(
            dimensions,
            key=lambda item: (
                float(item.get("value_relevance") or 0.0),
                float(item.get("corpus_weight") or 0.0),
            ),
            reverse=True,
        )
        family_label = str(sorted_dimensions[0].get("axis_family_label") or sorted_dimensions[0].get("axis_label") or family_id)

        keywords: list[str] = []
        examples: list[str] = []
        topic_labels: list[str] = []
        member_axis_ids: list[int] = []
        weighted_relevance_sum = 0.0
        weighted_assignment_sum = 0.0
        weight_sum = 0.0
        family_summary = str(sorted_dimensions[0].get("axis_family_summary") or sorted_dimensions[0].get("axis_summary") or "")
        family_assignment_scores: list[float] = []
        family_sort_order = 999
        family_axis_weights = {}
        family_base_relevance = 0.0

        for dimension in sorted_dimensions:
            axis_id = int(dimension["axis_id"])
            member_axis_ids.append(axis_id)
            topic = topic_lookup.get(axis_id, {})
            dimension_weight = max(
                0.20,
                float(dimension.get("value_relevance") or 0.0)
                + min(1.0, float(dimension.get("corpus_weight") or 0.0) / 2000.0),
            )
            weighted_relevance_sum += float(dimension.get("value_relevance") or 0.0) * dimension_weight
            weighted_assignment_sum += float(dimension.get("family_assignment_score") or 0.0) * dimension_weight
            weight_sum += dimension_weight
            family_assignment_scores.append(float(dimension.get("family_assignment_score") or 0.0))

            for keyword in list(dimension.get("keywords") or [])[:6]:
                if keyword and keyword not in keywords:
                    keywords.append(str(keyword))
                if len(keywords) >= 10:
                    break

            for topic_label in list(dimension.get("topic_labels") or [])[:2]:
                if topic_label and topic_label not in topic_labels:
                    topic_labels.append(str(topic_label))
                if len(topic_labels) >= 8:
                    break

            source_examples = list(dimension.get("examples") or topic.get("example_messages") or [])
            for example in source_examples[:3]:
                snippet = str(example.get("snippet") if isinstance(example, dict) else example).strip()
                if snippet and snippet not in examples:
                    examples.append(snippet)
                if len(examples) >= 4:
                    break

            family_axis_weights = family_axis_weights or dict((dimension.get("axis_family_axis_weights") or {}))
            family_base_relevance = max(family_base_relevance, float(dimension.get("axis_family_base_relevance") or 0.0))
            family_sort_order = min(family_sort_order, int(dimension.get("axis_family_sort_order") or 999))

        family_rows.append(
            {
                "family_id": family_id,
                "family_label": family_label,
                "family_summary": family_summary or f"Komentarzowa rodzina ESG-like. Najczestsze motywy: {', '.join(keywords[:5])}.",
                "keywords": keywords[:10],
                "examples": examples[:4],
                "topic_labels": topic_labels[:8],
                "member_axis_ids": member_axis_ids,
                "member_dimensions_count": len(member_axis_ids),
                "average_value_relevance": round((weighted_relevance_sum / weight_sum) if weight_sum > 0 else 0.0, 4),
                "average_assignment_score": round((weighted_assignment_sum / weight_sum) if weight_sum > 0 else 0.0, 4),
                "family_sort_order": family_sort_order,
                "family_base_relevance": round(family_base_relevance, 4),
                "family_axis_weights_seed": {
                    str(axis_id): round(float(weight), 6)
                    for axis_id, weight in (family_axis_weights or {}).items()
                },
            }
        )

    catalog: list[dict] = []
    for row in family_rows:
        seed_weights = row.get("family_axis_weights_seed") or {}
        combined_mix = normalize_positive_weights(
            [
                float(seed_weights.get(str(axis["axis_id"]), 0.0))
                for axis in ESG_LIKE_BLUEPRINTS
            ]
        )
        esg_relevance = min(
            1.0,
            (0.50 * float(row["family_base_relevance"]))
            + (0.30 * float(row["average_value_relevance"]))
            + (0.20 * float(row["average_assignment_score"])),
        )
        dominant_axis_position = max(range(len(combined_mix)), key=lambda position: combined_mix[position], default=0)
        dominant_axis = ESG_LIKE_BLUEPRINTS[dominant_axis_position]
        catalog.append(
            {
                "family_id": row["family_id"],
                "family_label": row["family_label"],
                "family_summary": row["family_summary"],
                "keywords": row["keywords"],
                "examples": row["examples"],
                "topic_labels": row["topic_labels"],
                "member_axis_ids": row["member_axis_ids"],
                "member_dimensions_count": row["member_dimensions_count"],
                "average_value_relevance": row["average_value_relevance"],
                "average_assignment_score": row["average_assignment_score"],
                "esg_relevance": round(esg_relevance, 4),
                "esg_axis_weights": {
                    str(axis["axis_id"]): round(combined_mix[position], 6)
                    for position, axis in enumerate(ESG_LIKE_BLUEPRINTS)
                },
                "dominant_axis_code": dominant_axis["axis_code"],
                "dominant_axis_label": dominant_axis["axis_label"],
                "sort_order": row["family_sort_order"],
            }
        )

    catalog.sort(
        key=lambda item: (
            int(item.get("sort_order") or 999),
            -float(item.get("esg_relevance") or 0.0),
            -float(item.get("average_value_relevance") or 0.0),
            -int(item.get("member_dimensions_count") or 0),
        ),
    )
    return catalog


def build_dimension_scores(company_rows: list[dict], dimension_catalog: list[dict]) -> tuple[dict[str, list[dict]], dict[int, list[float]]]:
    raw_values_by_dimension: dict[int, list[float]] = defaultdict(list)
    company_dimensions: dict[str, list[dict]] = {}
    catalog_by_id = {int(item["axis_id"]): item for item in dimension_catalog}

    for row in company_rows:
        symbol = str(row.get("symbol") or "").upper()
        payload: list[dict] = []
        for topic_payload in list(row.get("topics", [])):
            topic_id = int(topic_payload.get("topic_id", -1))
            if topic_id not in catalog_by_id:
                continue
            axis_definition = catalog_by_id[topic_id]
            raw_score = float(topic_payload.get("signed_topic_score") or 0.0)
            raw_values_by_dimension[topic_id].append(raw_score)
            payload.append(
                {
                    "axis_id": topic_id,
                    "axis_label": axis_definition["axis_label"],
                    "axis_summary": axis_definition["axis_summary"],
                    "axis_family_id": axis_definition.get("axis_family_id"),
                    "axis_family_label": axis_definition.get("axis_family_label"),
                    "axis_keywords": axis_definition["keywords"],
                    "axis_examples": axis_definition["examples"][:2],
                    "axis_raw_score": raw_score,
                    "axis_exposure": float(topic_payload.get("topic_share") or 0.0),
                    "axis_posts_count": int(topic_payload.get("posts_with_topic") or 0),
                    "axis_avg_sentiment": float(topic_payload.get("avg_sentiment") or 0.0),
                }
            )
        company_dimensions[symbol] = payload

    for symbol, payload in company_dimensions.items():
        normalized_payload = []
        for item in payload:
            axis_id = int(item["axis_id"])
            percentile = percentile_scale(raw_values_by_dimension[axis_id], item["axis_raw_score"])
            exposure = float(item["axis_exposure"] or 0.0)
            posts_count = int(item["axis_posts_count"] or 0)
            confidence = min(1.0, math.log1p(posts_count) / math.log1p(15)) * min(1.0, 0.20 + (0.80 * min(1.0, exposure * 3.5)))
            axis_score = 50.0 + confidence * (percentile - 50.0)
            normalized_payload.append(
                {
                    "axis_id": axis_id,
                    "axis_label": item["axis_label"],
                    "axis_summary": item["axis_summary"],
                    "axis_family_id": item["axis_family_id"],
                    "axis_family_label": item["axis_family_label"],
                    "axis_score": round(axis_score, 2),
                    "axis_raw_score": round(item["axis_raw_score"], 4),
                    "axis_exposure": round(exposure, 4),
                    "axis_confidence": round(confidence, 4),
                    "axis_posts_count": posts_count,
                    "axis_keywords": item["axis_keywords"],
                    "axis_examples": item["axis_examples"],
                    "axis_avg_sentiment": round(item["axis_avg_sentiment"], 4),
                }
            )
        normalized_payload.sort(key=lambda item: item["axis_exposure"], reverse=True)
        company_dimensions[symbol] = normalized_payload

    return company_dimensions, raw_values_by_dimension


def build_family_scores(
    company_dimensions: dict[str, list[dict]],
    family_catalog: list[dict],
) -> tuple[dict[str, list[dict]], dict[str, list[float]]]:
    family_catalog_by_id = {str(item["family_id"]): item for item in family_catalog}
    raw_values_by_family: dict[str, list[float]] = defaultdict(list)
    company_families: dict[str, list[dict]] = {}

    for symbol, dimensions in company_dimensions.items():
        family_buckets: dict[str, dict] = {}
        for dimension in dimensions:
            family_id = str(dimension.get("axis_family_id") or f"value-family-axis-{dimension['axis_id']}")
            family_definition = family_catalog_by_id.get(family_id)
            if family_definition is None:
                continue

            bucket = family_buckets.setdefault(
                family_id,
                {
                    "family_id": family_id,
                    "family_label": family_definition["family_label"],
                    "family_summary": family_definition["family_summary"],
                    "dominant_axis_code": family_definition.get("dominant_axis_code"),
                    "dominant_axis_label": family_definition.get("dominant_axis_label"),
                    "family_keywords": family_definition["keywords"],
                    "family_examples": family_definition["examples"],
                    "family_esg_relevance": float(family_definition.get("esg_relevance") or 0.0),
                    "family_esg_axis_weights": dict(family_definition.get("esg_axis_weights") or {}),
                    "weighted_raw_sum": 0.0,
                    "signal_weight_sum": 0.0,
                    "family_exposure": 0.0,
                    "family_posts_count": 0,
                    "member_dimensions": [],
                },
            )

            exposure = float(dimension.get("axis_exposure") or 0.0)
            confidence = float(dimension.get("axis_confidence") or 0.0)
            signal_weight = max(0.03, exposure) * (0.25 + (0.75 * confidence))
            raw_score = float(dimension.get("axis_raw_score") or 0.0)
            bucket["weighted_raw_sum"] += raw_score * signal_weight
            bucket["signal_weight_sum"] += signal_weight
            bucket["family_exposure"] += exposure
            bucket["family_posts_count"] += int(dimension.get("axis_posts_count") or 0)
            bucket["member_dimensions"].append(
                {
                    "axis_id": int(dimension["axis_id"]),
                    "axis_label": str(dimension["axis_label"]),
                    "axis_score": float(dimension["axis_score"]),
                    "axis_raw_score": raw_score,
                    "axis_exposure": exposure,
                    "axis_confidence": confidence,
                }
            )

        family_payload: list[dict] = []
        for family_id, bucket in family_buckets.items():
            signal_weight_sum = float(bucket["signal_weight_sum"])
            family_raw_score = (float(bucket["weighted_raw_sum"]) / signal_weight_sum) if signal_weight_sum > 0 else 0.0
            raw_values_by_family[family_id].append(family_raw_score)
            family_payload.append(
                {
                    "family_id": family_id,
                    "family_label": bucket["family_label"],
                    "family_summary": bucket["family_summary"],
                    "dominant_axis_code": bucket.get("dominant_axis_code"),
                    "dominant_axis_label": bucket.get("dominant_axis_label"),
                    "family_keywords": bucket["family_keywords"],
                    "family_examples": bucket["family_examples"],
                    "family_raw_score": family_raw_score,
                    "family_exposure": min(1.0, float(bucket["family_exposure"])),
                    "family_posts_count": int(bucket["family_posts_count"]),
                    "family_dimension_count": len(bucket["member_dimensions"]),
                    "family_esg_relevance": bucket["family_esg_relevance"],
                    "family_esg_axis_weights": bucket["family_esg_axis_weights"],
                    "family_member_dimensions": sorted(
                        bucket["member_dimensions"],
                        key=lambda item: (item["axis_exposure"], abs(item["axis_raw_score"])),
                        reverse=True,
                    )[:8],
                }
            )
        company_families[symbol] = family_payload

    for symbol, family_payload in company_families.items():
        normalized_payload = []
        for item in family_payload:
            percentile = percentile_scale(raw_values_by_family[item["family_id"]], float(item["family_raw_score"]))
            evidence_units = int(item["family_dimension_count"]) + min(int(item["family_posts_count"]), 24)
            exposure = float(item["family_exposure"])
            confidence = min(1.0, math.log1p(evidence_units) / math.log1p(28)) * min(
                1.0,
                0.20 + (0.80 * min(1.0, exposure * 1.8)),
            )
            family_score = 50.0 + confidence * (percentile - 50.0)
            normalized_payload.append(
                {
                    "family_id": item["family_id"],
                    "family_label": item["family_label"],
                    "family_summary": item["family_summary"],
                    "dominant_axis_code": item.get("dominant_axis_code"),
                    "dominant_axis_label": item.get("dominant_axis_label"),
                    "family_score": round(family_score, 2),
                    "family_raw_score": round(float(item["family_raw_score"]), 4),
                    "family_exposure": round(exposure, 4),
                    "family_confidence": round(confidence, 4),
                    "family_posts_count": int(item["family_posts_count"]),
                    "family_dimension_count": int(item["family_dimension_count"]),
                    "family_keywords": item["family_keywords"],
                    "family_examples": item["family_examples"][:3],
                    "family_esg_relevance": round(float(item["family_esg_relevance"]), 4),
                    "family_esg_axis_weights": item["family_esg_axis_weights"],
                    "family_member_dimensions": item["family_member_dimensions"],
                }
            )
        normalized_payload.sort(
            key=lambda item: (
                float(item.get("family_esg_relevance") or 0.0),
                float(item.get("family_exposure") or 0.0),
                float(item.get("family_confidence") or 0.0),
            ),
            reverse=True,
        )
        company_families[symbol] = normalized_payload

    return company_families, raw_values_by_family


def build_esg_like_membership(selected_topics: list[dict]) -> dict[int, dict[int, float]]:
    topic_documents = [build_topic_document(topic) for topic in selected_topics]
    corpus = topic_documents + [axis["descriptor"] for axis in ESG_LIKE_BLUEPRINTS]
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        max_df=1.0,
        max_features=8000,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(corpus)
    topic_matrix = matrix[: len(selected_topics)]
    axis_matrix = matrix[len(selected_topics) :]

    membership: dict[int, dict[int, float]] = {}
    for index, topic in enumerate(selected_topics):
        similarities = cosine_similarity(topic_matrix[index], axis_matrix).ravel().tolist()
        positive = [max(0.0, float(value)) for value in similarities]
        total = sum(positive)
        weights = [0.0 for _ in positive] if total <= 0 else [value / total for value in positive]
        membership[int(topic["topic_id"])] = {
            axis["axis_id"]: round(weights[position], 6)
            for position, axis in enumerate(ESG_LIKE_BLUEPRINTS)
        }
    return membership


def build_direct_esg_comment_cache(posts_rows: list[dict]) -> dict[str, dict[int, dict]]:
    comments: list[dict] = []
    for row in posts_rows:
        cleaned = normalize_text(str(row.get("text") or ""))
        tokens = tokenize(cleaned)
        if len(tokens) < 4:
            continue
        comments.append(
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "cleaned": " ".join(tokens),
                "sentiment_score": float(row.get("sentiment_score") or 0.0),
                "snippet": trim_text(str(row.get("text") or "")),
            }
        )

    if len(comments) < 200:
        return {}

    anchor_texts = []
    for axis in ESG_LIKE_BLUEPRINTS:
        anchor_texts.append(axis["positive_anchor"])
        anchor_texts.append(axis["negative_anchor"])

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        max_features=12000,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform([item["cleaned"] for item in comments] + anchor_texts)
    comment_matrix = matrix[: len(comments)]
    anchor_matrix = matrix[len(comments) :]

    buckets: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {"signal_sum": 0.0, "weight_sum": 0.0, "comments_count": 0, "examples": []}))
    for index, comment in enumerate(comments):
        similarities = cosine_similarity(comment_matrix[index], anchor_matrix).ravel().tolist()
        for axis_position, axis in enumerate(ESG_LIKE_BLUEPRINTS):
            positive_similarity = float(similarities[axis_position * 2])
            negative_similarity = float(similarities[(axis_position * 2) + 1])
            semantic_signal = positive_similarity - negative_similarity
            semantic_strength = positive_similarity + negative_similarity
            if semantic_strength < 0.02:
                continue

            blended_signal = (0.70 * semantic_signal) + (0.30 * float(comment["sentiment_score"]))
            bucket = buckets[comment["symbol"]][int(axis["axis_id"])]
            bucket["signal_sum"] += blended_signal * semantic_strength
            bucket["weight_sum"] += semantic_strength
            bucket["comments_count"] += 1
            if len(bucket["examples"]) < 4 and comment["snippet"] not in bucket["examples"]:
                bucket["examples"].append(comment["snippet"])

    return buckets


def build_esg_like_scores(
    company_families: dict[str, list[dict]],
    family_catalog: list[dict],
    posts_rows: list[dict],
) -> tuple[dict[str, list[dict]], dict[int, list[float]], dict[int, list[dict]]]:
    direct_cache = build_direct_esg_comment_cache(posts_rows)
    raw_values_by_axis: dict[int, list[float]] = defaultdict(list)
    company_axes: dict[str, list[dict]] = {}
    axis_family_catalog: dict[int, list[dict]] = defaultdict(list)

    for family in family_catalog:
        family_id = str(family["family_id"])
        family_relevance = float(family.get("esg_relevance") or 0.0)
        for axis in ESG_LIKE_BLUEPRINTS:
            axis_id = axis["axis_id"]
            axis_weight = float((family.get("esg_axis_weights") or {}).get(str(axis_id), 0.0))
            effective_weight = axis_weight * family_relevance
            if effective_weight < 0.04:
                continue
            axis_family_catalog[axis_id].append(
                {
                    "family_id": family_id,
                    "label": str(family.get("family_label") or family_id),
                    "axis_weight": effective_weight,
                    "esg_relevance": family_relevance,
                    "keywords": list(family.get("keywords") or [])[:6],
                    "examples": list(family.get("examples") or [])[:2],
                    "member_dimensions_count": int(family.get("member_dimensions_count") or 0),
                }
            )

    for axis_id, rows in axis_family_catalog.items():
        rows.sort(
            key=lambda item: (
                item["axis_weight"],
                item["esg_relevance"],
                item["member_dimensions_count"],
            ),
            reverse=True,
        )
        axis_family_catalog[axis_id] = rows[:12]

    for symbol, families in company_families.items():
        axes_payload: list[dict] = []
        for axis in ESG_LIKE_BLUEPRINTS:
            axis_id = axis["axis_id"]
            weighted_score_sum = 0.0
            weight_sum = 0.0
            exposure_sum = 0.0
            family_drivers: list[dict] = []

            for family in families:
                axis_weight = float((family.get("family_esg_axis_weights") or {}).get(str(axis_id), 0.0))
                family_relevance = float(family.get("family_esg_relevance") or 0.0)
                effective_weight = axis_weight * family_relevance
                if effective_weight < 0.04:
                    continue
                raw_score = float(family["family_raw_score"])
                exposure = float(family["family_exposure"])
                weighted_score_sum += raw_score * effective_weight
                weight_sum += effective_weight
                exposure_sum += exposure * effective_weight
                family_drivers.append(
                    {
                        "family_id": family["family_id"],
                        "label": family["family_label"],
                        "axis_weight": round(effective_weight, 4),
                        "family_score": float(family["family_score"]),
                        "family_raw_score": raw_score,
                        "family_confidence": float(family.get("family_confidence") or 0.0),
                    }
                )

            family_raw_score = weighted_score_sum / weight_sum if weight_sum > 0 else 0.0
            direct_bucket = direct_cache.get(symbol, {}).get(axis_id, {})
            direct_raw_score = (
                float(direct_bucket.get("signal_sum", 0.0)) / float(direct_bucket.get("weight_sum", 1.0))
                if float(direct_bucket.get("weight_sum", 0.0)) > 0
                else 0.0
            )
            family_strength = min(1.0, exposure_sum * 2.8)
            direct_strength = min(1.0, float(direct_bucket.get("weight_sum", 0.0)) * 2.5)
            total_strength = family_strength + direct_strength
            combined_raw_score = (
                ((family_raw_score * family_strength) + (direct_raw_score * direct_strength)) / total_strength
                if total_strength > 0
                else 0.0
            )

            axes_payload.append(
                {
                    "axis_id": axis_id,
                    "axis_label": axis["axis_label"],
                    "axis_summary": axis["axis_summary"],
                    "axis_raw_score": combined_raw_score,
                    "axis_exposure": exposure_sum + float(direct_bucket.get("weight_sum", 0.0)),
                    "axis_comments_count": int(direct_bucket.get("comments_count", 0)),
                    "axis_family_drivers": sorted(family_drivers, key=lambda item: abs(item["family_raw_score"]) * item["axis_weight"], reverse=True)[:8],
                    "axis_examples": list(direct_bucket.get("examples", []))[:4],
                }
            )
            raw_values_by_axis[axis_id].append(combined_raw_score)
        company_axes[symbol] = axes_payload

    normalized_company_axes: dict[str, list[dict]] = {}
    for symbol, axes_payload in company_axes.items():
        normalized_axes = []
        for axis_payload in axes_payload:
            axis_id = int(axis_payload["axis_id"])
            percentile = percentile_scale(raw_values_by_axis[axis_id], float(axis_payload["axis_raw_score"]))
            signal_units = len(axis_payload["axis_family_drivers"]) + int(axis_payload["axis_comments_count"])
            exposure = float(axis_payload["axis_exposure"])
            confidence = min(1.0, math.log1p(signal_units) / math.log1p(18)) * min(1.0, 0.20 + (0.80 * min(1.0, exposure * 2.5)))
            axis_score = 50.0 + confidence * (percentile - 50.0)
            normalized_axes.append(
                {
                    "axis_id": axis_id,
                    "axis_label": axis_payload["axis_label"],
                    "axis_summary": axis_payload["axis_summary"],
                    "axis_score": round(axis_score, 2),
                    "axis_raw_score": round(float(axis_payload["axis_raw_score"]), 4),
                    "axis_exposure": round(exposure, 4),
                    "axis_confidence": round(confidence, 4),
                    "axis_examples": axis_payload["axis_examples"],
                    "axis_family_drivers": axis_payload["axis_family_drivers"],
                }
            )
        normalized_company_axes[symbol] = normalized_axes

    return normalized_company_axes, raw_values_by_axis, axis_family_catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--posts-file", type=str, default=None)
    parser.add_argument("--company-topics-file", type=str, default=None)
    parser.add_argument("--topic-summary-file", type=str, default=None)
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    ensure_dir(OUT_DIR)
    posts_path = Path(args.posts_file) if args.posts_file else (POSTS_SCORED_SAMPLE_PATH if args.sample else POSTS_SCORED_PATH)
    company_topics_path = Path(args.company_topics_file) if args.company_topics_file else (
        COMPANY_TOPIC_FEATURES_SAMPLE_PATH if args.sample else COMPANY_TOPIC_FEATURES_PATH
    )
    topic_summary_path = Path(args.topic_summary_file) if args.topic_summary_file else (
        TOPIC_SUMMARY_SAMPLE_PATH if args.sample else TOPIC_SUMMARY_PATH
    )
    output_path = COMMENT_ESG_FEATURES_SAMPLE_PATH if args.sample else COMMENT_ESG_FEATURES_PATH
    summary_path = COMMENT_ESG_SUMMARY_SAMPLE_PATH if args.sample else COMMENT_ESG_SUMMARY_PATH

    if not posts_path.exists():
        raise FileNotFoundError(f"Brak pliku z postami: {posts_path}")
    if not company_topics_path.exists():
        raise FileNotFoundError(f"Brak pliku z cechami topicznymi spolek: {company_topics_path}")
    if not topic_summary_path.exists():
        raise FileNotFoundError(f"Brak podsumowania topicow: {topic_summary_path}")

    posts_rows = load_jsonl(posts_path)
    company_rows = load_jsonl(company_topics_path)
    topic_summary = load_json(topic_summary_path)
    topics = list(topic_summary.get("topics", []))

    if len(company_rows) < 25 or len(topics) < 10:
        raise RuntimeError("Za malo danych do zbudowania wymiarow wartosci z komentarzy.")

    selected_topics, discarded_topics = select_value_topics(topics)
    family_lookup = build_topic_families(selected_topics)
    dimension_catalog = build_value_dimension_catalog(selected_topics, family_lookup)
    family_catalog = build_family_catalog(dimension_catalog, selected_topics)
    company_dimensions, _raw_values_by_dimension = build_dimension_scores(company_rows, dimension_catalog)
    company_families, _raw_values_by_family = build_family_scores(company_dimensions, family_catalog)
    company_summary_axes, _raw_values_by_axis, axis_family_catalog = build_esg_like_scores(company_families, family_catalog, posts_rows)

    output_rows = []
    with output_path.open("w", encoding="utf-8") as handle:
        for row in sorted(company_rows, key=lambda item: str(item.get("symbol") or "")):
            symbol = str(row.get("symbol") or "").upper()
            dimensions = company_dimensions.get(symbol, [])
            summary_axes = company_summary_axes.get(symbol, [])
            summary_axis_scores = [float(axis["axis_score"]) for axis in summary_axes]
            custom_esg_proxy_score = round(sum(summary_axis_scores) / len(summary_axis_scores), 2) if summary_axis_scores else 50.0
            custom_esg_confidence = round(sum(float(axis["axis_confidence"]) for axis in summary_axes) / len(summary_axes), 4) if summary_axes else 0.0
            output_row = {
                "symbol": symbol,
                "company_name": row.get("company_name") or symbol,
                "category": row.get("category") or "Unknown",
                "posts_count": row.get("posts_count", 0),
                "custom_esg_axes": dimensions,
                "custom_esg_families": company_families.get(symbol, []),
                "custom_esg_summary_axes": summary_axes,
                "custom_esg_proxy_score": custom_esg_proxy_score,
                "custom_esg_confidence": custom_esg_confidence,
                "custom_esg_metric_version": ESG_ABSTRACTION_METRIC_VERSION,
                "custom_value_dimensions_metric_version": VALUE_DIMENSION_METRIC_VERSION,
            }
            handle.write(json.dumps(output_row, ensure_ascii=False) + "\n")
            output_rows.append(output_row)

    esg_like_axes_summary = []
    for axis in ESG_LIKE_BLUEPRINTS:
        axis_id = axis["axis_id"]
        families_for_axis = axis_family_catalog.get(axis_id, [])
        keywords: list[str] = []
        examples: list[str] = []
        family_labels: list[str] = []
        family_ids: list[str] = []
        family_weights: list[float] = []
        for family in families_for_axis:
            family_ids.append(str(family["family_id"]))
            family_labels.append(str(family["label"]))
            family_weights.append(round(float(family["axis_weight"]), 4))
            for keyword in family["keywords"]:
                if keyword not in keywords:
                    keywords.append(keyword)
                if len(keywords) >= 8:
                    break
            for example in family["examples"]:
                if example and example not in examples:
                    examples.append(example)
                if len(examples) >= 4:
                    break

        esg_like_axes_summary.append(
            {
                "axis_id": axis_id,
                "axis_label": axis["axis_label"],
                "axis_display_label": axis["axis_label"],
                "axis_summary": axis["axis_summary"],
                "axis_code": axis["axis_code"],
                "keywords": keywords[:8],
                "examples": examples[:4],
                "family_ids": family_ids,
                "family_labels": family_labels,
                "topic_labels": family_labels,
                "family_weights": family_weights,
                "topic_count": len(family_ids),
            }
        )

    summary = {
        "input_posts_file": str(posts_path),
        "input_company_topics_file": str(company_topics_path),
        "input_topic_summary_file": str(topic_summary_path),
        "output_company_esg_file": str(output_path),
        "companies_scored": len(output_rows),
        "raw_topics_count": len(topics),
        "dimensions_count": len(dimension_catalog),
        "families": family_catalog,
        "family_count": len(family_catalog),
        "axes": dimension_catalog,
        "esg_like_axes": esg_like_axes_summary,
        "discarded_topics_count": len(discarded_topics),
        "discarded_topics_preview": [
            {
                "topic_id": int(item["topic_id"]),
                "label": str(item.get("display_label") or item.get("label_hint") or f"Topic {item['topic_id']}"),
                "keywords": list(item.get("keywords", []))[:6],
                "value_relevance": round(float(item.get("value_relevance") or 0.0), 4),
                "specificity_score": round(float(item.get("specificity_score") or 0.0), 4),
                "domain_ratio": round(float(item.get("domain_ratio") or 0.0), 4),
            }
            for item in discarded_topics[:12]
        ],
        "metric_version": ESG_ABSTRACTION_METRIC_VERSION,
        "value_dimensions_metric_version": VALUE_DIMENSION_METRIC_VERSION,
        "projection_method": "organic-topic-dimensions-first-then-esg-like-summary",
        "is_sample": args.sample,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
