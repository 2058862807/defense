variable "aws_region" {
  description = "AWS region for the Protean Defense production deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "protean-prod"
}

variable "cluster_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.30"
}

variable "vpc_cidr" {
  description = "VPC CIDR"
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Availability zones (3 for HA across AZs)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "node_instance_type" {
  description = "Managed node group instance type"
  type        = string
  default     = "t3.medium"
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 5
}

variable "node_desired_size" {
  type    = number
  default = 3
}

variable "eks_oidc_client_id" {
  description = "OIDC client ID used by Kubernetes (aws-iam-authenticator etc.)"
  type        = string
  default     = "sts.amazonaws.com"
}

variable "rds_allocated_storage_gb" {
  type    = number
  default = 100
}

variable "rds_instance_class" {
  type    = string
  default = "db.t3.medium"
}

variable "rds_master_username" {
  type        = string
  default     = "protean"
  sensitive   = false
}

variable "rds_master_password" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Postgres master password. If empty, a random one is generated."
}

variable "redis_node_type" {
  type    = string
  default = "cache.t3.micro"
}

variable "redis_replicas_per_group" {
  type    = number
  default = 2
}

variable "s3_artifact_prefix" {
  type    = string
  default = "protean-artifacts"
}

variable "secretsmanager_prefix" {
  type        = string
  default     = "protean"
  description = "Prefix for AWS Secrets Manager secret names"
}

variable "app_namespace" {
  type    = string
  default = "protean-prod"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Extra tags applied to all resources"
}
