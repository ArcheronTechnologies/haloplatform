"""
Intelligence API routes.

Provides endpoints for the 3-layer fraud detection framework:
- Layer 1: Anomaly detection
- Layer 2: Pattern matching
- Layer 3: Predictive risk assessment
- Advanced: SAR generation, konkurs prediction, evasion detection
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from halo.api.deps import AuditRepo, User, AnalystUser
from halo.graph.client import GraphClient

router = APIRouter()


# Singleton instances (in production, use proper dependency injection)
_graph_client: Optional[GraphClient] = None


async def get_graph_client() -> GraphClient:
    """Get or create graph client."""
    global _graph_client
    if _graph_client is None:
        _graph_client = GraphClient()
    return _graph_client


GraphClientDep = Annotated[GraphClient, Depends(get_graph_client)]


# ============================================================================
# Response Models
# ============================================================================

class AnomalyScoreResponse(BaseModel):
    """Response for anomaly score."""
    entity_id: str
    entity_type: str
    composite_score: float
    is_anomalous: bool
    severity: str
    z_scores: dict[str, float] = Field(default_factory=dict)
    flags: list[dict] = Field(default_factory=list)


class PatternMatchResponse(BaseModel):
    """Response for pattern match."""
    pattern_id: str
    pattern_name: str
    severity: str
    typology: str
    entity_ids: list[str]
    match_data: dict
    detected_at: str


class FraudPredictionResponse(BaseModel):
    """Response for fraud prediction."""
    entity_id: str
    entity_type: str
    risk_level: str
    probability: float
    confidence: float
    rationale: str
    construction_signals: list[str] = Field(default_factory=list)
    recommended_action: Optional[str] = None


class SARResponse(BaseModel):
    """Response for SAR generation."""
    id: str
    subject_entity_id: str
    subject_name: Optional[str]
    sar_type: str
    status: str
    priority: str
    summary: Optional[str]
    trigger_reason: str
    created_by: Optional[str]
    sections: list[dict]


class KonkursPredictionResponse(BaseModel):
    """Response for konkurs prediction."""
    company_id: str
    konkurs_probability: float
    horizon_months: int
    risk_level: str
    confidence: float
    network_contagion_risk: float = 0.0
    director_risk_score: float = 0.0
    financial_health_score: float = 0.0
    distress_signals: list[str] = Field(default_factory=list)
    survival_signals: list[str] = Field(default_factory=list)


class EvasionScoreResponse(BaseModel):
    """Response for evasion detection."""
    entity_id: str
    entity_type: str
    evasion_probability: float
    evasion_level: str
    isolation_score: float = 0.0
    synthetic_compliance: bool = False
    structuring_detected: bool = False
    structuring_patterns: list[str] = Field(default_factory=list)
    rationale: Optional[str] = None


class PlaybookMatchResponse(BaseModel):
    """Response for playbook match."""
    playbook_id: str
    playbook_name: str
    severity: str
    confidence: float
    current_stage: int
    total_stages: int
    next_expected: Optional[str]
    matched_events: list[dict]
    entity_id: str
    alert: str


# ============================================================================
# Layer 1: Anomaly Detection
# ============================================================================

@router.get("/anomaly/address/{address_id}", response_model=AnomalyScoreResponse)
async def score_address_anomaly(
    address_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Score an address for statistical anomalies.

    Detects registration mills, high-density addresses, etc.
    """
    from halo.intelligence.anomaly import AnomalyDetector

    async with graph:
        detector = AnomalyDetector(graph_client=graph)
        score = await detector.score_address(address_id)

        # Log access
        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="analyze",
            resource_type="anomaly_address",
            resource_id=address_id,
            details={"is_anomalous": score.is_anomalous, "severity": score.severity},
        )

        return AnomalyScoreResponse(
            entity_id=score.entity_id,
            entity_type=score.entity_type,
            composite_score=score.composite_score,
            is_anomalous=score.is_anomalous,
            severity=score.severity,
            z_scores=score.z_scores,
            flags=score.flags,
        )


