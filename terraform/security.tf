# ─── Secret Manager: DB password stored encrypted with KMS ───────────────────
resource "google_secret_manager_secret" "db_pass" {
  secret_id = "alloydb-db-pass"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
        customer_managed_encryption {
          kms_key_name = google_kms_crypto_key.secrets_key.id
        }
      }
    }
  }

  depends_on = [google_kms_crypto_key_iam_member.secretmanager_kms_binding]
}

resource "google_secret_manager_secret_version" "db_pass" {
  secret      = google_secret_manager_secret.db_pass.id
  secret_data = var.db_pass
}

# ─── VPC for internal AlloyDB → Cloud Run traffic ──────────────────────────
resource "google_compute_network" "vpc" {
  name                    = "arch-agent-vpc"
  project                 = var.project_id
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "private" {
  name                     = "arch-agent-subnet"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.1
    metadata             = "EXCLUDE_ALL_METADATA"
  }
}

# ─── Firewall Rules ──────────────────────────────────────────────────────────

# Allow HTTPS from anywhere to Cloud Run (Cloud Run handles TLS, this rule is
# for the underlying network / Load Balancer if added later)
resource "google_compute_firewall" "allow_https_ingress" {
  name    = "allow-https-ingress"
  network = google_compute_network.vpc.name
  project = var.project_id

  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["443", "8000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["arch-agent-run"]
  description   = "Allow HTTPS and port 8000 traffic to Cloud Run service"
}

# Block all non-HTTPS ingress
resource "google_compute_firewall" "deny_other_ingress" {
  name    = "deny-other-ingress"
  network = google_compute_network.vpc.name
  project = var.project_id

  direction = "INGRESS"
  priority  = 2000

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
  description   = "Deny all other inbound traffic (catch-all)"
}

# Allow Cloud Run → AlloyDB on port 5432 (PostgreSQL)
resource "google_compute_firewall" "allow_alloydb_egress" {
  name    = "allow-alloydb-egress"
  network = google_compute_network.vpc.name
  project = var.project_id

  direction = "EGRESS"
  priority  = 900

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }

  destination_ranges = ["10.10.0.0/24"]
  description        = "Allow Cloud Run to reach AlloyDB on internal subnet"
}

# Allow all egress to Google APIs (Vertex AI, Secret Manager, GCS etc.)
resource "google_compute_firewall" "allow_google_apis_egress" {
  name    = "allow-google-apis-egress"
  network = google_compute_network.vpc.name
  project = var.project_id

  direction = "EGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  destination_ranges = ["199.36.153.4/30"] # restricted.googleapis.com
  description        = "Allow Cloud Run to reach Google APIs over Private Google Access"
}
