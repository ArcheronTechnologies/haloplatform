# Halo - Swedish-Sovereign Intelligence Platform

A platform for law enforcement and financial compliance built specifically for the Swedish market.

## Overview

Halo provides:
- **Entity Resolution** - Resolve Swedish entities (people, companies, properties) across fragmented public records
- **Swedish NLP** - Analyze Swedish text including informal language (forums, social media, Rinkebysvenska)
- **Anomaly Detection** - Detect transaction anomalies for bank AML compliance
- **Investigation Support** - Generate investigation leads with full audit trails

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         HALO PLATFORM                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Layer 1: DATA INGESTION                                        │
│   ├── Swedish Government APIs (SCB, Bolagsverket, Lantmäteriet) │
│   ├── Bank Transactions (CAMT.053, CSV, Bankgirot)              │
│   └── Document Upload (PDF, DOCX, Email)                        │
│                                                                  │
│   Layer 2: ENTITY RESOLUTION                                     │
│   ├── Person Matcher (personnummer validation)                   │
│   ├── Company Matcher (organisationsnummer validation)           │
│   └── Entity Graph (relationship mapping)                        │
│                                                                  │
│   Layer 3: NLP ANALYSIS                                          │
│   ├── KB-BERT NER (Named Entity Recognition)                     │
│   ├── GPT-SW3 (Swedish text generation/summarization)            │
│   ├── Sentiment Analysis (fear/violence detection)               │
│   └── Threat Vocabulary Detection                                │
│                                                                  │
│   Layer 4: ANOMALY DETECTION                                     │
│   ├── Transaction Patterns                                       │
│   ├── AML Pattern Detection                                      │
│   └── Risk Scoring                                               │
│                                                                  │
│   Layer 5: INVESTIGATION                                         │
│   ├── Case Management                                            │
│   ├── Evidence Handling                                          │
│   └── Workflow Engine                                            │
│                                                                  │
│   Layer 6: API & UI                                              │
│   ├── FastAPI Backend                                            │
│   └── React Frontend                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Node.js 18+ (for UI)

### Installation

```bash
# Clone the repository
git clone https://github.com/atlas-intelligence/halo.git
cd halo

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment configuration
cp .env.example .env
# Edit .env with your credentials

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn halo.api.main:app --reload
```

### Running the UI

```bash
cd halo/ui
npm install
npm run dev
```

## Project Structure

```
halo/
├── api/                    # FastAPI application
│   ├── routes/            # API endpoints
│   │   ├── alerts.py      # Alert management
│   │   ├── auth.py        # Authentication (BankID, OIDC)
│   │   ├── cases.py       # Case management
│   │   ├── entities.py    # Entity operations
│   │   └── search.py      # Search functionality
│   └── main.py            # FastAPI app initialization
│
├── db/                     # Database layer
│   ├── models.py          # SQLAlchemy models
│   └── migrations/        # Alembic migrations
│
├── entities/               # Entity resolution
│   ├── swedish_personnummer.py   # Personnummer validation
│   ├── organisationsnummer.py    # Org number validation
│   ├── graph.py                  # Entity graph operations
│   └── resolution.py             # Resolution engine
│
├── nlp/                    # Swedish NLP
│   ├── models/            # Model implementations
│   │   ├── kb_bert_ner.py # KB-BERT NER
│   │   └── gpt_sw3.py     # GPT-SW3 integration
│   ├── ner.py             # Named entity recognition
│   ├── sentiment.py       # Sentiment analysis
│   └── threat_vocab.py    # Threat vocabulary detection
│
├── anomaly/                # Anomaly detection
│   ├── rules_engine.py    # Rule-based detection
│   ├── scorer.py          # Risk scoring
│   └── transaction_patterns.py  # Transaction analysis
│
├── fincrime/               # Financial crime detection
│   ├── aml_patterns.py    # AML pattern detection
│   ├── risk_scoring.py    # Risk scoring methodology
│   ├── sar_generator.py   # SAR report generation
│   └── watchlist.py       # Watchlist integration
│
├── investigation/          # Investigation support
│   ├── case_manager.py    # Case management
│   ├── evidence.py        # Evidence handling
│   ├── timeline.py        # Timeline analysis
│   └── workflow.py        # Workflow engine
│
├── graph/                  # Intelligence graph
│   ├── schema.py          # Node types (Person, Company, Address)
│   ├── edges.py           # Edge types (ownership, directorships)
│   └── client.py          # Graph client (NetworkX, Neo4j)
│
├── intelligence/           # Proactive fraud detection
│   ├── anomaly.py         # Layer 1: Statistical anomaly detection
│   ├── patterns.py        # Layer 2: Graph pattern matching
│   ├── predictive.py      # Layer 3: ML-based risk prediction
│   ├── formation_agent.py # Formation agent tracking
│   ├── sequence_detector.py # Fraud playbook detection
│   ├── evasion.py         # Evasion behavior detection
│   ├── sar_generator.py   # SAR report generation
│   └── konkurs.py         # Bankruptcy prediction
│
├── ingestion/              # Data ingestion adapters
│   ├── scb_foretag.py     # SCB Företagsregistret
│   ├── scb_pxweb.py       # SCB Statistical Database
│   ├── bolagsverket_hvd.py # Bolagsverket HVD API
│   ├── lantmateriet.py    # Lantmäteriet Open Data
│   ├── bank_transactions.py # Bank transaction import
│   └── document_upload.py  # Document ingestion
│
├── review/                 # Human review system
│   ├── workflow.py        # Review workflow
│   └── validation.py      # Validation rules
│
├── ui/                     # React frontend
│   └── src/
│       ├── components/    # React components
│       ├── pages/         # Page components
│       └── services/      # API services
│
├── config.py               # Configuration management
└── security_framework.md   # Security documentation
```