@router.get("/anomaly/company/{company_id}", response_model=AnomalyScoreResponse)
async def score_company_anomaly(
    company_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Score a company for statistical anomalies.

    Detects shell company indicators, unusual patterns, etc.
    """
    from halo.intelligence.anomaly import AnomalyDetector

    async with graph:
        detector = AnomalyDetector(graph_client=graph)
        score = await detector.score_company(company_id)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="analyze",
            resource_type="anomaly_company",
            resource_id=company_id,
            details={"is_anomalous": score.is_anomalous, "severity": score.severity},
        )

        return AnomalyScoreResponse(
            entity_id=score.entity_id,
            entity_type=score.entity_type,
            composite_score=score.composite_score,
            is_anomalous=score.is_anomalous,
            severity=score.severity,
            z_scores=score.z_scores,
            flags=score.flags,
        )


@router.get("/anomaly/person/{person_id}", response_model=AnomalyScoreResponse)
async def score_person_anomaly(
    person_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Score a person for statistical anomalies.

    Detects nominee directors, unusual directorship patterns, etc.
    """
    from halo.intelligence.anomaly import AnomalyDetector

    async with graph:
        detector = AnomalyDetector(graph_client=graph)
        score = await detector.score_person(person_id)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="analyze",
            resource_type="anomaly_person",
            resource_id=person_id,
            details={"is_anomalous": score.is_anomalous, "severity": score.severity},
        )

        return AnomalyScoreResponse(
            entity_id=score.entity_id,
            entity_type=score.entity_type,
            composite_score=score.composite_score,
            is_anomalous=score.is_anomalous,
            severity=score.severity,
            z_scores=score.z_scores,
            flags=score.flags,
        )


# ============================================================================
# Layer 2: Pattern Detection
# ============================================================================

@router.get("/patterns", response_model=list[dict])
async def list_fraud_patterns(
    user: User,
    enabled_only: bool = Query(True, description="Only return enabled patterns"),
):
    """
    List all available fraud detection patterns.
    """
    from halo.intelligence.patterns import FRAUD_PATTERNS

    patterns = []
    for pattern_id, pattern in FRAUD_PATTERNS.items():
        if enabled_only and not pattern.enabled:
            continue
        patterns.append({
            "id": pattern.id,
            "name": pattern.name,
            "description": pattern.description,
            "severity": pattern.severity,
            "typology": pattern.typology,
            "enabled": pattern.enabled,
        })

    return patterns


@router.get("/patterns/detect/{entity_id}", response_model=list[PatternMatchResponse])
async def detect_patterns_for_entity(
    entity_id: str,
    entity_type: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
    pattern_ids: Optional[str] = Query(None, description="Comma-separated pattern IDs to check"),
):
    """
    Detect fraud patterns for a specific entity.

    Runs graph-based pattern matching against the entity's network.
    """
    from halo.intelligence.patterns import PatternMatcher

    async with graph:
        matcher = PatternMatcher(graph)

        # Parse pattern filter
        filter_patterns = pattern_ids.split(",") if pattern_ids else None

        matches = await matcher.detect_for_entity(
            entity_id=entity_id,
            entity_type=entity_type,
            pattern_ids=filter_patterns,
        )

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="analyze",
            resource_type="pattern_detection",
            resource_id=entity_id,
            details={"matches_found": len(matches)},
        )

        return [
            PatternMatchResponse(
                pattern_id=m.pattern_id,
                pattern_name=m.pattern_name,
                severity=m.severity,
                typology=m.typology,
                entity_ids=m.entity_ids,
                match_data=m.match_data,
                detected_at=m.detected_at.isoformat(),
            )
            for m in matches
        ]


@router.post("/patterns/scan", response_model=list[PatternMatchResponse])
async def scan_all_patterns(
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: AnalystUser,
    background_tasks: BackgroundTasks,
    typology: Optional[str] = Query(None, description="Filter by typology"),
    min_severity: Optional[str] = Query(None, description="Minimum severity: low, medium, high, critical"),
):
    """
    Scan for all fraud patterns across the graph.

    Requires analyst role. Results may be returned asynchronously for large graphs.
    """
    from halo.intelligence.patterns import PatternMatcher

    async with graph:
        matcher = PatternMatcher(graph)
        matches = await matcher.detect_all()

        # Filter by typology
        if typology:
            matches = [m for m in matches if m.typology == typology]

        # Filter by severity
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        if min_severity and min_severity in severity_order:
            min_level = severity_order[min_severity]
            matches = [m for m in matches if severity_order.get(m.severity, 0) >= min_level]

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="scan",
            resource_type="pattern_scan",
            resource_id="global",
            details={"matches_found": len(matches), "typology": typology},
        )

        return [
            PatternMatchResponse(
                pattern_id=m.pattern_id,
                pattern_name=m.pattern_name,
                severity=m.severity,
                typology=m.typology,
                entity_ids=m.entity_ids,
                match_data=m.match_data,
                detected_at=m.detected_at.isoformat(),
            )
            for m in matches
        ]


# ============================================================================
# Layer 3: Predictive Risk
# ============================================================================

