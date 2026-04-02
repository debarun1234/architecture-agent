resource "google_alloydb_cluster" "default" {
  cluster_id = "arch-agent-cluster"
  location   = var.region
  project    = var.project_id

  # Use our private VPC network, not the default network
  network_config {
    network = google_compute_network.vpc.id
  }

  initial_user {
    user     = var.db_user
    password = var.db_pass
  }

  # CMEK encryption for data at rest
  encryption_config {
    kms_key_name = google_kms_crypto_key.alloydb_key.id
  }

  depends_on = [
    google_service_networking_connection.private_vpc_connection,
    google_kms_crypto_key_iam_member.alloydb_kms_binding,
  ]
}

resource "google_alloydb_instance" "default" {
  cluster       = google_alloydb_cluster.default.name
  instance_id   = "arch-agent-instance"
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = 2
  }

  client_connection_config {
    require_connectors = false
    ssl_config {
      ssl_mode = "ALLOW_UNENCRYPTED_AND_ENCRYPTED"
    }
  }
}

# ─── Private Service Access for AlloyDB ──────────────────────────────────────
# AlloyDB requires Service Networking API + a private connection to the VPC
resource "google_compute_global_address" "private_ip_alloydb" {
  name          = "alloydb-private-ip-range"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloydb.name]
  depends_on              = [google_project_service.servicenetworking]
}

# Enable Service Networking API (required for AlloyDB private IP)
resource "google_project_service" "servicenetworking" {
  project            = var.project_id
  service            = "servicenetworking.googleapis.com"
  disable_on_destroy = false
}

# Enable AlloyDB API
resource "google_project_service" "alloydb" {
  project            = var.project_id
  service            = "alloydb.googleapis.com"
  disable_on_destroy = false
}
