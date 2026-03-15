# Enterprise Architecture Review Agent

An AI-powered system that analyzes system design documents (PRD/HLD/LLD) and produces grounded architectural insights using a 6-step agentic workflow — RAG knowledge retrieval, bottleneck detection, improvement proposals, Mermaid diagrams, OpenAPI specs, and verified citations.

## Architecture

This project has been upgraded to a production-ready **Google Cloud Platform (GCP)** architecture:

- **AI Engine**: Google Vertex AI `gemini-3.1-flash-light`
- **Vector Database**: Cloud SQL (AlloyDB) for PostgreSQL with `pgvector`
- **Hosting**: Google Cloud Run (Serverless)
- **Infrastructure as Code**: Terraform (VPC, KMS, Secret Manager, IAM, SQL)
- **CI/CD**: 7-stage Golden Pipeline via GitHub Actions using Workload Identity Federation

## Prerequisites

- **Python 3.10+** (for local development)
- **Google Cloud SDK (`gcloud`)**
- Application Default Credentials (ADC) configured:
  ```bash
  gcloud auth application-default login
  ```

## Local Development Setup

### 1. Enable Auto-Shift Commit Hook
This repository uses a pre-commit hook that **automatically shifts** any commits erroneously made on `master` to a new `feature/auto-shift-<timestamp>` branch.

Run this once after cloning:
```bash
git config core.hooksPath .githooks
```

### 2. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment Variables
You must connect to the AlloyDB instance to run the app locally.
```bash
export GOOGLE_CLOUD_PROJECT="<your project id>"
export GOOGLE_CLOUD_REGION="us-central1"
export ALLOYDB_CLUSTER="arch-agent-cluster"
export ALLOYDB_INSTANCE="arch-agent-instance"
export ALLOYDB_USER="postgres"
export ALLOYDB_PASS="<your-db-password>"
export ALLOYDB_NAME="knowledge_base"
```

### 3. Seed the Knowledge Base (run once)
This populates AlloyDB with `pgvector` embeddings using Vertex AI.
```bash
cd backend
python knowledge_base/seed.py
```

### 4. Start the Server
```bash
cd backend
python main.py
```
Open **http://localhost:8000** in your browser.

## CI/CD Golden Pipeline

This repository enforces a **7-Stage Golden Pipeline** on any pull request or push to `master`:

1. **Code Quality**: Flake8, Pylint, tflint
2. **Security Scan**: pip-audit, Bandit SAST, Trivy image scan (Blocks on CRITICAL CVEs), tfsec
3. **Unit Tests**: pytest + coverage
4. **Build**: Immutable Docker container pushed to Artifact Registry
5. **Infrastructure**: Terraform validate & apply (state held in GCS)
6. **Staging**: Auto-deploys to `architecture-review-agent-staging` + automated smoke test
7. **Production**: Requires manual approval gate in GitHub. Auto-rollbacks on smoke test failure.

**Branch Protection**: Direct pushes to `master` are blocked. All features must be developed on `feature/*` branches and merged via Pull Request.

## Security Controls

- **Keyless Deployment**: GitHub Actions uses Workload Identity Federation (WIF). No Service Account JSON keys exist.
- **Data at Rest**: AlloyDB is encrypted via Customer-Managed Encryption Keys (CMEK) via Cloud KMS.
- **Secret Management**: Database passwords are encrypted at rest in GCP Secret Manager and injected at runtime.
- **Network Isolation**: Cloud Run communicates with AlloyDB exclusively over a private VPC Serverless Connector. Only HTTPS ingress is open.
- **Principle of Least Privilege**: The Cloud Run service account has granular IAM bindings (no broad `owner`/`editor` roles).
