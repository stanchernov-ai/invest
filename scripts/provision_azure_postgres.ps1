# Provision Azure Database for PostgreSQL Flexible Server
# Based on docs/saas_postgres_rollout.md

$ResourceGroup = "rg-boardroom-prod"
$ServerName = "psql-boardroom-prod"
$AdminUser = "boardroom_admin"
$AdminPassword = "<GENERATE-STRONG-PASSWORD>"
$AppPassword = "<APP-PASSWORD>"
$Location = "eastus"

Write-Host "Creating Azure Postgres Flexible Server..."
az postgres flexible-server create `
  --resource-group $ResourceGroup `
  --name $ServerName `
  --location $Location `
  --tier Burstable `
  --sku-name Standard_B1ms `
  --storage-size 32 `
  --version 16 `
  --admin-user $AdminUser `
  --admin-password $AdminPassword `
  --public-access 0.0.0.0 `
  --yes

Write-Host "Creating Database 'boardroom'..."
az postgres flexible-server db create `
  --resource-group $ResourceGroup `
  --server-name $ServerName `
  --database-name boardroom

Write-Host "Creating Firewall Rule to Allow Azure Services..."
az postgres flexible-server firewall-rule create `
  --resource-group $ResourceGroup `
  --name $ServerName `
  --rule-name AllowAzureServices `
  --start-ip-address 0.0.0.0 `
  --end-ip-address 0.0.0.0

Write-Host "Provisioning complete. Run migrations manually using psql and connection string."
