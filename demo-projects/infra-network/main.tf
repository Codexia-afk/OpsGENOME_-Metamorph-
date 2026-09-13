terraform {
  required_version = ">= 1.0.0"
}

variable "environment" {
  type        = string
  description = "Target deployment environment (e.g. staging, prod)"
}

resource "aws_vpc" "primary" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true

  tags = {
    Name        = "primary-vpc"
    Environment = var.environment
  }
}