## Configuration

Configuration is managed through environment variables. See `.env.example` for all options.

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/halo

# Redis
REDIS_URL=redis://localhost:6379

# Security
SECRET_KEY=your-secure-secret-key-min-32-chars
PII_ENCRYPTION_KEY=base64-encoded-fernet-key

# Swedish Government APIs (see Data_credentials.md for details)
SCB_CERT_PATH=./secrets/scb_cert.p12
SCB_CERT_PASSWORD=your-password
BOLAGSVERKET_CLIENT_ID=your-client-id
BOLAGSVERKET_CLIENT_SECRET=your-client-secret
LANTMATERIET_GEOTORGET_USERNAME=your-username
LANTMATERIET_GEOTORGET_PASSWORD=your-password
```

## Documentation

| Document | Description |
|----------|-------------|
| [graph/README.md](graph/README.md) | Intelligence graph module documentation |
| [intelligence/README.md](intelligence/README.md) | Proactive fraud detection framework |
| [Data_credentials.md](Data_credentials.md) | Swedish government API credentials and integration guide |
| [security_framework.md](security_framework.md) | Security architecture and compliance |
| [SECURITY_REPORT.md](SECURITY_REPORT.md) | Security assessment and audit findings |
| [API_COMPLIANCE.md](ingestion/API_COMPLIANCE.md) | API compliance and rate limits |
| [SCB_DATA_PLAN.md](ingestion/SCB_DATA_PLAN.md) | SCB data integration strategy |
| [docs/api.md](docs/api.md) | API endpoint documentation |
| [docs/database.md](docs/database.md) | Database schema documentation |
| [docs/nlp.md](docs/nlp.md) | NLP models documentation |

## Target Customers

1. **Swedish Banks** (Swedbank, SEB) - AML compliance post-scandal
2. **Municipalities** - NIS2 compliance by January 2026
3. **Swedish Police** - STATUS enhancement/replacement
4. **Insurance Companies** - Fraud investigation

## Compliance

Halo is designed for Swedish regulatory compliance:

- **GDPR** - Data minimization, encryption, audit trails
- **Brottsdatalagen** - Human-in-loop required for decisions affecting individuals
- **NIS2** - Security requirements for critical infrastructure
- **AML/KYC** - Anti-money laundering pattern detection

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=halo --cov-report=html

# Run specific test file
pytest tests/test_entities.py -v
```

### Code Quality

```bash
# Format code
black halo/
isort halo/

# Type checking
mypy halo/

# Linting
ruff check halo/
```

## License

Proprietary - Atlas Intelligence AB

## Contact

- **Company:** Atlas Intelligence (formerly Archeron AB)
- **Engineers:** Tim (Lead), Fredrik (Co-founder)
