[CmdletBinding()]
param()

Write-Error "Source-based LocalSystem installation is disabled. It could run code from a user-writable directory as SYSTEM. Use the packaged BioUnlock installer, which installs its pre-login executable under Program Files."
exit 1
