terraform {
  required_version = ">= 1.11.0"

  backend "s3" {}

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "5.23.0"
    }
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "2.99.1"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.7.2"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "4.1.0"
    }
  }
}

provider "cloudflare" {}
provider "digitalocean" {}
