"""
Step 2 — Retrieve Knowledge (RAG)
Queries Cloud SQL / AlloyDB (pgvector) to retrieve relevant architecture guidelines
using Vertex AI TextEmbeddingModel.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import asyncpg
from google.cloud.alloydb.connector import AsyncConnector
from vertexai.language_models import TextEmbeddingModel

# Use environment variables for GCP connections
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT",
                       "project-ef11010f-3538-4e0c-8f1")
REGION = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
CLUSTER = os.getenv("ALLOYDB_CLUSTER", "arch-agent-cluster")
INSTANCE = os.getenv("ALLOYDB_INSTANCE", "arch-agent-instance")
DB_USER = os.getenv("ALLOYDB_USER", "postgres")
DB_PASS = os.getenv("ALLOYDB_PASS", "postgres")
DB_NAME = os.getenv("ALLOYDB_NAME", "knowledge_base")

N_RESULTS = 4  # results per query per collection (implicitly handled in SQL)

# Path to bundled JSON knowledge files — used as fallback when AlloyDB is unavailable
_DATA_DIR = Path(__file__).parent.parent.parent / "knowledge_base" / "data"
_COLLECTION_MAP = {
    "architecture_principles.json": "architecture_principles",
    "design_patterns.json": "design_patterns",
    "anti_patterns.json": "anti_patterns",
    "security_guidelines.json": "security_guidelines",
    "cloud_reference.json": "cloud_reference",
}


def _load_local_knowledge_base(db_error: Exception) -> list[dict]:
    """Load knowledge entries from local JSON files when AlloyDB is unavailable."""
    results = []
    for filename, collection in _COLLECTION_MAP.items():
        path = _DATA_DIR / filename
        if not path.exists():
            continue
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
            for entry in entries:
                results.append({
                    "source_id": entry.get("source_id", entry.get("id", "UNKNOWN")),
                    "section_reference": entry.get("section_reference", "N/A"),
                    "guideline_summary": entry.get("guideline_summary",
                                                    entry.get("text", "")),
                    "collection": collection,
                    "score": 0.5,
                    "full_text": entry.get("text",
                                           entry.get("guideline_summary", "")),
                })
        except Exception:
            continue
    if not results:
        return [{"source_id": "DB_CONNECTION_ERROR", "section_reference": "N/A",
                 "guideline_summary": f"Database error: {db_error}",
                 "collection": "system", "score": 0.0}]
    return results


def _build_queries(context: dict) -> list[str]:
    """Build targeted search queries from the extracted context."""
    queries = []

    # System components
    components = context.get("components", [])
    for c in components[:3]:
        queries.append(
            f"{c.get('type', '')} {c.get('technology', '')} architecture pattern")

    # Patterns used
    for p in context.get("architectural_patterns", [])[:3]:
        queries.append(f"{p} pattern best practice")

    # Reliability
    rel = context.get("reliability_requirements", {})
    if rel.get("availability_target") not in (None, "Not specified", ""):
        queries.append(
            f"high availability {rel['availability_target']} SLA reliability pattern")

    # Data stores
    for ds in context.get("data_stores", [])[:2]:
        queries.append(
            f"{ds.get('type', '')} {ds.get('technology', '')} data consistency scalability")

    # Deployment
    cloud = context.get("cloud_provider", "")
    if cloud and cloud != "Not specified":
        queries.append(f"{cloud} cloud reference architecture")

    # Security
    for sm in context.get("security_mechanisms", [])[:2]:
        queries.append(f"{sm.get('mechanism', '')} security best practice")

    # Traffic
    traffic = context.get("traffic_expectations", {})
    if traffic.get("peak_qps") not in (None, "Not specified", ""):
        queries.append("high QPS scalability load balancing caching")

    # Fallback generic queries
    queries += [
        "microservices architecture best practices",
        "API gateway design patterns",
        "distributed system reliability",
        "data partitioning sharding strategy",
        "zero trust security architecture",
    ]

    return list(dict.fromkeys(queries))


async def retrieve_knowledge(context: dict) -> list[dict[str, Any]]:
    """Query the AlloyDB pgvector store and return deduplicated results."""
    queries = _build_queries(context)

    # Generate embeddings for all queries at once
    try:
        embedding_model = TextEmbeddingModel.from_pretrained(
            "text-embedding-004")
        embeddings = embedding_model.get_embeddings(queries[:8])
        query_vectors = [emb.values for emb in embeddings]
    except Exception as e:
        return [{"source_id": "KB_UNAVAILABLE", "section_reference": "N/A",
                 "guideline_summary": f"Vertex AI Embedding unavailable: {e}",
                 "collection": "system", "score": 0.0}]

    all_results: list[dict] = []
    seen_ids: set[str] = set()

    connector = AsyncConnector()
    try:
        # Construct the AlloyDB Instance URI
        instance_uri = f"projects/{PROJECT_ID}/locations/{REGION}/clusters/{CLUSTER}/instances/{INSTANCE}"

        conn: asyncpg.Connection = await connector.connect(
            instance_uri,
            "asyncpg",
            user=DB_USER,
            password=DB_PASS,
            db=DB_NAME,
        )
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # Force index usage if available
        await conn.execute("SET enable_seqscan = off;")

        for q_vec in query_vectors:
            # We use pgvector's <=> operator for cosine distance
            query_sql = """
                SELECT id, collection_name, source_id, section_reference,
                       guideline_summary, text_content,
                       1 - (embedding <=> $1::vector) AS similarity_score
                FROM knowledge_entries
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """

            # Note: passing lists to asyncpg for vector types requires formatting
            # or casting. We format it manually as a string representation of array.
            vector_str = "[" + ",".join(str(v) for v in q_vec) + "]"

            rows = await conn.fetch(query_sql, vector_str, N_RESULTS)

            for row in rows:
                uid = f"{row['collection_name']}::{row['source_id']}"
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)

                all_results.append({
                    "source_id": row["source_id"] or "UNKNOWN",
                    "section_reference": row["section_reference"] or "N/A",
                    "guideline_summary": row["guideline_summary"] or row["text_content"],
                    "collection": row["collection_name"],
                    "score": round(row["similarity_score"], 4),
                    "full_text": row["text_content"],
                })

    except Exception as e:
        return _load_local_knowledge_base(e)
    finally:
        if 'conn' in locals() and not conn.is_closed():
            await conn.close()
        await connector.close()

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:40]
