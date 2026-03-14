resource "google_alloydb_cluster" "default" {
  cluster_id = "arch-agent-cluster"
  location   = var.region
  project    = var.project_id

  network_config {
    network = "projects/${var.project_id}/global/networks/default"
  }

  initial_user {
    user     = var.db_user
    password = var.db_pass
  }
}

resource "google_alloydb_instance" "default" {
  cluster       = google_alloydb_cluster.default.name
  instance_id   = "arch-agent-instance"
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = 2
  }

  # Enable public IP so Cloud Run can connect via AlloyDB Auth Proxy
  client_connection_config {
    require_connectors = false
    ssl_config {
      ssl_mode = "ALLOW_UNENCRYPTED_AND_ENCRYPTED"
    }
  }
}

# Give the AlloyDB SA the ability to connect
resource "google_project_iam_member" "alloydb_superuser" {
  project = var.project_id
  role    = "roles/alloydb.superuser"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}
