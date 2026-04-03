"""
Knowledge Base Seeder
Loads all JSON knowledge files into AlloyDB (pgvector) for RAG retrieval.
Run: python -m knowledge_base.seed
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
from google.cloud.alloydb.connector import AsyncConnector
from vertexai.language_models import TextEmbeddingModel

DATA_DIR = Path(__file__).parent / "data"

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT",
                       "project-ef11010f-3538-4e0c-8f1")
REGION = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
CLUSTER = os.getenv("ALLOYDB_CLUSTER", "arch-agent-cluster")
INSTANCE = os.getenv("ALLOYDB_INSTANCE", "arch-agent-instance")
DB_USER = os.getenv("ALLOYDB_USER", "postgres")
DB_PASS = os.getenv("ALLOYDB_PASS", "postgres")
DB_NAME = os.getenv("ALLOYDB_NAME", "knowledge_base")

FILES_TO_COLLECTIONS = {
    "architecture_principles.json": "architecture_principles",
    "design_patterns.json": "design_patterns",
    "anti_patterns.json": "anti_patterns",
    "security_guidelines.json": "security_guidelines",
    "cloud_reference.json": "cloud_reference",
}


async def seed():
    print(f"\n🚀 Seeding knowledge base to AlloyDB: {INSTANCE} ({DB_NAME})\n")

    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    connector = AsyncConnector()

    try:
        instance_uri = f"projects/{PROJECT_ID}/locations/{REGION}/clusters/{CLUSTER}/instances/{INSTANCE}"
        conn: asyncpg.Connection = await connector.connect(
            instance_uri,
            "asyncpg",
            user=DB_USER,
            password=DB_PASS,
            db=DB_NAME,
        )

        # Setup schema
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id VARCHAR(255) PRIMARY KEY,
                collection_name VARCHAR(255) NOT NULL,
                source_id VARCHAR(255),
                section_reference VARCHAR(255),
                guideline_summary TEXT,
                text_content TEXT,
                tags TEXT,
                embedding vector(768)
            )
        """)
        # Clear existing entries
        await conn.execute("TRUNCATE TABLE knowledge_entries")

        total = 0
        for filename, collection_name in FILES_TO_COLLECTIONS.items():
            filepath = DATA_DIR / filename
            if not filepath.exists():
                print(f"  ⚠️  Skipping {filename} — file not found")
                continue

            with open(filepath, "r", encoding="utf-8") as f:
                entries = json.load(f)

            documents = [e.get("text", e.get("guideline_summary", ""))
                         for e in entries]

            # Generate embeddings
            embeddings = embedding_model.get_embeddings(documents)

            # Prepare rows
            rows_to_insert = []
            for i, entry in enumerate(entries):
                emb_vector = embeddings[i].values
                # We format the vector as a string representation of array for asyncpg
                vector_str = "[" + ",".join(str(v) for v in emb_vector) + "]"

                rows_to_insert.append((
                    f"{collection_name}::{entry['id']}",
                    collection_name,
                    entry.get("source_id", ""),
                    entry.get("section_reference", ""),
                    entry.get("guideline_summary", ""),
                    documents[i],
                    ",".join(entry.get("tags", [])),
                    vector_str
                ))

            # Insert batch
            await conn.executemany("""
                INSERT INTO knowledge_entries (
                    id, collection_name, source_id, section_reference,
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector)
                ON CONFLICT (id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    guideline_summary = EXCLUDED.guideline_summary,
                    text_content = EXCLUDED.text_content
            """, rows_to_insert)

            # Create an HNSW index per collection to speed up search
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS knowledge_embedding_idx
                ON knowledge_entries USING hnsw (embedding vector_cosine_ops)
            """)

            total += len(entries)
            print(f"  ✅ {collection_name}: {len(entries)} entries")

        print(
            f"\n🎉 Seeded {total} documents across {len(FILES_TO_COLLECTIONS)} collections\n")

    except Exception as e:
        print(f"❌ Error seeding database: {e}")
    finally:
        if 'conn' in locals() and not conn.is_closed():
            await conn.close()
        await connector.close()


if __name__ == "__main__":
    # Allow running from project root
    sys.path.insert(0, str(Path(__file__).parent.parent))
    asyncio.run(seed())
