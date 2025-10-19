terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      version = "6.17.0"
    }
  }
  
  backend "s3" {
    bucket = "suren-terraform"
    key    = "pmu-events-info/terraform.tfstate"
    region = "us-east-2"
  }
}

provider "aws" {
  region = "us-east-1"
}


