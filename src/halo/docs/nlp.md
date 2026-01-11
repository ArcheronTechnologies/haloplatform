# Halo NLP Documentation

## Overview

The Halo NLP module provides Swedish-specific text analysis capabilities:

- **Named Entity Recognition (NER)** - Extract people, organizations, locations, and Swedish identifiers
- **Sentiment Analysis** - Detect fear, violence, and threat indicators
- **Threat Vocabulary Detection** - Identify criminal slang, gang terminology, and financial crime indicators
- **Swedish Tokenization** - Handle compound words and Swedish-specific text patterns

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      NLP Pipeline                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Input Text                                                     │
│       │                                                          │
│       ▼                                                          │
│   ┌──────────────────┐                                          │
│   │ SwedishTokenizer │  Tokenize, decompound Swedish words      │
│   └────────┬─────────┘                                          │
│            │                                                     │
│            ▼                                                     │
│   ┌──────────────────┐                                          │
│   │ NamedEntity      │  KB-BERT + pattern matching              │
│   │ Recognizer       │  Extract PER, ORG, LOC, identifiers      │
│   └────────┬─────────┘                                          │
│            │                                                     │
│            ▼                                                     │
│   ┌──────────────────┐                                          │
│   │ SentimentAnalyzer│  Detect fear, violence, threats          │
│   └────────┬─────────┘                                          │
│            │                                                     │
│            ▼                                                     │
│   ┌──────────────────┐                                          │
│   │ ThreatVocabulary │  Criminal slang, gang terms, AML         │
│   │ Detector         │  indicators                              │
│   └────────┬─────────┘                                          │
│            │                                                     │
│            ▼                                                     │
│   ┌──────────────────┐                                          │
│   │    NLPResult     │  Combined analysis results               │
│   └──────────────────┘                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Components

### NLPPipeline

The main entry point for text analysis.

```python
from halo.nlp import NLPPipeline

pipeline = NLPPipeline()
result = await pipeline.analyze("Han heter Johan Andersson och jobbar på IKEA.")

print(result.entities)  # [Entity(text="Johan Andersson", label="PER", ...)]
print(result.sentiment)  # SentimentResult(polarity=0.0, fear_score=0.0, ...)
print(result.threat_matches)  # []
```

#### NLPResult

```python
@dataclass
class NLPResult:
    text: str                      # Original text
    language: str                  # Detected language (default: "sv")
    entities: list[Entity]         # Extracted entities
    sentiment: SentimentResult     # Sentiment analysis
    threat_matches: list[VocabMatch]  # Threat vocabulary matches
    summary: Optional[str]         # AI-generated summary (if enabled)
    tokens: list[str]              # Tokenized text
    processing_time_ms: float      # Analysis time
```

---

### Named Entity Recognition

Extracts entities using KB-BERT and pattern matching.

```python
from halo.nlp import NamedEntityRecognizer

ner = NamedEntityRecognizer()
entities = ner.extract("Ring 08-123 456 78 eller maila info@example.com")

# Returns:
# [
#   Entity(text="08-123 456 78", label="PHONE", start=5, end=18),
#   Entity(text="info@example.com", label="EMAIL", start=32, end=48)
# ]
```

#### Supported Entity Types

| Label | Description | Detection Method |
|-------|-------------|------------------|
| `PER` | Person names | KB-BERT NER |
| `ORG` | Organizations | KB-BERT NER |
| `LOC` | Locations | KB-BERT NER |
| `PERSONNUMMER` | Swedish personal ID | Regex + validation |
| `ORGNR` | Swedish org number | Regex + validation |
| `PHONE` | Phone numbers | Regex |
| `EMAIL` | Email addresses | Regex |
| `MONEY` | Monetary amounts | Regex |

#### Entity Object

```python
@dataclass
class Entity:
    text: str           # The extracted text
    label: str          # Entity type (PER, ORG, etc.)
    start: int          # Start character position
    end: int            # End character position
    confidence: float   # Detection confidence (0-1)
    normalized: str     # Normalized form (e.g., cleaned personnummer)
    metadata: dict      # Additional information
```

#### Swedish Identifier Validation

Extracted personnummer and organisationsnummer are validated:

