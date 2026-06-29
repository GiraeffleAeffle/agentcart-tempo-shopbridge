terraform {
  required_version = ">= 1.6.0"

  backend "local" {
    path = "../../../.secrets/terraform/hetzner-staging.tfstate"
  }

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.50"
    }
  }
}

provider "hcloud" {}

resource "hcloud_ssh_key" "admin" {
  name       = var.ssh_key_name
  public_key = file(var.ssh_public_key_path)
}

resource "hcloud_firewall" "web" {
  name = "${var.server_name}-firewall"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.ssh_source_ips
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_server" "staging" {
  name        = var.server_name
  image       = var.image
  server_type = var.server_type
  location    = var.location
  ssh_keys    = [hcloud_ssh_key.admin.id]
  firewall_ids = [
    hcloud_firewall.web.id,
  ]

  labels = {
    app         = "agentcart"
    environment = "staging"
    role        = "woocommerce"
  }
}
