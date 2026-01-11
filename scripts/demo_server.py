#!/usr/bin/env python3
"""
Demo API server for Week 3 UI demo.

Serves real extracted data from the intelligence pipeline.
"""

import json
import pickle
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data"
GRAPH_PATH = DATA_DIR / "company_graph.pickle"
ALERTS_PATH = DATA_DIR / "alerts.json"
RESULTS_PATH = DATA_DIR / "intelligence_results.json"
EXTRACTION_PATH = DATA_DIR / "extraction_combined" / "results.json"
SCB_RESULTS_PATH = DATA_DIR / "scb_enrichment.json"

# Load data at startup
graph = None
alerts = []
intelligence_results = {}
companies = []
scb_results = {}


def load_data():
    global graph, alerts, intelligence_results, companies, scb_results

    if GRAPH_PATH.exists():
        with open(GRAPH_PATH, "rb") as f:
            graph = pickle.load(f)
        print(f"Loaded graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    if ALERTS_PATH.exists():
        with open(ALERTS_PATH) as f:
            alerts = json.load(f)
        print(f"Loaded {len(alerts)} alerts")

    if RESULTS_PATH.exists():
        with open(RESULTS_PATH) as f:
            intelligence_results = json.load(f)
        print(f"Loaded intelligence results")

    if EXTRACTION_PATH.exists():
        with open(EXTRACTION_PATH) as f:
            companies = json.load(f)
        print(f"Loaded {len(companies)} companies")

    if SCB_RESULTS_PATH.exists():
        with open(SCB_RESULTS_PATH) as f:
            scb_results = json.load(f)
        print(f"Loaded SCB enrichment data")


# ========== Dashboard Stats ==========

@app.route("/api/dashboard/stats")
def dashboard_stats():
    high_alerts = len([a for a in alerts if a.get("severity") == "high"])
    return jsonify({
        "alerts": {
            "total": len(alerts),
            "new_today": high_alerts,
        },
        "cases": {
            "open": 3,
            "total": 5,
        },
        "entities": {
            "high_risk": intelligence_results.get("patterns", {}).get("serial_directors", 0),
            "new_this_week": len(companies),
        },
        "sars": {
            "draft": 0,
            "pending": 0,
            "submitted_this_month": 0,
        },
    })


@app.route("/api/dashboard/recent-alerts")
def recent_alerts():
    limit = request.args.get("limit", 5, type=int)
    formatted = []
    for alert in alerts[:limit]:
        formatted.append({
            "id": alert["id"],
            "title": alert["description"],
            "description": f"Pattern: {alert['alert_type']}",
            "severity": alert["severity"],
            "status": "open",
            "created_at": alert["created_at"],
        })
    return jsonify(formatted)


@app.route("/api/dashboard/recent-cases")
def recent_cases():
    return jsonify([
        {
            "id": "case-1",
            "case_number": "CASE-2025-001",
            "title": "Serial Director Investigation",
            "priority": "high",
            "status": "open",
        },
        {
            "id": "case-2",
            "case_number": "CASE-2025-002",
            "title": "Shell Network Analysis",
            "priority": "medium",
            "status": "in_progress",
        },
    ])


# ========== Alerts ==========

@app.route("/api/alerts")
def list_alerts():
    status = request.args.get("status")
    risk_level = request.args.get("risk_level")
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 20, type=int)

    filtered = alerts
    if status and status != "all":
        filtered = [a for a in filtered if a.get("status", "open") == status]
    if risk_level and risk_level != "all":
        filtered = [a for a in filtered if a.get("severity") == risk_level]

    start = (page - 1) * limit
    end = start + limit

    items = []
    for alert in filtered[start:end]:
        items.append({
            "id": alert["id"],
            "alert_type": alert["alert_type"],
            "description": alert["description"],
            "risk_level": alert["severity"],
            "status": "open",
            "entity_id": alert.get("entity_id"),
            "entity_type": alert.get("entity_type"),
            "created_at": alert["created_at"],
        })

    return jsonify({
        "items": items,
        "total": len(filtered),
        "page": page,
        "limit": limit,
    })


