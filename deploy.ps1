<#
.SYNOPSIS
    One-click deployment script for Octopus Agile Companion HACS integration.

.DESCRIPTION
    This script handles versioning, git commits, tagging, and pushing to GitHub.
    It reads the current version from manifest.json, optionally bumps it,
    commits all changes, creates a git tag, and pushes everything.

.PARAMETER BumpType
    Type of version bump: 'major', 'minor', 'patch', or 'none' (default: 'patch')

.PARAMETER Message
    Commit message (default: "Release vX.X.X")

.PARAMETER NoPush
    If specified, only commits locally without pushing to remote

.EXAMPLE
    .\deploy.ps1
    # Bumps patch version (e.g., 1.0.0 -> 1.0.1), commits, tags, and pushes

.EXAMPLE
    .\deploy.ps1 -BumpType minor -Message "Add new calendar feature"
    # Bumps minor version (e.g., 1.0.1 -> 1.1.0) with custom message

.EXAMPLE
    .\deploy.ps1 -BumpType none
    # Commits and pushes without changing version
#>

param(
    [ValidateSet('major', 'minor', 'patch', 'none')]
    [string]$BumpType = 'patch',
    
    [string]$Message = '',
    
    [switch]$NoPush
)

$ErrorActionPreference = 'Stop'

# Paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManifestPath = Join-Path $ScriptDir "custom_components\octopus_agile_companion\manifest.json"

# Output helpers
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Info { param($msg) Write-Host "[..] $msg" -ForegroundColor Cyan }
function Write-Warn { param($msg) Write-Host "[!!] $msg" -ForegroundColor Yellow }
function Write-Err { param($msg) Write-Host "[XX] $msg" -ForegroundColor Red }

# Banner
Write-Host ""
Write-Host "=========================================================" -ForegroundColor Magenta
Write-Host "     Octopus Agile Companion - Deployment Script         " -ForegroundColor Magenta
Write-Host "=========================================================" -ForegroundColor Magenta
Write-Host ""

# Check we're in a git repo
if (-not (Test-Path (Join-Path $ScriptDir ".git"))) {
    Write-Err "Not a git repository! Run 'git init' first."
    exit 1
}

# Check manifest exists
if (-not (Test-Path $ManifestPath)) {
    Write-Err "manifest.json not found at: $ManifestPath"
    exit 1
}

# Read current version
$Manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$CurrentVersion = $Manifest.version
Write-Info "Current version: $CurrentVersion"

# Parse version
$VersionParts = $CurrentVersion -split '\.'
$Major = [int]$VersionParts[0]
$Minor = [int]$VersionParts[1]
$Patch = [int]$VersionParts[2]

# Bump version
$NewVersion = $CurrentVersion
switch ($BumpType) {
    'major' {
        $Major++
        $Minor = 0
        $Patch = 0
        $NewVersion = "$Major.$Minor.$Patch"
    }
    'minor' {
        $Minor++
        $Patch = 0
        $NewVersion = "$Major.$Minor.$Patch"
    }
    'patch' {
        $Patch++
        $NewVersion = "$Major.$Minor.$Patch"
    }
    'none' {
        Write-Info "Keeping version at $CurrentVersion"
    }
}

if ($BumpType -ne 'none') {
    Write-Info "New version: $NewVersion"
    
    # Update manifest.json
    $Manifest.version = $NewVersion
    $Manifest | ConvertTo-Json -Depth 10 | Set-Content $ManifestPath -Encoding UTF8
    Write-Success "Updated manifest.json"
}

# Set commit message
if ([string]::IsNullOrEmpty($Message)) {
    $Message = "Release v$NewVersion"
}

# Show git status
Write-Host ""
Write-Info "Git status:"
git status --short
Write-Host ""

# Confirm with user
$TagName = "v$NewVersion"
Write-Host "Actions to perform:" -ForegroundColor Yellow
Write-Host "  1. Stage all changes" -ForegroundColor White
Write-Host "  2. Commit with message: '$Message'" -ForegroundColor White
Write-Host "  3. Create tag: $TagName" -ForegroundColor White
if (-not $NoPush) {
    Write-Host "  4. Push to remote with tags" -ForegroundColor White
}
Write-Host ""

$Confirm = Read-Host "Proceed? (y/N)"
if ($Confirm -ne 'y' -and $Confirm -ne 'Y') {
    Write-Warn "Aborted by user"
    exit 0
}

Write-Host ""

# Stage all changes
Write-Info "Staging changes..."
git add -A
Write-Success "Changes staged"

# Commit
Write-Info "Committing..."
git commit -m $Message
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Nothing to commit or commit failed"
}
else {
    Write-Success "Committed: $Message"
}

# Create tag (delete if exists)
Write-Info "Creating tag $TagName..."
$ExistingTag = git tag -l $TagName
if ($ExistingTag) {
    Write-Warn "Tag $TagName already exists, deleting..."
    git tag -d $TagName
}
git tag -a $TagName -m "Release $NewVersion"
Write-Success "Tag created: $TagName"

# Push
if (-not $NoPush) {
    Write-Info "Pushing to remote..."
    git push origin main --follow-tags
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Push failed, trying with 'master' branch..."
        git push origin master --follow-tags
    }
    Write-Success "Pushed to remote with tags"
    
    # Create GitHub Release using gh CLI
    Write-Host ""
    Write-Info "Creating GitHub Release..."
    
    # Check if gh CLI is available
    $ghPath = Get-Command gh -ErrorAction SilentlyContinue
    if ($ghPath) {
        # Build release notes
        $ReleaseTitle = "v$NewVersion"
        $ReleaseNotes = @"
## What's New in v$NewVersion

$Message

### Installation
1. Add this repository to HACS as a custom repository
2. Search for "Octopus Agile Companion" in HACS
3. Install and restart Home Assistant
4. Add the integration via Settings > Devices & Services

### Full Changelog
https://github.com/wyvernp/octopus_agile_companion/compare/v$CurrentVersion...v$NewVersion
"@
        
        # Create the release
        $ReleaseNotes | gh release create $TagName --title $ReleaseTitle --notes-file -
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "GitHub Release created: $TagName"
        }
        else {
            Write-Warn "Failed to create GitHub release. Create manually at:"
            Write-Host "  https://github.com/wyvernp/octopus_agile_companion/releases/new?tag=$TagName" -ForegroundColor Blue
        }
    }
    else {
        Write-Warn "GitHub CLI (gh) not found. Install it for automatic releases:"
        Write-Host "  winget install GitHub.cli" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Create release manually at:" -ForegroundColor Yellow
        Write-Host "  https://github.com/wyvernp/octopus_agile_companion/releases/new?tag=$TagName" -ForegroundColor Blue
    }
}

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "              Deployment Complete!                       " -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Version $NewVersion has been deployed." -ForegroundColor White
Write-Host ""
