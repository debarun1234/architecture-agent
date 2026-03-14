$ErrorActionPreference = "Stop"

$PROJECT_ID    = "project-ef11010f-3538-4e0c-8f1"
$REGION        = "us-central1"
$SERVICE_NAME  = "architecture-review-agent"
$REGISTRY      = "$REGION-docker.pkg.dev/$PROJECT_ID/arch-agent"
$IMAGE_TAG     = "$REGISTRY/${SERVICE_NAME}:latest"
$SA_EMAIL      = "arch-agent-run-sa@$PROJECT_ID.iam.gserviceaccount.com"

# AlloyDB connection details — set these or export them as env vars before running
$ALLOYDB_CLUSTER  = if ($env:ALLOYDB_CLUSTER) { $env:ALLOYDB_CLUSTER } else { "arch-agent-cluster" }
$ALLOYDB_INSTANCE = if ($env:ALLOYDB_INSTANCE) { $env:ALLOYDB_INSTANCE } else { "arch-agent-instance" }
$ALLOYDB_USER     = if ($env:ALLOYDB_USER) { $env:ALLOYDB_USER } else { "postgres" }
$ALLOYDB_PASS     = if ($env:ALLOYDB_PASS) { $env:ALLOYDB_PASS } else { Read-Host "Enter AlloyDB password" -AsSecureString | ConvertFrom-SecureString -AsPlainText }
$ALLOYDB_NAME     = if ($env:ALLOYDB_NAME) { $env:ALLOYDB_NAME } else { "knowledge_base" }

Write-Host "=================================================="
Write-Host "🚀 Deploying Architecture Review Agent to Cloud Run"
Write-Host "=================================================="

# Configure gcloud project
gcloud config set project $PROJECT_ID

# Ensure Artifact Registry repo exists
Write-Host "`n[0/3] Ensuring Artifact Registry repository..."
gcloud artifacts repositories create arch-agent --repository-format=docker --location=$REGION 2>$null || true

Write-Host "`n[1/3] Building & pushing image via Cloud Build..."
gcloud builds submit --tag $IMAGE_TAG

Write-Host "`n[2/3] Deploying to Cloud Run..."
$ENV_VARS = "GOOGLE_CLOUD_PROJECT=$PROJECT_ID," +
            "GOOGLE_CLOUD_REGION=$REGION," +
            "ALLOYDB_CLUSTER=$ALLOYDB_CLUSTER," +
            "ALLOYDB_INSTANCE=$ALLOYDB_INSTANCE," +
            "ALLOYDB_USER=$ALLOYDB_USER," +
            "ALLOYDB_PASS=$ALLOYDB_PASS," +
            "ALLOYDB_NAME=$ALLOYDB_NAME"

gcloud run deploy $SERVICE_NAME `
  --image $IMAGE_TAG `
  --region $REGION `
  --allow-unauthenticated `
  --platform managed `
  --memory 1Gi `
  --timeout 300 `
  --service-account $SA_EMAIL `
  --set-env-vars $ENV_VARS

Write-Host "`n[3/3] Deployment complete! Service URL:"
gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)"