@app.route("/api/alerts/<alert_id>")
def get_alert(alert_id):
    for alert in alerts:
        if alert["id"] == alert_id:
            return jsonify({
                **alert,
                "risk_level": alert["severity"],
                "status": "open",
            })
    return jsonify({"error": "Not found"}), 404


# ========== Entities ==========

@app.route("/api/entities")
def list_entities():
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 20, type=int)
    entity_type = request.args.get("type")

    entities = []

    if graph:
        for node_id in graph.nodes():
            node_data = dict(graph.nodes[node_id])
            node_type = node_data.get("_type", "Unknown")

            if entity_type and node_type.lower() != entity_type.lower():
                continue

            names = node_data.get("names", [])
            name = names[0].get("name", "Unknown") if names else "Unknown"

            entities.append({
                "id": node_id,
                "type": node_type,
                "name": name,
                "orgnr": node_data.get("orgnr"),
                "risk_score": node_data.get("risk_score", 0),
                "shell_score": node_data.get("shell_score", 0),
            })

    start = (page - 1) * limit
    end = start + limit

    return jsonify({
        "items": entities[start:end],
        "total": len(entities),
        "page": page,
        "limit": limit,
    })


@app.route("/api/entities/<entity_id>")
def get_entity(entity_id):
    if not graph or entity_id not in graph.nodes:
        return jsonify({"error": "Not found"}), 404

    node_data = dict(graph.nodes[entity_id])
    names = node_data.get("names", [])
    name = names[0].get("name", "Unknown") if names else "Unknown"

    return jsonify({
        "id": entity_id,
        "type": node_data.get("_type", "Unknown"),
        "name": name,
        "orgnr": node_data.get("orgnr"),
        "risk_score": node_data.get("risk_score", 0),
        "shell_score": node_data.get("shell_score", 0),
        "data": node_data,
    })


# ========== Graph Network ==========

@app.route("/api/graph/entities/<entity_id>/network")
def get_network(entity_id):
    """Get subgraph around an entity."""
    if not graph:
        return jsonify({"nodes": [], "edges": []})

    hops = request.args.get("hops", 2, type=int)
    max_nodes = request.args.get("max_nodes", 50, type=int)

    # BFS to find neighbors within hops
    visited = {entity_id}
    current_layer = {entity_id}

    for _ in range(hops):
        next_layer = set()
        for node in current_layer:
            for neighbor in graph.neighbors(node):
                if neighbor not in visited and len(visited) < max_nodes:
                    visited.add(neighbor)
                    next_layer.add(neighbor)
            for predecessor in graph.predecessors(node):
                if predecessor not in visited and len(visited) < max_nodes:
                    visited.add(predecessor)
                    next_layer.add(predecessor)
        current_layer = next_layer

    # Build nodes and edges
    nodes = []
    for node_id in visited:
        node_data = dict(graph.nodes[node_id])
        names = node_data.get("names", [])
        name = names[0].get("name", "Unknown") if names else node_id

        nodes.append({
            "id": node_id,
            "type": node_data.get("_type", "Unknown"),
            "label": name[:30],
            "riskScore": node_data.get("risk_score", 0),
            "shellScore": node_data.get("shell_score", 0),
        })

    edges = []
    for u, v, data in graph.edges(data=True):
        if u in visited and v in visited:
            edges.append({
                "source": u,
                "target": v,
                "type": data.get("_type", ""),
                "label": data.get("role", ""),
            })

    return jsonify({
        "nodes": nodes,
        "edges": edges,
    })


