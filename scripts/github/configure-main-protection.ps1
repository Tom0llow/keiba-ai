[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Branch = "main"
$requiredCheckNames = @("Quality", "Test")
$githubActionsAppSlug = "github-actions"

Remove-Item Env:GH_REPO -ErrorAction SilentlyContinue
Remove-Item Env:GH_HOST -ErrorAction SilentlyContinue

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required."
}

$user = & gh api --hostname github.com user --jq .login 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($user | Out-String).Trim())) {
    $detail = ($user | ForEach-Object { $_.ToString() }) -join "`n"
    throw "GitHub API authentication failed. Run this admin script from an authenticated host terminal.`n$detail"
}

$origin = (& git remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($origin)) {
    throw "Remote 'origin' is not configured."
}

$originText = ($origin | Out-String).Trim()
if ($originText -match '^https://github\.com/(?<path>[^?#]+?)(?:\.git)?/?$') {
    $repo = [string]$Matches.path
}
elseif ($originText -match '^ssh://git@github\.com/(?<path>[^?#]+?)(?:\.git)?/?$') {
    $repo = [string]$Matches.path
}
elseif ($originText -match '^git@github\.com:(?<path>[^?#]+?)(?:\.git)?/?$') {
    $repo = [string]$Matches.path
}
else {
    throw "This admin script requires an origin hosted at github.com; found '$originText'."
}
$repo = $repo.Trim('/').TrimEnd('/')
if ($repo.EndsWith('.git', [System.StringComparison]::OrdinalIgnoreCase)) {
    $repo = $repo.Substring(0, $repo.Length - 4)
}
if ($repo -notmatch '^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+$') {
    throw "Could not derive a safe GitHub owner/repository identity from origin '$originText'."
}

$repoJson = (& gh repo view $repo --json nameWithOwner 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoJson)) {
    throw "GitHub CLI could not resolve the repository from origin '$origin'."
}

$resolvedRepo = [string](($repoJson | ConvertFrom-Json).nameWithOwner)
if (-not [string]::Equals(
    $repo,
    $resolvedRepo,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "GitHub CLI resolved '$resolvedRepo', not origin repository '$repo'."
}

$appJson = & gh api `
    --hostname github.com `
    -H "Accept: application/vnd.github+json" `
    -H "X-GitHub-Api-Version: 2026-03-10" `
    "apps/$githubActionsAppSlug" 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($appJson | Out-String).Trim())) {
    $detail = ($appJson | ForEach-Object { $_.ToString() }) -join "`n"
    throw "Could not resolve the GitHub Actions app from the GitHub API.`n$detail"
}

try {
    $githubActionsApp = $appJson | ConvertFrom-Json
}
catch {
    throw "The GitHub API returned invalid GitHub Actions app metadata: $($_.Exception.Message)"
}

$appSlugProperty = $githubActionsApp.PSObject.Properties["slug"]
$appIdProperty = $githubActionsApp.PSObject.Properties["id"]
if (
    $null -eq $appSlugProperty -or
    -not [string]::Equals(
        [string]$appSlugProperty.Value,
        $githubActionsAppSlug,
        [System.StringComparison]::Ordinal
    ) -or
    $null -eq $appIdProperty
) {
    throw "The GitHub API response did not identify the expected '$githubActionsAppSlug' app."
}

[long]$githubActionsAppId = 0
if (
    -not [long]::TryParse([string]$appIdProperty.Value, [ref]$githubActionsAppId) -or
    $githubActionsAppId -le 0
) {
    throw "The GitHub API returned an invalid GitHub Actions app ID."
}

$requiredChecks = @(
    $requiredCheckNames | ForEach-Object {
        [ordered]@{
            context = $_
            app_id  = $githubActionsAppId
        }
    }
)

# Repository merge policy: autonomous merge is squash-only.
$repoPolicy = @{
    allow_squash_merge = $true
    allow_merge_commit = $false
    allow_rebase_merge = $false
    delete_branch_on_merge = $true
} | ConvertTo-Json -Depth 5

$repoPolicy | gh api `
    --hostname github.com `
    --method PATCH `
    -H "Accept: application/vnd.github+json" `
    -H "X-GitHub-Api-Version: 2026-03-10" `
    "repos/$repo" `
    --input - | Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure repository merge policy."
}

# Require PRs, but require zero human GitHub approvals.
# The human boundary is the exact MERGE_READY HEAD approval in Codex.
$body = @{
    required_status_checks = @{
        strict   = $true
        contexts = @()
        checks   = $requiredChecks
    }
    enforce_admins = $true
    required_pull_request_reviews = @{
        dismiss_stale_reviews = $false
        require_code_owner_reviews = $false
        required_approving_review_count = 0
        require_last_push_approval = $false
    }
    restrictions = $null
    required_linear_history = $true
    allow_force_pushes = $false
    allow_deletions = $false
    block_creations = $false
    required_conversation_resolution = $true
    lock_branch = $false
    allow_fork_syncing = $true
} | ConvertTo-Json -Depth 10

$body | gh api `
    --hostname github.com `
    --method PUT `
    -H "Accept: application/vnd.github+json" `
    -H "X-GitHub-Api-Version: 2026-03-10" `
    "repos/$repo/branches/$Branch/protection" `
    --input - | Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure branch protection. Admin/owner permission may be required."
}

Write-Host "Configured repository/branch policy for ${repo}:$Branch"
Write-Host "Required checks: $($requiredCheckNames -join ', ') (GitHub Actions app_id $githubActionsAppId)"
Write-Host "PR required: yes; GitHub approvals required: 0; merge method: squash only"