@router.get("/predict/{entity_id}", response_model=FraudPredictionResponse)
async def predict_fraud_risk(
    entity_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Predict fraud risk for an entity.

    Uses ML-based risk prediction with construction signal detection.
    """
    from halo.intelligence.predictive import RiskPredictor

    async with graph:
        predictor = RiskPredictor(graph_client=graph)
        prediction = await predictor.predict(entity_id)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="predict",
            resource_type="fraud_risk",
            resource_id=entity_id,
            details={"risk_level": prediction.risk_level, "probability": prediction.probability},
        )

        return FraudPredictionResponse(
            entity_id=prediction.entity_id,
            entity_type=prediction.entity_type,
            risk_level=prediction.risk_level,
            probability=prediction.probability,
            confidence=prediction.confidence,
            rationale=prediction.rationale,
            construction_signals=prediction.construction_signals,
            recommended_action=prediction.recommended_action,
        )


@router.post("/predict/batch", response_model=list[FraudPredictionResponse])
async def predict_fraud_risk_batch(
    entity_ids: list[str],
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """
    Predict fraud risk for multiple entities.

    Requires analyst role. Maximum 100 entities per request.
    """
    if len(entity_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 entities per batch")

    from halo.intelligence.predictive import RiskPredictor

    async with graph:
        predictor = RiskPredictor(graph_client=graph)
        predictions = await predictor.predict_batch(entity_ids)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="predict_batch",
            resource_type="fraud_risk",
            resource_id="batch",
            details={"count": len(entity_ids)},
        )

        return [
            FraudPredictionResponse(
                entity_id=p.entity_id,
                entity_type=p.entity_type,
                risk_level=p.risk_level,
                probability=p.probability,
                confidence=p.confidence,
                rationale=p.rationale,
                construction_signals=p.construction_signals,
                recommended_action=p.recommended_action,
            )
            for p in predictions
        ]


@router.get("/predict/{entity_id}/explain", response_model=dict)
async def explain_prediction(
    entity_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Get detailed explanation of a fraud prediction.

    Returns human-readable explanation with recommended actions.
    """
    from halo.intelligence.predictive import RiskPredictor

    async with graph:
        predictor = RiskPredictor(graph_client=graph)
        prediction = await predictor.predict(entity_id)
        explanation = await predictor.explain_prediction(entity_id, prediction)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="explain",
            resource_type="fraud_prediction",
            resource_id=entity_id,
        )

        return explanation


# ============================================================================
# Advanced: SAR Generation
# ============================================================================

class SARRequest(BaseModel):
    """Request for SAR generation."""
    entity_id: str
    trigger_reason: str
    alert_ids: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


@router.post("/sar/generate", response_model=SARResponse)
async def generate_sar(
    request: SARRequest,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: AnalystUser,
):
    """
    Generate a Suspicious Activity Report (SAR).

    Requires analyst role. Creates structured report with all relevant data.
    """
    from halo.intelligence.sar_generator import SARGenerator

    async with graph:
        generator = SARGenerator(graph_client=graph)
        sar = await generator.generate_sar(
            entity_id=request.entity_id,
            trigger_reason=request.trigger_reason,
            alert_ids=request.alert_ids,
            created_by=user.username,
        )

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="generate",
            resource_type="sar",
            resource_id=sar.id,
            details={"entity_id": request.entity_id, "priority": sar.priority},
        )

        return SARResponse(
            id=sar.id,
            subject_entity_id=sar.subject_entity_id,
            subject_name=sar.subject_name,
            sar_type=sar.sar_type,
            status=sar.status,
            priority=sar.priority,
            summary=sar.summary,
            trigger_reason=sar.trigger_reason,
            created_by=sar.created_by,
            sections=[s.to_dict() for s in sar.sections],
        )


# ============================================================================
# Advanced: Konkurs Prediction
# ============================================================================

@router.get("/konkurs/{company_id}", response_model=KonkursPredictionResponse)
async def predict_konkurs(
    company_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
    horizon_months: int = Query(12, ge=6, le=36, description="Prediction horizon in months"),
):
    """
    Predict bankruptcy probability for a company.

    Uses network-based features including contagion risk.
    """
    from halo.intelligence.konkurs import KonkursPredictor

    async with graph:
        predictor = KonkursPredictor(graph_client=graph)
        prediction = await predictor.predict(company_id, horizon_months=horizon_months)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="predict",
            resource_type="konkurs",
            resource_id=company_id,
            details={"probability": prediction.konkurs_probability, "risk_level": prediction.risk_level},
        )

        return KonkursPredictionResponse(
            company_id=prediction.company_id,
            konkurs_probability=prediction.konkurs_probability,
            horizon_months=prediction.horizon_months,
            risk_level=prediction.risk_level,
            confidence=prediction.confidence,
            network_contagion_risk=prediction.network_contagion_risk,
            director_risk_score=prediction.director_risk_score,
            financial_health_score=prediction.financial_health_score,
            distress_signals=prediction.distress_signals,
            survival_signals=prediction.survival_signals,
        )