```python
# Personnummer validation includes:
# - Luhn checksum verification
# - Date validation (birth date must be valid)
# - Format normalization (YYYYMMDD-XXXX)

# Organisationsnummer validation includes:
# - Luhn checksum verification
# - Company type prefix validation
# - Format normalization
```

---

### Sentiment Analysis

Analyzes text for concerning emotional indicators.

```python
from halo.nlp import SentimentAnalyzer

analyzer = SentimentAnalyzer()
result = analyzer.analyze("Jag är rädd och känner mig hotad")

print(result.fear_score)      # 0.8
print(result.threat_score)    # 0.6
print(result.is_concerning)   # True
```

#### SentimentResult

```python
@dataclass
class SentimentResult:
    polarity: float         # Overall sentiment (-1 to 1)
    fear_score: float       # Fear indicators (0-1)
    violence_score: float   # Violence indicators (0-1)
    urgency_score: float    # Urgency/pressure (0-1)
    threat_score: float     # Threat language (0-1)
    risk_score: float       # Aggregate risk (0-1)
    detected_keywords: list[str]  # Matched keywords

    @property
    def is_concerning(self) -> bool:
        return fear_score > 0.5 or violence_score > 0.5 or threat_score > 0.5
```

#### Keyword Categories

**Fear Keywords:**
- rädd, rädsla, skräck, orolig, ångest, panik, hotad, farlig, desperat, hjälp...

**Violence Keywords:**
- slå, mörda, döda, skjuta, kniv, vapen, blod, våld, attack, misshandel...

**Urgency Keywords:**
- snabbt, nu, omedelbart, bråttom, deadline, måste, genast...

---

### Threat Vocabulary Detection

Detects criminal and threat-related terminology.

```python
from halo.nlp import ThreatVocabularyDetector

detector = ThreatVocabularyDetector()
matches = detector.detect("Vi ska fixa bransen med lite grönt")

# Returns:
# [
#   VocabMatch(keyword="bransen", category="gang", severity="high"),
#   VocabMatch(keyword="grönt", category="drugs", severity="medium")
# ]
```

#### VocabMatch

```python
@dataclass
class VocabMatch:
    keyword: str      # Matched term
    category: str     # Category (gang, drugs, fraud, etc.)
    start: int        # Start position
    end: int          # End position
    context: str      # Surrounding text
    severity: str     # low, medium, high
```

#### Vocabulary Categories

| Category | Description | Examples |
|----------|-------------|----------|
| `gang` | Gang-related terms | gäng, bransen, brödraskapet |
| `drugs` | Drug terminology | knark, grönt, ladd, langare |
| `weapons` | Weapons | vapen, skjutvapen, kniv |
| `violence` | Violence terms | slå, mörda, hämnd |
| `money_laundering` | AML indicators | tvätta, svarta pengar, målvakt |
| `fraud` | Fraud indicators | bluff, bedräger, fake |
| `rinkebysvenska` | Suburb slang | gansen, para, wallah |

#### Rinkebysvenska Support

The detector includes Swedish urban slang (Rinkebysvenska/förortssvenska):

```python
# Examples of detected slang:
# - "gansen" (police)
# - "para" (money)
# - "shansen" (chance/opportunity)
# - "habibi" (friend, Arabic origin)
# - "wallah" (I swear, Arabic origin)
```

---

### Swedish Tokenizer

Handles Swedish-specific tokenization.

```python
from halo.nlp import SwedishTokenizer

tokenizer = SwedishTokenizer()
tokens = tokenizer.tokenize("Försäkringsbolaget AB kontaktade mig.")

# Returns: ["Försäkringsbolaget", "AB", "kontaktade", "mig", "."]

# With decompounding:
decompounded = tokenizer.decompound("sjukvårdsförsäkring")
# Returns: ["sjukvård", "försäkring"]
```

#### Features

- Swedish-aware tokenization
- Compound word splitting (decompounding)
- Handles Swedish characters (å, ä, ö)
- Preserves important punctuation

---

## Models

### KB-BERT

The Named Entity Recognition uses KB-BERT (Kungliga Biblioteket BERT):

- **Model:** `KB/bert-base-swedish-cased-ner`
- **Training:** Fine-tuned on Swedish NER datasets
- **Entities:** PER, ORG, LOC, MISC

