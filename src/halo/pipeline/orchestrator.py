#!/usr/bin/env python3
"""
Unified Data Pipeline Orchestrator.

Chains all data sources into a continuous flow:
  SCB Företagsregistret -> Bolagsverket HVD -> Allabolag scraper -> Graph + Alerts

When new org numbers are discovered by SCB, they automatically flow through
each enrichment stage and end up in the intelligence graph.

Usage:
    # Run full pipeline (discovers new orgs, enriches, scrapes, updates graph)
    python -m halo.pipeline.orchestrator --full

    # Run specific stage
    python -m halo.pipeline.orchestrator --stage scb
    python -m halo.pipeline.orchestrator --stage bolagsverket
    python -m halo.pipeline.orchestrator --stage allabolag
    python -m halo.pipeline.orchestrator --stage graph

    # Watch mode (continuous processing)
    python -m halo.pipeline.orchestrator --watch
"""

import asyncio
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass, field, asdict

import httpx
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PipelineStage(str, Enum):
    """Pipeline stages in order of execution."""
    SCB = "scb"                    # Discover org numbers from SCB
    BOLAGSVERKET = "bolagsverket"  # Enrich with Bolagsverket HVD
    GRAPH = "graph"                # Build/update intelligence graph (immediate)
    ALLABOLAG = "allabolag"        # Async enrichment with directors/financials