@app.route("/api/graph/full")
def get_full_graph():
    """Get the full graph for network visualization."""
    if not graph:
        return jsonify({"nodes": [], "edges": [], "stats": {}, "clusters": []})

    max_nodes = request.args.get("max_nodes", 500, type=int)
    min_shell_score = request.args.get("min_shell_score", 0, type=float)
    mode = request.args.get("mode", "connected")  # connected, all, high_risk

    # Calculate node degrees for prioritization
    node_degrees = {}
    for node_id in graph.nodes():
        node_degrees[node_id] = graph.degree(node_id)

    # Build candidate list based on mode
    candidates = []
    for node_id, node_data in graph.nodes(data=True):
        node_type = node_data.get("_type", "Unknown")
        shell_score = node_data.get("shell_score", 0) or 0
        degree = node_degrees.get(node_id, 0)

        # Filter by shell score if specified
        if min_shell_score > 0 and node_type == "Company" and shell_score < min_shell_score:
            continue

        # Calculate priority score
        if mode == "connected":
            # Prioritize nodes with connections
            priority = degree * 10 + shell_score * 5
        elif mode == "high_risk":
            # Prioritize high shell scores
            priority = shell_score * 100 + degree
        else:
            priority = 0

        candidates.append((node_id, node_data, priority, degree, shell_score))

    # Sort by priority (highest first)
    candidates.sort(key=lambda x: x[2], reverse=True)

    # Select top nodes
    selected_ids = set()
    nodes = []

    for node_id, node_data, priority, degree, shell_score in candidates:
        if len(nodes) >= max_nodes:
            break

        # In connected mode, skip isolated nodes unless we need more
        if mode == "connected" and degree == 0 and len(nodes) < max_nodes * 0.8:
            continue

        names = node_data.get("names", [])
        name = names[0].get("name", "Unknown") if names else node_id

        nodes.append({
            "id": node_id,
            "type": node_data.get("_type", "Unknown"),
            "label": name[:30] if len(name) > 30 else name,
            "riskScore": node_data.get("risk_score", 0) or 0,
            "shellScore": shell_score,
            "degree": degree,
        })
        selected_ids.add(node_id)

    # Get edges between selected nodes
    edges = []
    for u, v, data in graph.edges(data=True):
        if u in selected_ids and v in selected_ids:
            edges.append({
                "source": u,
                "target": v,
                "type": data.get("_type", ""),
                "label": data.get("role", ""),
            })

    # Find clusters (connected components in the subgraph)
    from collections import defaultdict

    adjacency = defaultdict(set)
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])

    visited = set()
    clusters = []

    def bfs_cluster(start):
        cluster_nodes = []
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            cluster_nodes.append(node)
            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    queue.append(neighbor)
        return cluster_nodes

    for node in selected_ids:
        if node not in visited:
            cluster = bfs_cluster(node)
            if len(cluster) > 1:  # Only include connected clusters
                # Calculate cluster stats
                cluster_shell_scores = [
                    n["shellScore"] for n in nodes if n["id"] in cluster
                ]
                cluster_types = [
                    n["type"] for n in nodes if n["id"] in cluster
                ]
                clusters.append({
                    "id": f"cluster-{len(clusters)}",
                    "nodes": cluster,
                    "size": len(cluster),
                    "avgShellScore": sum(cluster_shell_scores) / len(cluster_shell_scores) if cluster_shell_scores else 0,
                    "maxShellScore": max(cluster_shell_scores) if cluster_shell_scores else 0,
                    "companyCount": cluster_types.count("Company"),
                    "personCount": cluster_types.count("Person"),
                })

    # Sort clusters by risk (max shell score, then size)
    clusters.sort(key=lambda c: (c["maxShellScore"], c["size"]), reverse=True)

    # Add cluster ID to nodes
    node_to_cluster = {}
    for cluster in clusters:
        for node_id in cluster["nodes"]:
            node_to_cluster[node_id] = cluster["id"]

    for node in nodes:
        node["clusterId"] = node_to_cluster.get(node["id"])

    # Stats
    total_companies = sum(1 for _, d in graph.nodes(data=True) if d.get("_type") == "Company")
    total_persons = sum(1 for _, d in graph.nodes(data=True) if d.get("_type") == "Person")
    connected_nodes = sum(1 for n in nodes if n.get("degree", 0) > 0)

    return jsonify({
        "nodes": nodes,
        "edges": edges,
        "clusters": clusters[:20],  # Top 20 clusters
        "stats": {
            "total_nodes": graph.number_of_nodes(),
            "total_edges": graph.number_of_edges(),
            "displayed_nodes": len(nodes),
            "displayed_edges": len(edges),
            "connected_nodes": connected_nodes,
            "cluster_count": len([c for c in clusters if c["size"] > 1]),
            "total_companies": total_companies,
            "total_persons": total_persons,
        }
    })