```python
# Model configuration
KB_BERT_MODEL = "KB/bert-base-swedish-cased-ner"
```

### GPT-SW3 (Optional)

For text summarization:

- **Model:** `AI-Sweden-Models/gpt-sw3-1.3b`
- **Usage:** Document summarization, report generation

```python
from halo.nlp.models.gpt_sw3 import GPTSw3Summarizer

summarizer = GPTSw3Summarizer()
summary = await summarizer.summarize(long_text, max_length=200)
```

---

## Configuration

### Environment Variables

```bash
# Model paths (optional - defaults to downloading from HuggingFace)
KB_BERT_MODEL_PATH=./models/kb-bert-ner
GPT_SW3_MODEL_PATH=./models/gpt-sw3

# GPU settings
NLP_USE_GPU=false
NLP_BATCH_SIZE=32

# Analysis settings
NLP_MAX_TEXT_LENGTH=50000
NLP_ENABLE_SUMMARIZATION=true
```

### Pipeline Configuration

```python
pipeline = NLPPipeline(
    use_gpu=False,
    enable_ner=True,
    enable_sentiment=True,
    enable_threat_detection=True,
    enable_summarization=False,  # Requires GPT-SW3
)
```

---

## Performance

### Benchmarks

| Component | Speed (chars/sec) | Memory |
|-----------|------------------|--------|
| Tokenizer | 500,000 | 50 MB |
| NER (KB-BERT) | 5,000 | 500 MB |
| Sentiment | 100,000 | 100 MB |
| Threat Vocab | 1,000,000 | 20 MB |

### Optimization Tips

1. **Batch Processing:** Process multiple documents together
2. **GPU Acceleration:** Enable for KB-BERT if available
3. **Selective Analysis:** Disable unused components
4. **Caching:** Cache results for frequently analyzed texts

```python
# Batch processing example
results = await pipeline.analyze_batch([doc1, doc2, doc3])
```

---

## Usage Examples

### Full Analysis Pipeline

```python
from halo.nlp import NLPPipeline

async def analyze_document(text: str):
    pipeline = NLPPipeline()
    result = await pipeline.analyze(text)

    # Check for concerning content
    if result.sentiment.is_concerning:
        print(f"Concerning content detected!")
        print(f"Fear score: {result.sentiment.fear_score}")
        print(f"Violence score: {result.sentiment.violence_score}")

    # Extract entities for linking
    for entity in result.entities:
        if entity.label == "PERSONNUMMER":
            print(f"Found personnummer: {entity.normalized}")
        elif entity.label == "ORG":
            print(f"Found organization: {entity.text}")

    # Check for threat vocabulary
    for match in result.threat_matches:
        if match.severity == "high":
            print(f"High-severity term: {match.keyword} ({match.category})")

    return result
```

### Integration with Entity Resolution

```python
from halo.nlp import NLPPipeline
from halo.entities import EntityResolver

async def extract_and_resolve(text: str):
    # NLP analysis
    pipeline = NLPPipeline()
    nlp_result = await pipeline.analyze(text)

    # Entity resolution
    resolver = EntityResolver()

    for entity in nlp_result.entities:
        if entity.label == "PERSONNUMMER":
            resolved = await resolver.resolve_person(entity.normalized)
            print(f"Resolved to: {resolved.display_name}")
        elif entity.label == "ORGNR":
            resolved = await resolver.resolve_company(entity.normalized)
            print(f"Resolved to: {resolved.display_name}")
```

### Document Processing Workflow

```python
from halo.nlp import NLPPipeline
from halo.db.models import Document

async def process_document(doc: Document):
    pipeline = NLPPipeline()
    result = await pipeline.analyze(doc.raw_text)

    # Update document with NLP results
    doc.entities_extracted = [
        {"text": e.text, "label": e.label, "start": e.start, "end": e.end}
        for e in result.entities
    ]
    doc.sentiment_scores = {
        "polarity": result.sentiment.polarity,
        "fear": result.sentiment.fear_score,
        "violence": result.sentiment.violence_score,
        "threat": result.sentiment.threat_score,
    }
    doc.threat_indicators = [m.keyword for m in result.threat_matches]
    doc.summary = result.summary
    doc.processed = True

    return doc
```
