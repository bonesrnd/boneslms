resource "cloudflare_zero_trust_tunnel_cloudflared" "staging" {
  account_id = var.cloudflare_account_id
  name       = var.project_name
  config_src = "cloudflare"
}

data "cloudflare_zero_trust_tunnel_cloudflared_token" "staging" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.staging.id
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "staging" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.staging.id

  config = {
    ingress = [
      {
        hostname = local.canvas_hostname
        service  = "http://localhost:8080"
      },
      {
        hostname = local.files_hostname
        service  = "http://localhost:8080"
      },
      {
        hostname = local.rce_hostname
        service  = "http://localhost:3000"
      },
      {
        hostname = local.ssh_hostname
        service  = "ssh://localhost:22"
      },
      {
        service = "http_status:404"
      },
    ]
  }
}

resource "cloudflare_dns_record" "canvas" {
  zone_id = var.cloudflare_zone_id
  name    = local.canvas_hostname
  content = "${cloudflare_zero_trust_tunnel_cloudflared.staging.id}.cfargotunnel.com"
  type    = "CNAME"
  ttl     = 1
  proxied = true
  comment = "Managed by OpenTofu for Bones LMS staging"
}

resource "cloudflare_dns_record" "files" {
  zone_id = var.cloudflare_zone_id
  name    = local.files_hostname
  content = "${cloudflare_zero_trust_tunnel_cloudflared.staging.id}.cfargotunnel.com"
  type    = "CNAME"
  ttl     = 1
  proxied = true
  comment = "Managed by OpenTofu for Bones LMS staging"
}

resource "cloudflare_dns_record" "rce" {
  zone_id = var.cloudflare_zone_id
  name    = local.rce_hostname
  content = "${cloudflare_zero_trust_tunnel_cloudflared.staging.id}.cfargotunnel.com"
  type    = "CNAME"
  ttl     = 1
  proxied = true
  comment = "Managed by OpenTofu for Bones LMS staging"
}

resource "cloudflare_dns_record" "ssh" {
  zone_id = var.cloudflare_zone_id
  name    = local.ssh_hostname
  content = "${cloudflare_zero_trust_tunnel_cloudflared.staging.id}.cfargotunnel.com"
  type    = "CNAME"
  ttl     = 1
  proxied = true
  comment = "Managed by OpenTofu for Bones LMS staging"
}

resource "cloudflare_zero_trust_access_identity_provider" "account_login" {
  account_id = var.cloudflare_account_id
  name       = "Cloudflare"
  type       = "cloudflare"

  config = {
    restrict_to_account_members = true
  }
}

resource "cloudflare_zero_trust_access_service_token" "github" {
  account_id = var.cloudflare_account_id
  name       = "Bones LMS staging GitHub Actions"
  duration   = "8760h"
}

resource "cloudflare_zero_trust_access_policy" "admin" {
  account_id = var.cloudflare_account_id
  name       = "Allow Bones LMS staging administrator"
  decision   = "allow"

  include = [
    {
      email = {
        email = var.admin_email
      }
    },
  ]
}

resource "cloudflare_zero_trust_access_policy" "github" {
  account_id = var.cloudflare_account_id
  name       = "Allow Bones LMS staging deployment"
  decision   = "non_identity"

  include = [
    {
      service_token = {
        token_id = cloudflare_zero_trust_access_service_token.github.id
      }
    },
  ]
}

resource "cloudflare_zero_trust_access_policy" "app_origin" {
  account_id = var.cloudflare_account_id
  name       = "Bypass Access for the Bones LMS app host"
  decision   = "bypass"

  include = [
    {
      ip = {
        ip = "${digitalocean_droplet.app.ipv4_address}/32"
      }
    },
    {
      ip = {
        ip = "${digitalocean_droplet.app.ipv6_address}/128"
      }
    },
  ]
}

resource "cloudflare_zero_trust_access_application" "canvas" {
  account_id                = var.cloudflare_account_id
  name                      = "Bones LMS Staging"
  type                      = "self_hosted"
  domain                    = local.canvas_hostname
  session_duration          = "12h"
  allowed_idps              = [cloudflare_zero_trust_access_identity_provider.account_login.id]
  auto_redirect_to_identity = true
  skip_interstitial         = true
  policies = [
    {
      id         = cloudflare_zero_trust_access_policy.app_origin.id
      precedence = 1
    },
    {
      id         = cloudflare_zero_trust_access_policy.admin.id
      precedence = 2
    },
    {
      id         = cloudflare_zero_trust_access_policy.github.id
      precedence = 3
    },
  ]
}

resource "cloudflare_zero_trust_access_application" "ssh" {
  account_id                = var.cloudflare_account_id
  name                      = "Bones LMS Staging SSH"
  type                      = "self_hosted"
  domain                    = local.ssh_hostname
  session_duration          = "1h"
  allowed_idps              = [cloudflare_zero_trust_access_identity_provider.account_login.id]
  auto_redirect_to_identity = true
  service_auth_401_redirect = true
  policies = [
    {
      id         = cloudflare_zero_trust_access_policy.admin.id
      precedence = 1
    },
    {
      id         = cloudflare_zero_trust_access_policy.github.id
      precedence = 2
    },
  ]
}