# ========== Demo-specific endpoints ==========

@app.route("/api/demo/summary")
def demo_summary():
    """Get demo summary stats."""
    # Pattern data is stored as top-level lists, not nested under "patterns"
    serial_directors = intelligence_results.get("serial_directors", [])
    shell_networks = intelligence_results.get("shell_networks", [])
    shared_directors = intelligence_results.get("shared_directors", [])

    scb_patterns = scb_results.get("patterns", {})
    scb_stats = scb_results.get("stats", {})

    return jsonify({
        "companies": len(companies),
        "persons": sum(1 for n in graph.nodes() if n.startswith("person-")) if graph else 0,
        "edges": graph.number_of_edges() if graph else 0,
        "alerts": len(alerts),
        "serial_directors": len(serial_directors),
        "shell_networks": len(shell_networks),
        "role_concentrations": len(shared_directors),
        "circular_directors": 0,  # Not yet computed
        "new_companies_many_directors": 0,  # Not yet computed
        "dormant_reactivations": 0,  # Not yet computed
        "top_serial_directors": serial_directors[:5],
        "top_shell_networks": shell_networks[:3],
        "top_role_concentrations": shared_directors[:5],
        "top_circular_directors": [],
        "top_new_companies_many_directors": [],
        # SCB enrichment data
        "scb_enriched": scb_stats.get("companies_enriched", 0) > 0,
        "scb_stats": {
            "f_skatt_registered": scb_stats.get("f_skatt_registered", 0),
            "moms_registered": scb_stats.get("moms_registered", 0),
            "zero_employees": scb_stats.get("zero_employees", 0),
        },
        "scb_patterns": {
            "no_fskatt": len(scb_patterns.get("no_fskatt", [])),
            "zero_employees_many_directors": len(scb_patterns.get("zero_employees_many_directors", [])),
            "shell_sni_codes": len(scb_patterns.get("shell_sni_codes", [])),
        },
        "top_zero_emp_many_dirs": scb_patterns.get("zero_employees_many_directors", [])[:5],
        "top_shell_sni": scb_patterns.get("shell_sni_codes", [])[:5],
    })


@app.route("/api/demo/networks")
def demo_networks():
    """Get all detected shell networks."""
    networks = intelligence_results.get("top_shell_networks", [])
    return jsonify(networks)


@app.route("/api/demo/serial-directors")
def demo_serial_directors():
    """Get all serial directors."""
    directors = intelligence_results.get("top_serial_directors", [])
    return jsonify(directors)


# ========== Auth (mock) ==========

@app.route("/api/v1/auth/login", methods=["POST"])
def login():
    return jsonify({
        "access_token": "demo-token",
        "refresh_token": "demo-refresh",
        "token_type": "bearer",
    })


@app.route("/api/v1/auth/me")
def auth_me():
    return jsonify({
        "id": "user-1",
        "username": "demo",
        "email": "demo@halo.se",
        "role": "analyst",
    })


@app.route("/api/v1/auth/oidc/providers")
def oidc_providers():
    return jsonify({"providers": []})


if __name__ == "__main__":
    load_data()
    print("\n" + "=" * 60)
    print("HALO Demo Server")
    print("=" * 60)
    print(f"Companies: {len(companies)}")
    print(f"Alerts: {len(alerts)}")
    print(f"Graph: {graph.number_of_nodes() if graph else 0} nodes")
    print("=" * 60)
    print("\nStarting server on http://localhost:5001")
    print("UI should be started with: cd halo/ui && npm run dev")
    print("=" * 60 + "\n")
    app.run(port=5001, debug=True)
