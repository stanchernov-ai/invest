# Provision Microsoft Entra External ID tenant
# Based on docs/saas_technical_solution.md

Write-Host "Creating Entra External ID Tenant..."
# Note: Entra External ID tenants usually need to be created via the Azure Portal.
# We document the steps here.

Write-Host "Steps to manually provision Entra External ID:"
Write-Host "1. Go to Azure Portal -> Create a resource -> Microsoft Entra External ID."
Write-Host "2. Create tenant with email/password flow."
Write-Host "3. Register 'boardroom-app' application."
Write-Host "4. Add the MSAL configuration to 'sc-invest-boardroom-app'."
Write-Host "5. Add 'entra_oid' linking logic in Python REST API."
