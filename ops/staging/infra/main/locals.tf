locals {
  canvas_hostname = "canvas.${var.domain}"
  files_hostname  = "files.${var.domain}"
  rce_hostname    = "rce.${var.domain}"
  ssh_hostname    = "ssh.${var.domain}"
  database_name   = "canvas_production"
  database_user   = "canvas"
  common_tags     = ["boneslms", "staging", "managed-by-opentofu"]
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "random_password" "canvas_encryption_key" {
  length  = 64
  special = false
}

resource "random_password" "canvas_jwt_encryption_key" {
  length  = 64
  special = false
}

resource "random_password" "canvas_admin_password" {
  length  = 32
  special = false
}

resource "random_password" "rce_ecosystem_key" {
  length  = 32
  special = false
}

resource "random_password" "rce_ecosystem_secret" {
  length  = 32
  special = false
}

resource "tls_private_key" "deploy" {
  algorithm = "ED25519"
}

resource "tls_private_key" "host" {
  algorithm = "ED25519"
}
