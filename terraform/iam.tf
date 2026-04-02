resource "google_service_account" "cloud_run_sa" {
  account_id   = "arch-agent-run-sa"
  display_name = "Service Account for Architecture Agent Cloud Run"
  project      = var.project_id
}

# ─── Vertex AI ───────────────────────────────────────────────────────────────
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# ─── AlloyDB ─────────────────────────────────────────────────────────────────
resource "google_project_iam_member" "alloydb_client" {
  project = var.project_id
  role    = "roles/alloydb.client"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_project_iam_member" "cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# ─── Secret Manager ──────────────────────────────────────────────────────────
resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# ─── KMS ─────────────────────────────────────────────────────────────────────
resource "google_kms_crypto_key_iam_member" "cloud_run_kms_decrypt" {
  crypto_key_id = google_kms_crypto_key.secrets_key.id
  role          = "roles/cloudkms.cryptoKeyDecrypter"
  member        = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# ─── Cloud Trace (Observability) ─────────────────────────────────────────────
resource "google_project_iam_member" "trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# ─── Cloud Logging ───────────────────────────────────────────────────────────
resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# ─── Cloud Storage (document uploads & artifacts) ────────────────────────────
resource "google_project_iam_member" "storage_object_creator" {
  project = var.project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_project_iam_member" "storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# Reduced from roles/run.admin to roles/run.developer (deploy only, no admin)
resource "google_project_iam_member" "ci_run_admin" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:github-actions-deployer@${var.project_id}.iam.gserviceaccount.com"
}

# Reduced from roles/storage.admin to roles/storage.objectAdmin (object-level only)
resource "google_project_iam_member" "ci_storage_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:github-actions-deployer@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "ci_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:github-actions-deployer@${var.project_id}.iam.gserviceaccount.com"
}

# Scoped serviceAccountUser to only the Cloud Run SA (not project-wide)
resource "google_service_account_iam_member" "ci_sa_user" {
  service_account_id = google_service_account.cloud_run_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:github-actions-deployer@${var.project_id}.iam.gserviceaccount.com"
}