class JobStatus(str, Enum):
    """Status of a pipeline job."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PipelineJob:
    """A job in the pipeline for a single org number."""
    orgnr: str
    current_stage: PipelineStage
    status: JobStatus = JobStatus.PENDING
    scb_data: Optional[dict] = None
    bolagsverket_data: Optional[dict] = None
    directors_data: Optional[list] = None  # Extracted directors from XBRL/PDF
    allabolag_data: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class PipelineStats:
    """Statistics for pipeline execution."""
    orgnrs_discovered: int = 0
    bolagsverket_enriched: int = 0
    allabolag_scraped: int = 0
    graph_updated: int = 0
    errors: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None


class PipelineDatabase:
    """SQLite database for pipeline state management."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pipeline_jobs (
                orgnr TEXT PRIMARY KEY,
                current_stage TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                scb_data TEXT,
                bolagsverket_data TEXT,
                directors_data TEXT,
                allabolag_data TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT,
                retry_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_stage_status
            ON pipeline_jobs(current_stage, status);

            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                stats TEXT,
                status TEXT DEFAULT 'running'
            );
        """)
        # Add directors_data column if it doesn't exist (migration)
        try:
            conn.execute("ALTER TABLE pipeline_jobs ADD COLUMN directors_data TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()
        conn.close()

    def add_orgnrs(self, orgnrs: list[str], stage: PipelineStage = PipelineStage.SCB):
        """Add new org numbers to the pipeline."""
        conn = sqlite3.connect(self.db_path)
        now = datetime.now(timezone.utc).isoformat()

        added = 0
        for orgnr in orgnrs:
            orgnr = orgnr.replace("-", "").strip()
            if len(orgnr) != 10:
                continue
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO pipeline_jobs
                    (orgnr, current_stage, status, created_at, updated_at)
                    VALUES (?, ?, 'pending', ?, ?)
                """, (orgnr, stage.value, now, now))
                added += 1
            except sqlite3.IntegrityError:
                pass

        conn.commit()
        conn.close()
        return added

    def get_jobs_for_stage(
        self,
        stage: PipelineStage,
        status: JobStatus = JobStatus.PENDING,
        limit: int = 100
    ) -> list[PipelineJob]:
        """Get jobs ready for a specific stage."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT * FROM pipeline_jobs
            WHERE current_stage = ? AND status = ?
            ORDER BY created_at ASC
            LIMIT ?
        """, (stage.value, status.value, limit)).fetchall()

        conn.close()

        jobs = []
        for row in rows:
            jobs.append(PipelineJob(
                orgnr=row['orgnr'],
                current_stage=PipelineStage(row['current_stage']),
                status=JobStatus(row['status']),
                scb_data=json.loads(row['scb_data']) if row['scb_data'] else None,
                bolagsverket_data=json.loads(row['bolagsverket_data']) if row['bolagsverket_data'] else None,
                directors_data=json.loads(row['directors_data']) if row['directors_data'] else None,
                allabolag_data=json.loads(row['allabolag_data']) if row['allabolag_data'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                error=row['error'],
                retry_count=row['retry_count'],
            ))

        return jobs

    def update_job(self, job: PipelineJob):
        """Update a job's status and data."""
        conn = sqlite3.connect(self.db_path)
        job.updated_at = datetime.now(timezone.utc).isoformat()

        conn.execute("""
            UPDATE pipeline_jobs SET
                current_stage = ?,
                status = ?,
                scb_data = ?,
                bolagsverket_data = ?,
                directors_data = ?,
                allabolag_data = ?,
                updated_at = ?,
                error = ?,
                retry_count = ?
            WHERE orgnr = ?
        """, (
            job.current_stage.value,
            job.status.value,
            json.dumps(job.scb_data) if job.scb_data else None,
            json.dumps(job.bolagsverket_data) if job.bolagsverket_data else None,
            json.dumps(job.directors_data) if job.directors_data else None,
            json.dumps(job.allabolag_data) if job.allabolag_data else None,
            job.updated_at,
            job.error,
            job.retry_count,
            job.orgnr,
        ))

        conn.commit()
        conn.close()

    def advance_job(self, job: PipelineJob):
        """Advance a job to the next pipeline stage."""
        stage_order = [
            PipelineStage.SCB,
            PipelineStage.BOLAGSVERKET,
            PipelineStage.ALLABOLAG,
            PipelineStage.GRAPH,
        ]

        current_idx = stage_order.index(job.current_stage)
        if current_idx < len(stage_order) - 1:
            job.current_stage = stage_order[current_idx + 1]
            job.status = JobStatus.PENDING
        else:
            job.status = JobStatus.COMPLETED

        self.update_job(job)

    def get_stats(self) -> dict:
        """Get pipeline statistics."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        stats = {}
        for stage in PipelineStage:
            for status in JobStatus:
                count = conn.execute("""
                    SELECT COUNT(*) as cnt FROM pipeline_jobs
                    WHERE current_stage = ? AND status = ?
                """, (stage.value, status.value)).fetchone()['cnt']

                key = f"{stage.value}_{status.value}"
                stats[key] = count

        total = conn.execute("SELECT COUNT(*) as cnt FROM pipeline_jobs").fetchone()['cnt']
        stats['total_jobs'] = total

        conn.close()
        return stats


class PipelineOrchestrator:
    """
    Orchestrates the full data pipeline.

    Flow:
    1. SCB: Discover new org numbers from SCB Företagsregistret
    2. Bolagsverket: Enrich with official registration data
    3. Allabolag: Scrape for directors, financials, addresses
    4. Graph: Update the intelligence graph and run pattern detection
    """

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path(__file__).parent.parent.parent / "data"
        self.db = PipelineDatabase(self.data_dir / "pipeline.db")

        # Lazy-loaded adapters
        self._scb_adapter = None
        self._bolagsverket_adapter = None
        self._allabolag_scraper = None

        # Stats for current run
        self.stats = PipelineStats()

    async def run_full_pipeline(
        self,
        discover_limit: int = 1000,
        enrich_limit: int = 100,
    ):
        """
        Run the full pipeline end-to-end.

        Flow: SCB -> Bolagsverket -> Graph (immediate)
              Allabolag runs async and updates graph nodes later

        Args:
            discover_limit: Max new org numbers to discover from SCB
            enrich_limit: Max org numbers to enrich via Bolagsverket
        """
        logger.info("=" * 60)
        logger.info("STARTING FULL PIPELINE RUN")
        logger.info("=" * 60)

        self.stats = PipelineStats()

        # Stage 1: Discover new org numbers from SCB
        await self.run_scb_discovery(limit=discover_limit)

        # Stage 2: Enrich with Bolagsverket
        await self.run_bolagsverket_enrichment(limit=enrich_limit)

        # Stage 3: Update graph immediately with SCB+Bolagsverket data
        await self.run_graph_update()

        # Stage 4: Queue for allabolag enrichment (async, runs in background)
        await self.queue_allabolag_enrichment()

        self.stats.completed_at = datetime.now(timezone.utc).isoformat()

        logger.info("=" * 60)
        logger.info("PIPELINE RUN COMPLETE")
        logger.info(f"  Discovered: {self.stats.orgnrs_discovered}")
        logger.info(f"  Bolagsverket enriched: {self.stats.bolagsverket_enriched}")
        logger.info(f"  Graph updated: {self.stats.graph_updated}")
        logger.info(f"  Queued for allabolag: {self.stats.allabolag_scraped}")
        logger.info(f"  Errors: {self.stats.errors}")
        logger.info("=" * 60)

        return self.stats

    async def run_scb_discovery(self, limit: int = 1000):
        """
        Stage 1: Discover new org numbers from SCB Företagsregistret.

        Pulls org numbers from SCB and adds them to the pipeline.
        """
        logger.info("[Stage 1] SCB Discovery")

        try:
            from halo.ingestion.scb_foretag import SCBForetagAdapter

            # Check for certificate
            cert_path = self.data_dir / "[REDACTED_CERT]"
            if not cert_path.exists():
                logger.warning("SCB certificate not found, using existing org number files")
                # Fall back to loading from JSON files
                discovered = await self._load_orgnrs_from_files()
                self.stats.orgnrs_discovered = discovered
                return

            # Initialize adapter
            adapter = SCBForetagAdapter(
                cert_path=cert_path,
                cert_password="[REDACTED_PASSWORD]"  # From existing scripts
            )

            try:
                # Count available
                total = await adapter.count_companies(only_active=True, legal_form="49")
                logger.info(f"  Total active ABs in SCB: {total:,}")

                # Fetch multiple batches to reach target (SCB max is 2000 per request)
                new_orgnrs = []
                offset = 0
                batch_size = 2000

                while len(new_orgnrs) < limit:
                    records = await adapter.fetch_companies_batch(
                        offset=offset,
                        limit=batch_size,
                        only_active=True,
                        legal_form="49",
                    )

                    if not records:
                        break

                    for record in records:
                        orgnr = record.raw_data.get("OrgNr", "")
                        # Convert 12-digit to 10-digit
                        if len(orgnr) == 12 and orgnr.startswith("16"):
                            orgnr = orgnr[2:]

                        if len(orgnr) == 10 and orgnr.isdigit():
                            new_orgnrs.append(orgnr)

                    offset += len(records)
                    logger.info(f"  Fetched batch: {len(records)} orgnrs (total: {len(new_orgnrs)})")

                    # Rate limiting
                    await asyncio.sleep(1)

                # Add to pipeline (SCB stage completed, move to Bolagsverket)
                added = self.db.add_orgnrs(new_orgnrs[:limit], stage=PipelineStage.BOLAGSVERKET)
                self.stats.orgnrs_discovered = added
                logger.info(f"  Discovered {added} new org numbers")

            finally:
                await adapter.close()

        except ImportError:
            logger.warning("SCB adapter not available, loading from files")
            discovered = await self._load_orgnrs_from_files()
            self.stats.orgnrs_discovered = discovered
        except Exception as e:
            logger.error(f"SCB discovery failed: {e}")
            self.stats.errors += 1
            # Fall back to files
            discovered = await self._load_orgnrs_from_files()
            self.stats.orgnrs_discovered = discovered

    async def _load_orgnrs_from_files(self) -> int:
        """Load org numbers from existing JSON files."""
        all_orgnrs = set()

        sources = [
            "orgnrs_scb_established.json",
            "orgnrs_combined.json",
            "orgnrs_new_batch.json",
            "orgnrs_demo.json",
        ]

        for filename in sources:
            filepath = self.data_dir / filename
            if filepath.exists():
                try:
                    with open(filepath) as f:
                        data = json.load(f)
                    for item in data:
                        if isinstance(item, str):
                            all_orgnrs.add(item.replace("-", ""))
                        elif isinstance(item, dict) and 'orgnr' in item:
                            all_orgnrs.add(item['orgnr'].replace("-", ""))
                    logger.info(f"  Loaded {len(data)} from {filename}")
                except Exception as e:
                    logger.warning(f"  Failed to load {filename}: {e}")

        # Add to pipeline
        added = self.db.add_orgnrs(list(all_orgnrs), stage=PipelineStage.BOLAGSVERKET)
        logger.info(f"  Added {added} org numbers from files")
        return added

    async def run_bolagsverket_enrichment(self, limit: int = 100):
        """
        Stage 2: Enrich org numbers with Bolagsverket HVD data.

        Fetches official company registration data AND extracts directors
        from annual reports (XBRL/PDF).
        """
        logger.info("[Stage 2] Bolagsverket Enrichment")

        jobs = self.db.get_jobs_for_stage(PipelineStage.BOLAGSVERKET, limit=limit)
        if not jobs:
            logger.info("  No jobs pending for Bolagsverket stage")
            return

        logger.info(f"  Processing {len(jobs)} org numbers")

        try:
            from halo.ingestion.bolagsverket_hvd import BolagsverketHVDAdapter
            from halo.config import settings

            # Check for credentials
            if not settings.bolagsverket_client_id:
                logger.warning("Bolagsverket credentials not configured, skipping enrichment")
                # Move jobs to next stage without enrichment
                for job in jobs:
                    job.status = JobStatus.SKIPPED
                    self.db.advance_job(job)
                return

            adapter = BolagsverketHVDAdapter()

            # Also initialize extraction pipeline for directors
            extraction_pipeline = None
            try:
                from halo.extraction.pipeline import ExtractionPipeline, PipelineConfig
                extraction_config = PipelineConfig(
                    bv_client_id=settings.bolagsverket_client_id,
                    bv_client_secret=settings.bolagsverket_client_secret,
                    rate_limit_delay=1.0,
                )
                extraction_pipeline = ExtractionPipeline(extraction_config)
            except ImportError as e:
                logger.warning(f"  Extraction pipeline not available: {e}")

            try:
                enriched = 0
                directors_extracted = 0

                # Start extraction pipeline context if available
                if extraction_pipeline:
                    await extraction_pipeline.__aenter__()

                for job in jobs:
                    try:
                        job.status = JobStatus.IN_PROGRESS
                        self.db.update_job(job)

                        # Step 1: Fetch basic company data
                        record = await adapter.fetch_company(job.orgnr)

                        if record:
                            job.bolagsverket_data = record.raw_data
                            enriched += 1

                        # Step 2: Extract directors from annual reports
                        if extraction_pipeline:
                            try:
                                results = await extraction_pipeline.process_company(
                                    job.orgnr, max_documents=1
                                )
                                if results and results[0].directors:
                                    # Store extracted directors
                                    job.directors_data = [
                                        {
                                            "first_name": d.first_name,
                                            "last_name": d.last_name,
                                            "role": d.role,
                                            "role_normalized": d.role_normalized,
                                            "confidence": d.confidence,
                                        }
                                        for d in results[0].directors
                                    ]
                                    directors_extracted += 1
                                    logger.debug(f"  Extracted {len(results[0].directors)} directors for {job.orgnr}")
                            except Exception as e:
                                logger.debug(f"  Director extraction failed for {job.orgnr}: {e}")

                        job.status = JobStatus.COMPLETED
                        self.db.advance_job(job)

                        # Rate limiting - Bolagsverket enforces strict limits
                        await asyncio.sleep(1.5)

                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429:
                            # Rate limited - wait longer and retry
                            logger.warning(f"  Rate limited, waiting 30s...")
                            await asyncio.sleep(30)
                            job.status = JobStatus.PENDING  # Retry later
                            self.db.update_job(job)
                        else:
                            logger.error(f"  Failed to enrich {job.orgnr}: {e}")
                            job.error = str(e)
                            job.retry_count += 1
                            if job.retry_count >= 3:
                                job.status = JobStatus.FAILED
                            else:
                                job.status = JobStatus.PENDING
                            self.db.update_job(job)
                            self.stats.errors += 1
                    except Exception as e:
                        logger.error(f"  Failed to enrich {job.orgnr}: {e}")
                        job.error = str(e)
                        job.retry_count += 1
                        if job.retry_count >= 3:
                            job.status = JobStatus.FAILED
                        else:
                            job.status = JobStatus.PENDING
                        self.db.update_job(job)
                        self.stats.errors += 1

                self.stats.bolagsverket_enriched = enriched
                logger.info(f"  Enriched {enriched} org numbers")
                logger.info(f"  Extracted directors for {directors_extracted} companies")

            finally:
                await adapter.close()
                if extraction_pipeline:
                    await extraction_pipeline.__aexit__(None, None, None)

        except ImportError:
            logger.warning("Bolagsverket adapter not available, skipping stage")
            for job in jobs:
                job.status = JobStatus.SKIPPED
                self.db.advance_job(job)
        except Exception as e:
            logger.error(f"Bolagsverket enrichment failed: {e}")
            self.stats.errors += 1

    async def run_allabolag_scraping(self, limit: int = 50):
        """
        Stage 3: Scrape allabolag.se for detailed company data.

        Gets directors, financials, addresses, etc.
        """
        logger.info("[Stage 3] Allabolag Scraping")

        jobs = self.db.get_jobs_for_stage(PipelineStage.ALLABOLAG, limit=limit)
        if not jobs:
            logger.info("  No jobs pending for Allabolag stage")
            return

        logger.info(f"  Processing {len(jobs)} org numbers")

        try:
            # Import allabolag scraper
            from allabolag.config import ScraperConfig
            from allabolag.database import ScraperDatabase

            config = ScraperConfig()
            db = ScraperDatabase(config.storage)

            # Add jobs to allabolag scraper queue
            orgnrs = [job.orgnr for job in jobs]
            db.add_jobs(orgnrs, priority=5)

            logger.info(f"  Added {len(orgnrs)} to allabolag scraper queue")
            logger.info("  Note: Run 'python -m allabolag' to process the queue")

            # Mark jobs as in progress (they'll be completed when scraper runs)
            for job in jobs:
                job.status = JobStatus.IN_PROGRESS
                self.db.update_job(job)

            # Check if any have already been scraped
            scraped = self._check_allabolag_results(jobs)
            self.stats.allabolag_scraped = scraped

        except ImportError as e:
            logger.error(f"Allabolag module not available: {e}")
            self.stats.errors += 1
        except Exception as e:
            logger.error(f"Allabolag scraping failed: {e}")
            self.stats.errors += 1

    def _check_allabolag_results(self, jobs: list[PipelineJob]) -> int:
        """Check if orgnrs have been scraped by allabolag and update pipeline."""
        allabolag_db = self.data_dir.parent / "allabolag_scrape.db"
        if not allabolag_db.exists():
            return 0

        conn = sqlite3.connect(allabolag_db)
        conn.row_factory = sqlite3.Row

        scraped = 0
        for job in jobs:
            row = conn.execute(
                "SELECT * FROM companies WHERE orgnr = ?",
                (job.orgnr,)
            ).fetchone()

            if row:
                job.allabolag_data = dict(row)
                job.status = JobStatus.COMPLETED
                self.db.advance_job(job)
                scraped += 1

        conn.close()
        return scraped

    async def run_graph_update(self):
        """
        Stage 3: Update the intelligence graph with SCB+Bolagsverket data.

        Loads companies immediately - no waiting for allabolag.
        Allabolag enriches asynchronously later.
        """
        logger.info("[Stage 3] Graph Update")

        jobs = self.db.get_jobs_for_stage(PipelineStage.GRAPH, limit=1000)
        if not jobs:
            logger.info("  No jobs pending for Graph stage")
            return

        logger.info(f"  Processing {len(jobs)} org numbers")

        try:
            import pickle
            import networkx as nx
            from pathlib import Path

            GRAPH_PATH = self.data_dir / "company_graph.pickle"

            # Load existing graph or create new
            if GRAPH_PATH.exists():
                with open(GRAPH_PATH, "rb") as f:
                    graph = pickle.load(f)
                logger.info(f"  Loaded existing graph: {graph.number_of_nodes()} nodes")
            else:
                graph = nx.MultiDiGraph()

            # Add companies from Bolagsverket data
            updated = 0
            for job in jobs:
                try:
                    # Create company node from Bolagsverket data
                    company_id = f"company-{job.orgnr}"

                    if job.bolagsverket_data:
                        bv = job.bolagsverket_data

                        # Extract company name from organisationsnamn structure
                        company_name = ""
                        org_namn = bv.get("organisationsnamn", {})
                        if org_namn:
                            namn_lista = org_namn.get("organisationsnamnLista", [])
                            if namn_lista:
                                # Get primary name (FORETAGSNAMN type preferred)
                                for namn_entry in namn_lista:
                                    namn_type = namn_entry.get("organisationsnamntyp", {}).get("kod", "")
                                    if namn_type == "FORETAGSNAMN":
                                        company_name = namn_entry.get("namn", "")
                                        break
                                # Fall back to first name if no FORETAGSNAMN
                                if not company_name and namn_lista:
                                    company_name = namn_lista[0].get("namn", "")

                        # Extract company info from Bolagsverket response
                        node_data = {
                            "_type": "Company",
                            "orgnr": job.orgnr,
                            "names": [{"name": company_name, "type": "legal"}],
                            "legal_form": bv.get("juridiskForm", {}).get("beskrivning"),
                            "status": bv.get("status", {}).get("beskrivning"),
                            "registration_date": bv.get("organisationsdatum", {}).get("registreringsdatum"),
                            "source": "bolagsverket_hvd",
                            "pipeline_loaded_at": datetime.now(timezone.utc).isoformat(),
                        }

                        # Address - nested under postadressOrganisation.postadress
                        post_addr_org = bv.get("postadressOrganisation", {})
                        if post_addr_org:
                            addr = post_addr_org.get("postadress", {})
                            if addr:
                                node_data["address"] = {
                                    "street": addr.get("utdelningsadress"),
                                    "postal_code": addr.get("postnummer"),
                                    "city": addr.get("postort"),
                                }

                        # SNI codes - nested under naringsgrenOrganisation.sni
                        naringsgren = bv.get("naringsgrenOrganisation", {})
                        if naringsgren:
                            sni_list = naringsgren.get("sni", [])
                            # Filter out empty entries
                            valid_sni = [s for s in sni_list if s.get("kod", "").strip()]
                            if valid_sni:
                                node_data["sni_codes"] = valid_sni

                        # Business description - nested under verksamhetsbeskrivning.beskrivning
                        verks = bv.get("verksamhetsbeskrivning", {})
                        if verks and verks.get("beskrivning"):
                            node_data["purpose"] = verks["beskrivning"]

                        graph.add_node(company_id, **node_data)
                        updated += 1

                    # Add directors from extracted data
                    if hasattr(job, 'directors_data') and job.directors_data:
                        for i, director in enumerate(job.directors_data):
                            # Create unique person ID based on name
                            first_name = director.get("first_name", "")
                            last_name = director.get("last_name", "")
                            full_name = f"{first_name} {last_name}".strip()

                            # Create deterministic ID from name
                            name_key = full_name.lower().replace(" ", "_")
                            person_id = f"person-{name_key}"

                            # Add or update person node
                            if person_id not in graph:
                                graph.add_node(person_id, **{
                                    "_type": "Person",
                                    "names": [{"name": full_name, "type": "legal"}],
                                    "source": "bolagsverket_xbrl",
                                })

                            # Add director edge
                            role = director.get("role_normalized", "STYRELSELEDAMOT")
                            graph.add_edge(person_id, company_id, **{
                                "_type": "director",
                                "role": role,
                                "source": "bolagsverket_xbrl",
                            })

                    # Advance to allabolag stage for async enrichment
                    job.status = JobStatus.COMPLETED
                    self.db.advance_job(job)

                except Exception as e:
                    logger.error(f"  Failed to add {job.orgnr} to graph: {e}")
                    job.error = str(e)
                    job.status = JobStatus.FAILED
                    self.db.update_job(job)
                    self.stats.errors += 1

            # Save graph
            with open(GRAPH_PATH, "wb") as f:
                pickle.dump(graph, f)
            logger.info(f"  Graph saved: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

            # Run pattern detection
            try:
                from scripts.load_allabolag import run_pattern_detection
                run_pattern_detection(graph)
            except Exception as e:
                logger.warning(f"  Pattern detection skipped: {e}")

            self.stats.graph_updated = updated
            logger.info(f"  Added {updated} companies to graph")

        except Exception as e:
            logger.error(f"Graph update failed: {e}")
            self.stats.errors += 1

    async def queue_allabolag_enrichment(self):
        """
        Stage 4: Queue companies for async allabolag enrichment.

        Adds orgnrs to allabolag scraper queue. The scraper runs separately
        and updates the graph nodes when it completes.
        """
        logger.info("[Stage 4] Queue Allabolag Enrichment")

        jobs = self.db.get_jobs_for_stage(PipelineStage.ALLABOLAG, limit=1000)
        if not jobs:
            logger.info("  No jobs pending for Allabolag enrichment")
            return

        logger.info(f"  Queueing {len(jobs)} org numbers for allabolag")

        try:
            from allabolag.config import ScraperConfig
            from allabolag.database import ScraperDatabase

            config = ScraperConfig()
            scraper_db = ScraperDatabase(config.storage)

            # Add to allabolag scraper queue
            orgnrs = [job.orgnr for job in jobs]
            scraper_db.add_jobs(orgnrs, priority=5)

            # Mark as in progress in pipeline (allabolag will complete them)
            for job in jobs:
                job.status = JobStatus.IN_PROGRESS
                self.db.update_job(job)

            self.stats.allabolag_scraped = len(orgnrs)
            logger.info(f"  Queued {len(orgnrs)} orgnrs for allabolag enrichment")
            logger.info("  Run 'python -m allabolag run' to process the queue")

        except ImportError as e:
            logger.warning(f"Allabolag module not available: {e}")
        except Exception as e:
            logger.error(f"Failed to queue allabolag enrichment: {e}")

    async def watch(self, interval: int = 300):
        """
        Watch mode: continuously process the pipeline.

        Args:
            interval: Seconds between pipeline runs
        """
        logger.info(f"Starting watch mode (interval: {interval}s)")
        logger.info("Press Ctrl+C to stop")

        while True:
            try:
                await self.run_full_pipeline(
                    discover_limit=100,
                    enrich_limit=50,
                )

                stats = self.db.get_stats()
                logger.info(f"Pipeline stats: {json.dumps(stats, indent=2)}")

                logger.info(f"Sleeping for {interval} seconds...")
                await asyncio.sleep(interval)

            except KeyboardInterrupt:
                logger.info("Watch mode stopped")
                break
            except Exception as e:
                logger.error(f"Pipeline error: {e}")
                await asyncio.sleep(60)  # Wait before retry


async def main():
    import argparse

    parser = argparse.ArgumentParser(description='Halo Data Pipeline Orchestrator')
    parser.add_argument('--full', action='store_true', help='Run full pipeline (100 orgs)')
    parser.add_argument('--run-all', action='store_true', help='Run ALL pending orgs through pipeline')
    parser.add_argument('--stage', choices=['scb', 'bolagsverket', 'graph', 'allabolag'],
                       help='Run specific stage')
    parser.add_argument('--watch', action='store_true', help='Watch mode (continuous)')
    parser.add_argument('--interval', type=int, default=300, help='Watch interval in seconds')
    parser.add_argument('--limit', type=int, default=100, help='Limit for stage processing')
    parser.add_argument('--stats', action='store_true', help='Show pipeline statistics')
    parser.add_argument('--reset', action='store_true', help='Reset pipeline state')
    parser.add_argument('--discover', type=int, help='Discover N orgnrs from SCB')

    args = parser.parse_args()

    data_dir = Path(__file__).parent.parent.parent / "data"
    orchestrator = PipelineOrchestrator(data_dir=data_dir)

    if args.reset:
        print("Resetting pipeline state...")
        conn = sqlite3.connect(data_dir / "pipeline.db")
        conn.execute("DELETE FROM pipeline_jobs")
        conn.commit()
        conn.close()
        print("Pipeline cleared.")
        return

    if args.stats:
        stats = orchestrator.db.get_stats()
        print("\n" + "=" * 60)
        print("PIPELINE STATUS")
        print("=" * 60)

        # Group by stage
        stages = ['scb', 'bolagsverket', 'graph', 'allabolag']
        for stage in stages:
            pending = stats.get(f'{stage}_pending', 0)
            in_prog = stats.get(f'{stage}_in_progress', 0)
            completed = stats.get(f'{stage}_completed', 0)
            failed = stats.get(f'{stage}_failed', 0)
            total = pending + in_prog + completed + failed
            if total > 0:
                print(f"\n{stage.upper()}:")
                print(f"  Pending: {pending}  In Progress: {in_prog}  Completed: {completed}  Failed: {failed}")

        print(f"\nTotal jobs: {stats.get('total_jobs', 0)}")
        print("=" * 60)
        return

    if args.discover:
        print(f"Discovering {args.discover} orgnrs from SCB...")
        await orchestrator.run_scb_discovery(limit=args.discover)
        return

    if args.watch:
        await orchestrator.watch(interval=args.interval)
    elif args.run_all:
        # Run ALL pending through the full pipeline
        print("Running ALL pending orgnrs through pipeline...")
        stats = orchestrator.db.get_stats()
        total_pending = sum(v for k, v in stats.items() if 'pending' in k)
        print(f"Total pending: {total_pending}")

        while True:
            # Keep running until nothing left
            await orchestrator.run_full_pipeline(
                discover_limit=0,  # Don't discover new ones
                enrich_limit=10000,  # Process all
            )

            # Check if done
            stats = orchestrator.db.get_stats()
            bolagsverket_pending = stats.get('bolagsverket_pending', 0)
            graph_pending = stats.get('graph_pending', 0)

            if bolagsverket_pending == 0 and graph_pending == 0:
                print("\nAll orgnrs processed!")
                break

            print(f"\nRemaining: Bolagsverket={bolagsverket_pending}, Graph={graph_pending}")

    elif args.stage:
        if args.stage == 'scb':
            await orchestrator.run_scb_discovery(limit=args.limit)
        elif args.stage == 'bolagsverket':
            await orchestrator.run_bolagsverket_enrichment(limit=args.limit)
        elif args.stage == 'graph':
            await orchestrator.run_graph_update()
        elif args.stage == 'allabolag':
            await orchestrator.queue_allabolag_enrichment()
    else:
        # Default: run full pipeline
        await orchestrator.run_full_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
