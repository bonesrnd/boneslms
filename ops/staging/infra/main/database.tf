resource "digitalocean_database_cluster" "postgres" {
  name                 = "${var.project_name}-postgres"
  engine               = "pg"
  version              = var.database_version
  size                 = var.database_size
  region               = var.region
  node_count           = 1
  private_network_uuid = digitalocean_vpc.staging.id
  tags                 = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}

data "digitalocean_database_ca" "postgres" {
  cluster_id = digitalocean_database_cluster.postgres.id
}

resource "digitalocean_database_postgresql_config" "canvas" {
  cluster_id                = digitalocean_database_cluster.postgres.id
  max_locks_per_transaction = 640
  max_stack_depth           = 5242880
  timezone                  = "UTC"
}

resource "digitalocean_database_db" "canvas" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = local.database_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "digitalocean_database_user" "canvas" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = local.database_user

  lifecycle {
    ignore_changes = [settings]
  }
}

resource "digitalocean_database_firewall" "canvas" {
  cluster_id = digitalocean_database_cluster.postgres.id

  rule {
    type  = "droplet"
    value = digitalocean_droplet.app.id
  }
}
