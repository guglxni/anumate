# Terraform Infrastructure

Infrastructure as Code for provisioning cloud resources for the Anumate platform.

## Structure

- `modules/` - Reusable Terraform modules
- `environments/` - Environment-specific configurations
- `providers.tf` - Provider configurations
- `variables.tf` - Input variables
- `outputs.tf` - Output values
- `main.tf` - Main infrastructure definition

## Environments

- `environments/dev/` - Development environment
- `environments/staging/` - Staging environment  
- `environments/prod/` - Production environment

## Usage

```bash
# Initialize
terraform init

# Plan changes
terraform plan -var-file="environments/dev/terraform.tfvars"

# Apply changes
terraform apply -var-file="environments/dev/terraform.tfvars"
```