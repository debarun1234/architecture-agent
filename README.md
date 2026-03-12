# Enterprise Architecture Review Agent

An AI-powered system that analyzes system design documents (PRD/HLD/LLD) and produces grounded architectural insights using a 6-step agentic workflow — RAG knowledge retrieval, bottleneck detection, improvement proposals, Mermaid diagrams, OpenAPI specs, and verified citations.

## Prerequisites

- **Python 3.10+**
- **Gemini API Key** — [Get one free at aistudio.google.com](https://aistudio.google.com)

## Quick Start (Windows)

```bat
cd backend
pip install -r requirements.txt
python knowledge_base\seed.py
python main.py
```

Then open **http://localhost:8000** in your browser.

## Manual Start

### 1. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Seed the knowledge base (run once)
```bash
cd backend
python knowledge_base/seed.py
```
Expected output: `🎉 Seeded 46 documents across 5 collections`

### 3. Start the server
```bash
cd backend
python main.py
```

### 4. Open the app
Navigate to **http://localhost:8000**

## Usage

1. Enter your **Gemini API key** in the inline field or via **Settings**
2. Drag & drop a design document (`.txt`, `.md`, `.pdf`, `.docx`)
3. Click **Run Architecture Review**
4. Watch the 6-step agent progress tracker
5. Explore results across 6 tabs: **Context → Guidelines → Bottlenecks → Proposals → Artifacts → Citations**
6. Click **Export JSON** to download the full structured review

## Project Structure

```
architecture-agent/
├── backend/
│   ├── main.py                     # FastAPI server
│   ├── requirements.txt
│   ├── agent/
│   │   ├── orchestrator.py         # 6-step workflow engine
│   │   └── steps/
│   │       ├── step1_extract.py    # Context extraction
│   │       ├── step2_retrieve.py   # RAG retrieval (ChromaDB)
│   │       ├── step3_detect.py     # Bottleneck detection
│   │       ├── step4_propose.py    # Improvement proposals
│   │       ├── step5_artifacts.py  # Mermaid + OpenAPI + Summary
│   │       └── step6_verify.py     # Citation & verification
│   ├── knowledge_base/
│   │   ├── seed.py                 # ChromaDB seeder
│   │   └── data/
│   │       ├── architecture_principles.json
│   │       ├── design_patterns.json
│   │       ├── anti_patterns.json
│   │       ├── security_guidelines.json
│   │       └── cloud_reference.json
│   └── tests/
│       └── sample_prd.txt          # Sample document for testing
└── frontend/
    ├── index.html
    ├── style.css
    └── app.js
```

## Output Format

The agent returns a structured JSON object:

```json
{
  "context": { ... },
  "retrieved_guidelines": [ { "source_id", "section_reference", "guideline_summary" } ],
  "bottlenecks": { "bottlenecks": [ { "id", "area", "severity", "title", "description" } ] },
  "proposed_changes": { "proposals": [ { "id", "rationale", "impact_analysis" } ] },
  "artifacts": { "mermaid_diagram", "openapi_spec", "review_summary" },
  "citations": [ { "finding_id", "verification_status", "source_id" } ]
}
```

## Knowledge Base

| Collection | Entries | Coverage |
|---|---|---|
| `architecture_principles` | 12 | Scalability, reliability, observability, data, API design |
| `design_patterns` | 12 | API Gateway, Saga, CQRS, Event Sourcing, Outbox, Sharding |
| `anti_patterns` | 10 | Distributed Monolith, God Service, SPOF, Chatty I/O, N+1 |
| `security_guidelines` | 10 | Zero Trust, OAuth2, RBAC, encryption, OWASP |
| `cloud_reference` | 12 | AWS, GCP, Azure, Multi-Cloud, Kafka, Observability, DR |
