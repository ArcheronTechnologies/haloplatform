"""
Demo API for Halo Intelligence Platform.

Minimal FastAPI serving detection results from precomputed data.
No auth, no database - just serves the intelligence results for demo purposes.
"""

import json
import pickle
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import networkx as nx

app = FastAPI(
    title="Halo Intelligence Demo",
    description="Shell company detection demo using real Swedish company data",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data"
GRAPH_PATH = DATA_DIR / "scb_graph.pickle"
RESULTS_PATH = DATA_DIR / "intelligence_results.json"

# Load data at startup
GRAPH: Optional[nx.MultiDiGraph] = None
RESULTS: Optional[dict] = None


def load_data():
    """Load graph and intelligence results."""
    global GRAPH, RESULTS

    if GRAPH_PATH.exists():
        with open(GRAPH_PATH, "rb") as f:
            GRAPH = pickle.load(f)
        print(f"Loaded graph: {GRAPH.number_of_nodes()} nodes, {GRAPH.number_of_edges()} edges")

    if RESULTS_PATH.exists():
        with open(RESULTS_PATH, "r") as f:
            RESULTS = json.load(f)
        print(f"Loaded results: {len(RESULTS.get('high_risk_companies', []))} high-risk companies")


@app.on_event("startup")
async def startup():
    load_data()


@app.get("/api/health")
def health():
    """Health check."""
    return {
        "status": "ok",
        "graph_loaded": GRAPH is not None,
        "results_loaded": RESULTS is not None,
    }


@app.get("/api/stats")
def get_stats():
    """Get summary statistics."""
    if not RESULTS:
        raise HTTPException(status_code=503, detail="Results not loaded")

    summary = RESULTS.get("summary", {})
    return {
        "total_companies": summary.get("total_companies", 0),
        "total_addresses": summary.get("total_addresses", 0),
        "high_risk_count": summary.get("high_risk_count", 0),
        "medium_risk_count": summary.get("medium_risk_count", 0),
        "suspicious_address_count": summary.get("suspicious_address_count", 0),
        "risk_distribution": summary.get("risk_distribution", {}),
    }


@app.get("/api/alerts")
def get_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity: high, medium, low"),
    limit: int = Query(50, ge=1, le=200),
):
    """Get detected alerts (high-risk companies and suspicious addresses)."""
    if not RESULTS:
        raise HTTPException(status_code=503, detail="Results not loaded")

    alerts = []

    # Add high-risk companies as alerts
    for company in RESULTS.get("high_risk_companies", []):
        alert = {
            "id": f"shell-{company['orgnr']}",
            "alert_type": "shell_company",
            "severity": company["risk_level"],
            "entity_id": company["company_id"],
            "entity_type": "Company",
            "title": f"Potential Shell Company: {company['name']}",
            "description": f"Shell score: {company['shell_score']:.0%}",
            "orgnr": company["orgnr"],
            "name": company["name"],
            "shell_score": company["shell_score"],
            "flags": company["flags"],
            "indicators": company["indicators"],
        }
        alerts.append(alert)

    # Add suspicious addresses as alerts
    for addr in RESULTS.get("suspicious_addresses", []):
        alert = {
            "id": f"addr-{addr['address_id']}",
            "alert_type": "registration_mill",
            "severity": "high" if addr["company_count"] >= 10 else "medium",
            "entity_id": addr["address_id"],
            "entity_type": "Address",
            "title": f"Registration Mill: {addr['company_count']} companies",
            "description": f"{addr['street']}, {addr['postal_code']} {addr['city']}",
            "company_count": addr["company_count"],
            "address": {
                "street": addr["street"],
                "postal_code": addr["postal_code"],
                "city": addr["city"],
            },
        }
        alerts.append(alert)

    # Filter by severity
    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]

    # Sort by severity (high first) then by shell_score
    severity_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: (severity_order.get(a["severity"], 3), -a.get("shell_score", 0)))

    return {"alerts": alerts[:limit], "total": len(alerts)}


@app.get("/api/alerts/{alert_id}")
def get_alert(alert_id: str):
    """Get single alert by ID."""
    alerts = get_alerts(limit=200)["alerts"]
    for alert in alerts:
        if alert["id"] == alert_id:
            return alert
    raise HTTPException(status_code=404, detail="Alert not found")


