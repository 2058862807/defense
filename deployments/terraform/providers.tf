terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.14"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "s3" {
    # Bucket + DynamoDB lock created by scripts/aws_bootstrap.sh before apply.
    # Override via -backend-config if using a different account/region.
    bucket         = "protean-terraform-state"
    key            = "protean-prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "protean-terraform-lock"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Application = "protean-defense"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

provider "kubernetes" {
  host                   = aws_eks_cluster.protean.endpoint
  cluster_ca_certificate = base64decode(aws_eks_cluster.protean.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.protean.token
}

provider "helm" {
  kubernetes {
    host                   = aws_eks_cluster.protean.endpoint
    cluster_ca_certificate = base64decode(aws_eks_cluster.protean.certificate_authority[0].data)
    token                  = data.aws_eks_cluster_auth.protean.token
  }
}

data "aws_eks_cluster_auth" "protean" {
  name = aws_eks_cluster.protean.name
}

data "aws_eks_cluster" "protean" {
  name = aws_eks_cluster.protean.name
}