@router.get("/konkurs/{company_id}/contagion", response_model=dict)
async def analyze_contagion_risk(
    company_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Analyze bankruptcy contagion risk in the company's network.

    Shows how a potential bankruptcy would affect connected entities.
    """
    from halo.intelligence.konkurs import KonkursPredictor

    async with graph:
        predictor = KonkursPredictor(graph_client=graph)
        result = await predictor.analyze_contagion_risk(company_id)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="analyze",
            resource_type="contagion_risk",
            resource_id=company_id,
        )

        return result


# ============================================================================
# Advanced: Evasion Detection
# ============================================================================

@router.get("/evasion/{entity_id}", response_model=EvasionScoreResponse)
async def detect_evasion(
    entity_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Detect evasion behaviors for an entity.

    Identifies attempts to avoid detection through isolation, synthetic compliance, or structuring.
    """
    from halo.intelligence.evasion import EvasionDetector

    async with graph:
        detector = EvasionDetector(graph_client=graph)
        score = await detector.analyze(entity_id)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="analyze",
            resource_type="evasion",
            resource_id=entity_id,
            details={"evasion_level": score.evasion_level},
        )

        return EvasionScoreResponse(
            entity_id=score.entity_id,
            entity_type=score.entity_type,
            evasion_probability=score.evasion_probability,
            evasion_level=score.evasion_level,
            isolation_score=score.isolation_score,
            synthetic_compliance=score.synthetic_compliance,
            structuring_detected=score.structuring_detected,
            structuring_patterns=score.structuring_patterns,
            rationale=score.rationale,
        )


# ============================================================================
# Advanced: Playbook Detection
# ============================================================================

@router.get("/playbooks", response_model=list[dict])
async def list_fraud_playbooks(
    user: User,
):
    """
    List all available fraud playbooks (sequence patterns).
    """
    from halo.intelligence.sequence_detector import PLAYBOOKS

    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "severity": p.severity,
            "typology": p.typology,
            "stages": len(p.sequence),
            "time_window_days": p.time_window_days,
        }
        for p in PLAYBOOKS.values()
    ]


@router.get("/playbooks/detect/{entity_id}", response_model=list[PlaybookMatchResponse])
async def detect_playbooks(
    entity_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
):
    """
    Detect if an entity is following known fraud playbooks.

    Returns matches with current stage and next expected actions.
    """
    from halo.intelligence.sequence_detector import FraudSequenceDetector

    async with graph:
        detector = FraudSequenceDetector(graph_client=graph)
        matches = await detector.detect_playbook(entity_id)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="analyze",
            resource_type="playbook_detection",
            resource_id=entity_id,
            details={"matches_found": len(matches)},
        )

        return [
            PlaybookMatchResponse(
                playbook_id=m.playbook_id,
                playbook_name=m.playbook_name,
                severity=m.severity,
                confidence=m.confidence,
                current_stage=m.current_stage,
                total_stages=m.total_stages,
                next_expected=m.next_expected,
                matched_events=m.matched_events,
                entity_id=m.entity_id,
                alert=m.alert,
            )
            for m in matches
        ]


# ============================================================================
# Network Risk Analysis
# ============================================================================

@router.get("/network-risk/{entity_id}", response_model=dict)
async def analyze_network_risk(
    entity_id: str,
    graph: GraphClientDep,
    audit_repo: AuditRepo,
    user: User,
    hops: int = Query(2, ge=1, le=4, description="Network depth for analysis"),
):
    """
    Analyze network-level risk around an entity.

    Includes risk propagation and high-risk entity identification.
    """
    from halo.intelligence.predictive import NetworkRiskAnalyzer

    async with graph:
        analyzer = NetworkRiskAnalyzer(graph)
        result = await analyzer.analyze_network_risk(entity_id, hops=hops)

        await audit_repo.log(
            user_id=user.id,
            user_name=user.username,
            action="analyze",
            resource_type="network_risk",
            resource_id=entity_id,
            details={"network_size": result.get("network_size", 0)},
        )

        return result
