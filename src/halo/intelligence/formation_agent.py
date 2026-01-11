"""
Formation Agent Intelligence.

Track who forms companies and their outcome rates.
The formation agent is often the common thread across fraud networks.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from halo.graph.client import GraphClient


@dataclass
class FormationAgentScore:
    """Score and statistics for a formation agent."""
    agent_id: str
    agent_name: str
    agent_type: str  # lawyer, accountant, company_service_provider, individual

    # Statistics
    companies_formed: int = 0
    active_companies: int = 0
    dissolved_companies: int = 0
    konkurs_companies: int = 0

    # Outcome rates
    konkurs_rate_2y: float = 0.0  # % that went bankrupt within 2 years
    dissolved_rate_2y: float = 0.0  # % dissolved within 2 years
    shell_score_avg: float = 0.0  # average shell company score
    pattern_match_rate: float = 0.0  # % matching fraud patterns

    # Risk assessment
    bad_outcome_rate: float = 0.0
    suspicion_level: str = "low"  # low, medium, high
    alert: Optional[str] = None

    # Metadata
    first_formation: Optional[datetime] = None
    last_formation: Optional[datetime] = None
    computed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "companies_formed": self.companies_formed,
            "active_companies": self.active_companies,
            "dissolved_companies": self.dissolved_companies,
            "konkurs_companies": self.konkurs_companies,
            "konkurs_rate_2y": self.konkurs_rate_2y,
            "dissolved_rate_2y": self.dissolved_rate_2y,
            "shell_score_avg": self.shell_score_avg,
            "pattern_match_rate": self.pattern_match_rate,
            "bad_outcome_rate": self.bad_outcome_rate,
            "suspicion_level": self.suspicion_level,
            "alert": self.alert,
        }


class FormationAgentTracker:
    """
    Track formation agents (lawyers, accountants, company service providers).

    The formation agent is often the common thread across fraud networks.
    Scoring formation agents by their outcomes helps identify enablers.
    """

    def __init__(self, graph_client: Optional[GraphClient] = None):
        self.graph = graph_client

    async def score_formation_agent(self, agent_id: str) -> FormationAgentScore:
        """
        Score a formation agent based on outcomes of companies they formed.
        """
        # Get agent info
        agent_info = await self._get_agent_info(agent_id)
        agent_name = agent_info.get("name", "Unknown")
        agent_type = agent_info.get("type", "unknown")

        # Get companies formed by this agent
        companies = await self._get_companies_formed_by(agent_id)

        if not companies:
            return FormationAgentScore(
                agent_id=agent_id,
                agent_name=agent_name,
                agent_type=agent_type,
                companies_formed=0
            )

        # Calculate outcomes
        total = len(companies)
        konkurs_2y = 0
        dissolved_2y = 0
        shell_high = 0
        pattern_matches = 0
        active = 0
        dissolved = 0
        konkurs = 0
        shell_scores = []

        formation_dates = []

        for company in companies:
            company_id = company.get("id")
            formation_date = company.get("formation", {}).get("date")
            status = company.get("status", {}).get("code", "")

            if formation_date:
                try:
                    if isinstance(formation_date, str):
                        from datetime import date
                        formation_date = date.fromisoformat(formation_date)
                    formation_dates.append(formation_date)
                except (ValueError, TypeError):
                    pass

            # Count statuses
            if status.lower() in ("active", "aktiv"):
                active += 1
            elif status.lower() in ("dissolved", "avregistrerad", "upplöst"):
                dissolved += 1
            elif status.lower() in ("konkurs", "bankrupt"):
                konkurs += 1

            # Check outcomes within 2 years
            if await self._konkurs_within(company_id, years=2):
                konkurs_2y += 1

            if await self._dissolved_within(company_id, years=2):
                dissolved_2y += 1

            # Shell company score
            shell_score = company.get("shell_score", 0.0)
            shell_scores.append(shell_score)
            if shell_score > 0.7:
                shell_high += 1

            # Pattern matches
            if await self._matches_fraud_pattern(company_id):
                pattern_matches += 1

        # Calculate rates
        konkurs_rate_2y = konkurs_2y / total if total > 0 else 0.0
        dissolved_rate_2y = dissolved_2y / total if total > 0 else 0.0
        shell_score_avg = sum(shell_scores) / len(shell_scores) if shell_scores else 0.0
        pattern_match_rate = pattern_matches / total if total > 0 else 0.0

        # Calculate weighted bad outcome rate
        bad_outcome_rate = (
            konkurs_2y * 2 +
            dissolved_2y +
            shell_high +
            pattern_matches * 2
        ) / (total * 2) if total > 0 else 0.0

        # Determine suspicion level
        if bad_outcome_rate > 0.4:
            suspicion_level = "high"
        elif bad_outcome_rate > 0.2:
            suspicion_level = "medium"
        else:
            suspicion_level = "low"

        # Generate alert if warranted
        alert = None
        if bad_outcome_rate > 0.3:
            alert = f"Formation agent with {bad_outcome_rate:.0%} bad outcome rate"
        elif total > 50 and konkurs_rate_2y > 0.15:
            alert = f"High-volume agent with {konkurs_rate_2y:.0%} bankruptcy rate"
        elif pattern_match_rate > 0.3:
            alert = f"Agent's companies frequently match fraud patterns ({pattern_match_rate:.0%})"

        # Get formation date range
        first_formation = min(formation_dates) if formation_dates else None
        last_formation = max(formation_dates) if formation_dates else None

        return FormationAgentScore(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=agent_type,
            companies_formed=total,
            active_companies=active,
            dissolved_companies=dissolved,
            konkurs_companies=konkurs,
            konkurs_rate_2y=konkurs_rate_2y,
            dissolved_rate_2y=dissolved_rate_2y,
            shell_score_avg=shell_score_avg,
            pattern_match_rate=pattern_match_rate,
            bad_outcome_rate=bad_outcome_rate,
            suspicion_level=suspicion_level,
            alert=alert,
            first_formation=datetime.combine(first_formation, datetime.min.time()) if first_formation else None,
            last_formation=datetime.combine(last_formation, datetime.min.time()) if last_formation else None,
        )

    async def find_suspicious_agents(
        self,
        min_companies: int = 10,
        min_bad_rate: float = 0.2
    ) -> list[FormationAgentScore]:
        """
        Find formation agents with suspicious outcome rates.
        """
        agent_ids = await self._get_all_formation_agents()
        suspicious = []

        for agent_id in agent_ids:
            score = await self.score_formation_agent(agent_id)

            if (score.companies_formed >= min_companies and
                score.bad_outcome_rate >= min_bad_rate):
                suspicious.append(score)

        # Sort by bad outcome rate
        suspicious.sort(key=lambda x: x.bad_outcome_rate, reverse=True)
        return suspicious

    async def get_agent_network(self, agent_id: str) -> dict:
        """
        Get the network of companies and persons connected to a formation agent.
        """
        companies = await self._get_companies_formed_by(agent_id)
        company_ids = [c.get("id") for c in companies if c.get("id")]

        if not company_ids or not self.graph:
            return {
                "agent_id": agent_id,
                "companies": companies,
                "network": {"nodes": {}, "edges": []}
            }

        # Expand network from all companies
        network = await self.graph.expand_network(company_ids, hops=1)

        return {
            "agent_id": agent_id,
            "companies": companies,
            "network": network
        }

    async def compare_agents(
        self,
        agent_ids: list[str]
    ) -> list[FormationAgentScore]:
        """
        Compare multiple formation agents.
        """
        scores = []
        for agent_id in agent_ids:
            score = await self.score_formation_agent(agent_id)
            scores.append(score)

        # Sort by bad outcome rate
        scores.sort(key=lambda x: x.bad_outcome_rate, reverse=True)
        return scores

    # Helper methods

    async def _get_agent_info(self, agent_id: str) -> dict:
        """Get formation agent info."""
        if self.graph:
            # Try person
            person = await self.graph.get_person(agent_id)
            if person:
                return {
                    "name": person.get("display_name", "Unknown"),
                    "type": "individual"
                }
            # Try company (law firm, accounting firm)
            company = await self.graph.get_company(agent_id)
            if company:
                return {
                    "name": company.get("display_name", "Unknown"),
                    "type": "company_service_provider"
                }
        return {"name": "Unknown", "type": "unknown"}

    async def _get_companies_formed_by(self, agent_id: str) -> list[dict]:
        """Get all companies formed by this agent."""
        if self.graph:
            # Query for companies where formation.agent = agent_id
            query = """
            MATCH (c:Company)
            WHERE c.formation.agent = $agent_id
            RETURN c
            """
            try:
                results = await self.graph.execute_cypher(query, {"agent_id": agent_id})
                return [r.get("c", {}) for r in results]
            except Exception:
                pass
        return []

    async def _get_all_formation_agents(self) -> list[str]:
        """Get all formation agent IDs."""
        if self.graph:
            query = """
            MATCH (c:Company)
            WHERE c.formation.agent IS NOT NULL
            RETURN DISTINCT c.formation.agent as agent_id
            """
            try:
                results = await self.graph.execute_cypher(query)
                return [r.get("agent_id") for r in results if r.get("agent_id")]
            except Exception:
                pass
        return []

    async def _konkurs_within(self, company_id: str, years: int) -> bool:
        """Check if company went bankrupt within N years of formation."""
        if self.graph:
            company = await self.graph.get_company(company_id)
            if company:
                status = company.get("status", {})
                if status.get("code", "").lower() in ("konkurs", "bankrupt"):
                    # Check if bankruptcy was within N years
                    formation = company.get("formation", {}).get("date")
                    status_from = status.get("from")
                    if formation and status_from:
                        try:
                            from datetime import date
                            if isinstance(formation, str):
                                formation = date.fromisoformat(formation)
                            if isinstance(status_from, str):
                                status_from = date.fromisoformat(status_from)
                            return (status_from - formation).days < (years * 365)
                        except (ValueError, TypeError):
                            pass
        return False

    async def _dissolved_within(self, company_id: str, years: int) -> bool:
        """Check if company was dissolved within N years of formation."""
        if self.graph:
            company = await self.graph.get_company(company_id)
            if company:
                status = company.get("status", {})
                if status.get("code", "").lower() in ("dissolved", "avregistrerad", "upplöst"):
                    formation = company.get("formation", {}).get("date")
                    status_from = status.get("from")
                    if formation and status_from:
                        try:
                            from datetime import date
                            if isinstance(formation, str):
                                formation = date.fromisoformat(formation)
                            if isinstance(status_from, str):
                                status_from = date.fromisoformat(status_from)
                            return (status_from - formation).days < (years * 365)
                        except (ValueError, TypeError):
                            pass
        return False

    async def _matches_fraud_pattern(self, company_id: str) -> bool:
        """Check if company matches any fraud patterns."""
        # Would integrate with PatternMatcher
        return False
