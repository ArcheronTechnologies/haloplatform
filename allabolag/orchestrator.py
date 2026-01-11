"""
Main scraper orchestrator.

Coordinates:
- Job queue management
- Worker dispatch
- Progress monitoring
- Block detection and recovery
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from .config import ScraperConfig
from .database import ScraperDatabase, ScrapeJob, Company
from .session import SessionManager, BlockDetectedError
from .parser import AllabolagParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AllabolagScraper:
    """
    Main scraper orchestrator.

    Usage:
        config = ScraperConfig()
        scraper = AllabolagScraper(config)

        # Load orgnrs to scrape
        await scraper.load_jobs_from_file("orgnrs.txt")

        # Run
        await scraper.run()
    """

    def __init__(self, config: ScraperConfig = None, auto_update_graph: bool = True):
        self.config = config or ScraperConfig()
        self.db = ScraperDatabase(self.config.storage)
        self.session = SessionManager(self.config)
        self.parser = AllabolagParser()
        self.auto_update_graph = auto_update_graph

        self._running = False
        self._stats = {
            'scraped': 0,
            'failed': 0,
            'blocked': 0,
            'start_time': None,
        }
    
    async def load_jobs_from_file(self, filepath: str, priority: int = 0):
        """
        Load orgnrs from a text file (one per line).
        
        You can generate this from SCB Företagsregistret or
        by scraping allabolag.se's alphabetical company listing.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        orgnrs = []
        with open(path, 'r') as f:
            for line in f:
                orgnr = line.strip().replace('-', '')
                if orgnr and len(orgnr) == 10 and orgnr.isdigit():
                    orgnrs.append(orgnr)
        
        logger.info(f"Loading {len(orgnrs)} orgnrs from {filepath}")
        self.db.add_jobs(orgnrs, priority=priority)
        
        stats = self.db.get_job_stats()
        logger.info(f"Job queue: {stats}")
    
    async def load_jobs_from_scb(self, scb_file: str):
        """
        Load orgnrs from SCB Företagsregistret export.
        
        SCB provides company lists with status flags.
        We only want active Aktiebolag.
        """
        # Implementation depends on SCB file format
        # This is a placeholder
        pass
    
    async def run(self, max_jobs: int = None):
        """
        Run the scraper.
        
        Args:
            max_jobs: Stop after N jobs (for testing). None = run until queue empty.
        """
        self._running = True
        self._stats['start_time'] = datetime.utcnow()
        
        # Reset any stuck jobs from previous run
        self.db.reset_in_progress()
        
        jobs_processed = 0
        
        try:
            while self._running:
                # Get next job
                job = self.db.get_next_job()
                
                if not job:
                    logger.info("Job queue empty, scraping complete!")
                    break
                
                # Process job
                await self._process_job(job)
                
                jobs_processed += 1
                
                # Check max_jobs limit
                if max_jobs and jobs_processed >= max_jobs:
                    logger.info(f"Reached max_jobs limit ({max_jobs})")
                    break
                
                # Periodic stats
                if jobs_processed % 50 == 0:
                    self._log_progress()
                
                # Occasionally visit random page
                await self.session.maybe_random_page()
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self._running = False
            await self.session.close()
            self._log_progress()

            # Auto-update graph if enabled and we scraped any companies
            if self.auto_update_graph and self._stats['scraped'] > 0:
                await self._trigger_graph_update()
    
    async def _process_job(self, job: ScrapeJob):
        """Process a single scrape job."""
        # Use short URL format - site redirects to canonical URL with company name
        url = f"{self.config.base_url}/{job.orgnr}"
        
        try:
            # Make request
            response, response_time_ms = await self.session.request(url)
            
            # Log request
            self.db.log_request(
                orgnr=job.orgnr,
                success=True,
                status_code=response.status_code,
                response_time_ms=response_time_ms,
                proxy_session="direct",  # No proxy
            )
            
            if response.status_code == 200:
                # Parse
                html = response.text
                company = self.parser.parse_company_page(html, url)
                
                if company:
                    company.scraped_at = datetime.utcnow().isoformat()
                    self.db.save_company(company, response.content)
                    self.db.complete_job(job.orgnr, success=True)
                    self._stats['scraped'] += 1
                    logger.debug(f"Scraped: {company.name} ({job.orgnr})")
                else:
                    self.db.complete_job(job.orgnr, success=False, error="Parse failed")
                    self._stats['failed'] += 1
                    logger.warning(f"Parse failed for {job.orgnr}")
            
            elif response.status_code == 404:
                # Company doesn't exist or was removed
                self.db.complete_job(job.orgnr, success=True)  # Don't retry
                logger.debug(f"404 for {job.orgnr}")
            
            else:
                # Other error, might be temporary
                self.db.complete_job(job.orgnr, success=False, 
                                    error=f"HTTP {response.status_code}")
                self._stats['failed'] += 1
        
        except BlockDetectedError as e:
            # We're blocked, the session manager will handle cooldown
            self.db.mark_blocked(job.orgnr)
            self.db.log_block_event(
                proxy_session="direct",
                status_code=0,
                error_message=str(e),
                cooldown_hours=self.config.retry.block_cooldown_hours
            )
            self._stats['blocked'] += 1
            logger.error(f"Block detected while scraping {job.orgnr}")
        
        except Exception as e:
            self.db.complete_job(job.orgnr, success=False, error=str(e))
            self.db.log_request(
                orgnr=job.orgnr,
                success=False,
                status_code=0,
                response_time_ms=0,
                proxy_session="direct",
                error_type=type(e).__name__,
            )
            self._stats['failed'] += 1
            logger.error(f"Error scraping {job.orgnr}: {e}")
    
    def _log_progress(self):
        """Log current progress."""
        stats = self.db.get_job_stats()
        
        total = sum(stats.values())
        completed = stats.get('completed', 0)
        pending = stats.get('pending', 0)
        failed = stats.get('failed', 0)
        blocked = stats.get('blocked', 0)
        
        # Calculate rate
        if self._stats['start_time']:
            elapsed = (datetime.utcnow() - self._stats['start_time']).total_seconds()
            rate = self._stats['scraped'] / (elapsed / 3600) if elapsed > 0 else 0
        else:
            rate = 0
        
        # Calculate ETA
        if rate > 0:
            remaining = pending + failed
            eta_hours = remaining / rate
            eta_str = f"{eta_hours:.1f} hours"
        else:
            eta_str = "unknown"
        
        # Error rate
        error_rate = self.db.get_recent_error_rate(minutes=60)
        
        logger.info(
            f"Progress: {completed}/{total} ({100*completed/total:.1f}%) | "
            f"Rate: {rate:.0f}/hour | ETA: {eta_str} | "
            f"Failed: {failed} | Blocked: {blocked} | "
            f"Error rate (1h): {100*error_rate:.1f}%"
        )
    
    def stop(self):
        """Stop the scraper gracefully."""
        self._running = False
    
    async def run_priority_scrape(self, orgnrs: List[str]):
        """
        Scrape specific orgnrs with high priority.

        Use this for targeted scrapes of specific companies.
        """
        self.db.add_jobs(orgnrs, priority=100)  # High priority
        await self.run(max_jobs=len(orgnrs))

    async def _trigger_graph_update(self):
        """Trigger graph update after scraping completes."""
        logger.info("Triggering graph update with new data...")
        try:
            import subprocess
            import sys
            from pathlib import Path

            # Run the graph loader script
            script_path = Path(__file__).parent.parent / "scripts" / "load_allabolag.py"
            if script_path.exists():
                result = subprocess.run(
                    [sys.executable, str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode == 0:
                    logger.info("Graph update completed successfully")
                    # Log key stats from output
                    for line in result.stdout.split('\n'):
                        if 'companies_loaded' in line or 'Pattern Detection' in line:
                            logger.info(f"  {line.strip()}")
                else:
                    logger.error(f"Graph update failed: {result.stderr}")
            else:
                logger.warning(f"Graph loader script not found at {script_path}")

            # Also notify the pipeline orchestrator if running
            try:
                from halo.pipeline.orchestrator import PipelineOrchestrator
                orchestrator = PipelineOrchestrator()
                # Mark scraped orgnrs as ready for graph stage
                stats = self.db.get_job_stats()
                logger.info(f"Pipeline notified: {stats.get('completed', 0)} jobs completed")
            except ImportError:
                pass  # Pipeline module not available

        except Exception as e:
            logger.error(f"Graph update trigger failed: {e}")


async def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Allabolag.se Scraper')
    parser.add_argument('command', choices=['run', 'load', 'stats', 'reset'])
    parser.add_argument('--file', help='File with orgnrs (for load command)')
    parser.add_argument('--max', type=int, help='Max jobs to process')
    parser.add_argument('--priority', type=int, default=0, help='Priority for loaded jobs')
    
    args = parser.parse_args()
    
    config = ScraperConfig()
    scraper = AllabolagScraper(config)
    
    if args.command == 'load':
        if not args.file:
            print("--file required for load command")
            return
        await scraper.load_jobs_from_file(args.file, priority=args.priority)
    
    elif args.command == 'run':
        await scraper.run(max_jobs=args.max)
    
    elif args.command == 'stats':
        stats = scraper.db.get_job_stats()
        print(f"Job Queue Stats:")
        for status, count in sorted(stats.items()):
            print(f"  {status}: {count}")
        
        # Error rate
        error_rate = scraper.db.get_recent_error_rate()
        print(f"\nError rate (last hour): {100*error_rate:.1f}%")
        
        # Today's requests
        today = scraper.db.get_requests_today()
        print(f"Requests today: {today}")
    
    elif args.command == 'reset':
        scraper.db.reset_in_progress()
        print("Reset in_progress jobs to pending")


if __name__ == '__main__':
    asyncio.run(main())