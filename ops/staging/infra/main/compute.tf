resource "digitalocean_vpc" "staging" {
  name   = "${var.project_name}-vpc"
  region = var.region
}

resource "digitalocean_tag" "app_firewall" {
  name = "${var.project_name}-firewall"
}

resource "digitalocean_droplet" "app" {
  name       = "${var.project_name}-app"
  region     = var.region
  size       = var.droplet_size
  image      = "ubuntu-24-04-x64"
  vpc_uuid   = digitalocean_vpc.staging.id
  monitoring = true
  backups    = var.enable_droplet_backups
  ipv6       = true
  tags       = concat(local.common_tags, [digitalocean_tag.app_firewall.id])

  depends_on = [digitalocean_firewall.app]

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    bootstrap_ssh_cidr    = var.bootstrap_ssh_cidr
    deploy_public_key     = trimspace(tls_private_key.deploy.public_key_openssh)
    host_private_key      = indent(4, trimspace(tls_private_key.host.private_key_openssh))
    host_public_key       = trimspace(tls_private_key.host.public_key_openssh)
    tunnel_token          = data.cloudflare_zero_trust_tunnel_cloudflared_token.staging.token
    cloudflared_image     = "cloudflare/cloudflared@sha256:a5b5e6fd9a372f054b9a843c219bfbcdceb54691605312a8b1ee72978bdf1aa1"
    cloudflared_tokenfile = "/etc/boneslms-tunnel-token"
  })

  lifecycle {
    ignore_changes = [
      backups,
      user_data,
    ]
  }
}

resource "digitalocean_firewall" "app" {
  name = "${var.project_name}-app"
  tags = [digitalocean_tag.app_firewall.id]

  dynamic "inbound_rule" {
    for_each = var.enable_bootstrap_ssh_ingress ? [1] : []

    content {
      protocol         = "tcp"
      port_range       = "22"
      source_addresses = [var.bootstrap_ssh_cidr]
    }
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

resource "digitalocean_project" "staging" {
  name        = "Bones LMS Staging"
  description = "Production-like staging infrastructure for Bones LMS."
  purpose     = "Web Application"
  environment = "Staging"

  resources = [
    digitalocean_droplet.app.urn,
    digitalocean_database_cluster.postgres.urn,
    digitalocean_spaces_bucket.files.urn,
  ]
}
