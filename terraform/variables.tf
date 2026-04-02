variable "project_id" {
  description = "The GCP project ID"
  type        = string
  default     = "project-ef11010f-3538-4e0c-8f1"
}

variable "region" {
  description = "The GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "db_name" {
  description = "The database name"
  type        = string
  default     = "knowledge_base"
}

variable "db_user" {
  description = "The database username"
  type        = string
  default     = "postgres"
}

variable "db_pass" {
  description = "The database password"
  type        = string
  sensitive   = true
}

variable "service_name" {
  description = "The Cloud Run service name"
  type        = string
  default     = "architecture-review-agent"
}