@app.get("/api/entities/{entity_id}")
def get_entity(entity_id: str):
    """Get entity details from graph."""
    if not GRAPH:
        raise HTTPException(status_code=503, detail="Graph not loaded")

    if entity_id not in GRAPH.nodes:
        raise HTTPException(status_code=404, detail="Entity not found")

    node_data = dict(GRAPH.nodes[entity_id])
    node_type = node_data.get("_type", "Unknown")

    # Get label based on type
    if node_type == "Company" or entity_id.startswith("company-"):
        names = node_data.get("names", [])
        label = names[0].get("name", entity_id) if names else entity_id
    elif node_type == "Address" or entity_id.startswith("address-"):
        normalized = node_data.get("normalized", {})
        label = f"{normalized.get('street', '')}, {normalized.get('city', '')}"
    else:
        label = entity_id

    return {
        "id": entity_id,
        "type": node_type or ("Company" if entity_id.startswith("company-") else "Address"),
        "label": label,
        "properties": node_data,
    }


@app.get("/api/entities/{entity_id}/network")
def get_entity_network(
    entity_id: str,
    hops: int = Query(2, ge=1, le=3, description="Network depth"),
):
    """Get network around an entity for visualization."""
    if not GRAPH:
        raise HTTPException(status_code=503, detail="Graph not loaded")

    if entity_id not in GRAPH.nodes:
        raise HTTPException(status_code=404, detail="Entity not found")

    nodes = []
    edges = []
    visited = set()

    def get_node_info(node_id: str) -> dict:
        """Extract node info for visualization."""
        data = dict(GRAPH.nodes[node_id])
        node_type = data.get("_type", "")

        if node_id.startswith("company-"):
            node_type = "Company"
            names = data.get("names", [])
            label = names[0].get("name", node_id[:20]) if names else node_id[:20]
            # Get shell score from results if available
            shell_score = 0
            if RESULTS:
                for company in RESULTS.get("high_risk_companies", []):
                    if company["company_id"] == node_id:
                        shell_score = company["shell_score"]
                        break
        elif node_id.startswith("address-"):
            node_type = "Address"
            normalized = data.get("normalized", {})
            label = normalized.get("street", node_id[:20]) or node_id[:20]
            shell_score = 0
        else:
            label = node_id[:20]
            shell_score = 0

        return {
            "id": node_id,
            "type": node_type,
            "label": label,
            "shellScore": shell_score,
            "riskScore": shell_score,
        }

    def expand(node_id: str, depth: int):
        """Recursively expand network."""
        if depth > hops or node_id in visited:
            return
        visited.add(node_id)

        nodes.append(get_node_info(node_id))

        # Get all edges (both directions)
        for u, v, edge_data in GRAPH.edges(node_id, data=True):
            edge_type = edge_data.get("_type", "").replace("Edge", "")
            edges.append({
                "source": u,
                "target": v,
                "type": edge_type,
            })
            if v not in visited:
                expand(v, depth + 1)

        # Also check incoming edges
        for u, v, edge_data in GRAPH.in_edges(node_id, data=True):
            edge_type = edge_data.get("_type", "").replace("Edge", "")
            edge_key = f"{u}-{v}"
            if not any(e["source"] == u and e["target"] == v for e in edges):
                edges.append({
                    "source": u,
                    "target": v,
                    "type": edge_type,
                })
            if u not in visited:
                expand(u, depth + 1)

    expand(entity_id, 0)

    return {
        "nodes": nodes,
        "edges": edges,
        "seed_entity_id": entity_id,
    }


@app.get("/api/companies")
def list_companies(
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
    limit: int = Query(100, ge=1, le=1000),
):
    """List companies with their risk scores."""
    if not GRAPH or not RESULTS:
        raise HTTPException(status_code=503, detail="Data not loaded")

    # Build company list from results
    all_results = RESULTS.get("all_results", [])

    if risk_level:
        all_results = [r for r in all_results if r["risk_level"] == risk_level]

    return {
        "companies": all_results[:limit],
        "total": len(all_results),
    }


@app.get("/api/sni-distribution")
def get_sni_distribution():
    """Get SNI code distribution."""
    if not RESULTS:
        raise HTTPException(status_code=503, detail="Results not loaded")

    return RESULTS.get("sni_distribution", {})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
