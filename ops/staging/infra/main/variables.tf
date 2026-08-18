variable "project_name" {
  description = "Name used for DigitalOcean and Cloudflare resources."
  type        = string
  default     = "boneslms-staging"
}

variable "region" {
  description = "DigitalOcean region."
  type        = string
  default     = "nyc3"
}

variable "domain" {
  description = "Cloudflare-managed base domain."
  type        = string
  default     = "bonesrnd.com"
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID that owns the Zero Trust organization."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for the base domain."
  type        = string
}

variable "cloudflare_otp_identity_provider_id" {
  description = "Existing Cloudflare One-Time PIN identity provider ID."
  type        = string
}

variable "admin_email" {
  description = "Email allowed through Cloudflare Access and used for Canvas bootstrap."
  type        = string
  default     = "bones@bonesrnd.com"

  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+$", var.admin_email))
    error_message = "admin_email must be a valid email address."
  }
}

variable "canvas_account_name" {
  description = "Initial root-account name shown in Canvas."
  type        = string
  default     = "Bones LMS"
}

variable "droplet_size" {
  description = "DigitalOcean Droplet size slug."
  type        = string
  default     = "s-4vcpu-8gb"
}

variable "database_size" {
  description = "DigitalOcean Managed PostgreSQL size slug."
  type        = string
  default     = "db-s-2vcpu-4gb"
}

variable "database_version" {
  description = "Managed PostgreSQL major version."
  type        = string
  default     = "16"
}

variable "spaces_bucket_prefix" {
  description = "Prefix for the globally unique Canvas attachment bucket."
  type        = string
  default     = "boneslms-staging-files"
}

variable "enable_droplet_backups" {
  description = "Enable DigitalOcean Droplet backups."
  type        = bool
  default     = true
}

variable "bootstrap_ssh_cidr" {
  description = "Single administrator host CIDR admitted by UFW for bootstrap recovery."
  type        = string

  validation {
    condition = (
      can(cidrhost(var.bootstrap_ssh_cidr, 0)) &&
      can(regex("/(32|128)$", var.bootstrap_ssh_cidr))
    )
    error_message = "bootstrap_ssh_cidr must be a single IPv4 /32 or IPv6 /128 host."
  }
}

variable "enable_bootstrap_ssh_ingress" {
  description = "Temporarily admit bootstrap_ssh_cidr through the DigitalOcean firewall."
  type        = bool
  default     = false
}
