#!/bin/bash
set -e

PROJECT_ID="project-ef11010f-3538-4e0c-8f1"
REGION="us-central1"
SERVICE_NAME="architecture-review-agent"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/arch-agent"
IMAGE_TAG="${REGISTRY}/${SERVICE_NAME}:latest"
SA_EMAIL="arch-agent-run-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# AlloyDB connection details — override via env vars if needed
ALLOYDB_CLUSTER="${ALLOYDB_CLUSTER:-arch-agent-cluster}"
ALLOYDB_INSTANCE="${ALLOYDB_INSTANCE:-arch-agent-instance}"
ALLOYDB_USER="${ALLOYDB_USER:-postgres}"
ALLOYDB_PASS="${ALLOYDB_PASS:?ALLOYDB_PASS env var must be set}"
ALLOYDB_NAME="${ALLOYDB_NAME:-knowledge_base}"

echo "=================================================="
echo "🚀 Deploying Architecture Review Agent to Cloud Run"
echo "=================================================="

# Configure gcloud project
gcloud config set project "$PROJECT_ID"

# Ensure Artifact Registry repo exists
echo ""
echo "[0/3] Ensuring Artifact Registry repository..."
gcloud artifacts repositories create arch-agent \
  --repository-format=docker \
  --location="$REGION" 2>/dev/null || true

echo ""
echo "[1/3] Building & pushing image via Cloud Build..."
gcloud builds submit --tag "$IMAGE_TAG"

echo ""
echo "[2/3] Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_TAG" \
  --region "$REGION" \
  --allow-unauthenticated \
  --platform managed \
  --memory 1Gi \
  --timeout 300 \
  --service-account "$SA_EMAIL" \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_REGION=${REGION},GOOGLE_CLOUD_LOCATION=global,EMBEDDING_LOCATION=${REGION},ALLOYDB_CLUSTER=${ALLOYDB_CLUSTER},ALLOYDB_INSTANCE=${ALLOYDB_INSTANCE},ALLOYDB_USER=${ALLOYDB_USER},ALLOYDB_PASS=${ALLOYDB_PASS},ALLOYDB_NAME=${ALLOYDB_NAME}"

echo ""
echo "[3/3] Deployment complete! Service URL:"
gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format="value(status.url)"
