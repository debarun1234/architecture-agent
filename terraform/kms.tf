# ─── KMS Keyring & Keys ──────────────────────────────────────────────────────
resource "google_kms_key_ring" "arch_agent" {
  name     = "arch-agent-keyring"
  location = var.region
  project  = var.project_id
}

# Key used to encrypt the database password secret in Secret Manager
resource "google_kms_crypto_key" "secrets_key" {
  name            = "secrets-encryption-key"
  key_ring        = google_kms_key_ring.arch_agent.id
  rotation_period = "7776000s" # 90-day automatic rotation

  lifecycle {
    prevent_destroy = true
  }
}

# Key used for AlloyDB data-at-rest encryption (CMEK)
resource "google_kms_crypto_key" "alloydb_key" {
  name            = "alloydb-cmek-key"
  key_ring        = google_kms_key_ring.arch_agent.id
  rotation_period = "7776000s" # 90-day automatic rotation

  lifecycle {
    prevent_destroy = true
  }
}

# Allow AlloyDB service agent to use the CMEK key
resource "google_project_service_identity" "alloydb_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "alloydb.googleapis.com"
}

resource "google_kms_crypto_key_iam_member" "alloydb_kms_binding" {
  crypto_key_id = google_kms_crypto_key.alloydb_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_project_service_identity.alloydb_sa.email}"
}

# Allow Secret Manager service agent to use the secrets key
resource "google_kms_crypto_key_iam_member" "secretmanager_kms_binding" {
  crypto_key_id = google_kms_crypto_key.secrets_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${var.project_number}@gcp-sa-secretmanager.iam.gserviceaccount.com"
}
