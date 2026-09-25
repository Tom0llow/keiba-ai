[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Branch = "main"
$requiredCheckNames = @("Quality", "Test")
$githubActionsAppSlug = "github-actions"

function Get-OptionalPropertyValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

. (Join-Path $PSScriptRoot "..\agent\_common.ps1")

$repoRoot = Set-RepoRoot
$currentScript = [System.IO.Path]::GetFullPath($PSCommandPath)
$workspaceScript = [System.IO.Path]::GetFullPath((Join-Path `
    $repoRoot "scripts\github\verify-main-protection.ps1"
))
if (-not [string]::Equals(
    $currentScript,
    $workspaceScript,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    $null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
}
Assert-GhAuthenticated
$binding = Get-GitHubRepositoryBinding
$repo = [string]$binding.nameWithOwner

$appRaw = Invoke-Gh @(
    "api", "--hostname", [string]$binding.host,
    "-H", "Accept: application/vnd.github+json",
    "-H", "X-GitHub-Api-Version: 2026-03-10",
    "apps/$githubActionsAppSlug"
)
$githubActionsApp = $appRaw | ConvertFrom-Json
$resolvedAppSlug = Get-OptionalPropertyValue -Object $githubActionsApp -Name "slug"
$resolvedAppId = Get-OptionalPropertyValue -Object $githubActionsApp -Name "id"
if (-not [string]::Equals(
    [string]$resolvedAppSlug,
    $githubActionsAppSlug,
    [System.StringComparison]::Ordinal
)) {
    throw "The GitHub API response did not identify the expected '$githubActionsAppSlug' app."
}

[long]$githubActionsAppId = 0
if (
    $null -eq $resolvedAppId -or
    -not [long]::TryParse([string]$resolvedAppId, [ref]$githubActionsAppId) -or
    $githubActionsAppId -le 0
) {
    throw "The GitHub API returned an invalid GitHub Actions app ID."
}

$repoRaw = Invoke-Gh @(
    "api", "--hostname", [string]$binding.host,
    "-H", "Accept: application/vnd.github+json",
    "-H", "X-GitHub-Api-Version: 2026-03-10",
    "repos/$repo"
)
$r = $repoRaw | ConvertFrom-Json

$raw = Invoke-Gh @(
    "api", "--hostname", [string]$binding.host,
    "-H", "Accept: application/vnd.github+json",
    "-H", "X-GitHub-Api-Version: 2026-03-10",
    "repos/$repo/branches/$Branch/protection"
)
$p = $raw | ConvertFrom-Json

$requiredStatusChecks = Get-OptionalPropertyValue -Object $p -Name "required_status_checks"
$configuredChecks = @()
$strictStatusChecks = $false

if ($null -ne $requiredStatusChecks) {
    $checksProperty = $requiredStatusChecks.PSObject.Properties["checks"]
    if ($null -ne $checksProperty -and $null -ne $checksProperty.Value) {
        $configuredChecks = @(
            $checksProperty.Value | ForEach-Object {
                $context = Get-OptionalPropertyValue -Object $_ -Name "context"
                $appIdValue = Get-OptionalPropertyValue -Object $_ -Name "app_id"
                $appId = $null
                [long]$parsedAppId = 0
                if (
                    $null -ne $appIdValue -and
                    [long]::TryParse([string]$appIdValue, [ref]$parsedAppId)
                ) {
                    $appId = $parsedAppId
                }

                [pscustomobject][ordered]@{
                    context = [string]$context
                    appId   = $appId
                }
            }
        )
    }

    $strictProperty = $requiredStatusChecks.PSObject.Properties["strict"]
    if ($null -ne $strictProperty) {
        $strictStatusChecks = [bool]$strictProperty.Value
    }
}

$expectedChecks = @(
    $requiredCheckNames | ForEach-Object {
        [pscustomobject][ordered]@{
            context = $_
            appId   = $githubActionsAppId
        }
    }
)
$missingChecks = @(
    $expectedChecks | Where-Object {
        $expectedCheck = $_
        @($configuredChecks | Where-Object {
            [string]::Equals(
                [string]$_.context,
                [string]$expectedCheck.context,
                [System.StringComparison]::Ordinal
            ) -and $_.appId -eq $expectedCheck.appId
        }).Count -eq 0
    }
)
$unexpectedChecks = @(
    $configuredChecks | Where-Object {
        $configuredCheck = $_
        @($expectedChecks | Where-Object {
            [string]::Equals(
                [string]$_.context,
                [string]$configuredCheck.context,
                [System.StringComparison]::Ordinal
            ) -and $_.appId -eq $configuredCheck.appId
        }).Count -eq 0
    }
)
$requiredChecksConfigured = (
    $configuredChecks.Count -eq $expectedChecks.Count -and
    $missingChecks.Count -eq 0 -and
    $unexpectedChecks.Count -eq 0
)

$prRule = Get-OptionalPropertyValue -Object $p -Name "required_pull_request_reviews"
$pullRequestRequired = ($null -ne $prRule)
$requiredApprovalCount = -1
$codeOwnerReviewRequired = $false
$lastPushApprovalRequired = $false

if ($pullRequestRequired) {
    $approvalProp = $prRule.PSObject.Properties["required_approving_review_count"]
    if ($null -ne $approvalProp) {
        $requiredApprovalCount = [int]$approvalProp.Value
    }

    $codeOwnerProp = $prRule.PSObject.Properties["require_code_owner_reviews"]
    if ($null -ne $codeOwnerProp) {
        $codeOwnerReviewRequired = [bool]$codeOwnerProp.Value
    }

    $lastPushProp = $prRule.PSObject.Properties["require_last_push_approval"]
    if ($null -ne $lastPushProp) {
        $lastPushApprovalRequired = [bool]$lastPushProp.Value
    }
}

$result = [ordered]@{
    repository                  = $repo
    branch                      = $Branch
    githubActionsAppId          = $githubActionsAppId
    requiredChecksConfigured    = $requiredChecksConfigured
    configuredChecks            = $configuredChecks
    missingChecks               = $missingChecks
    unexpectedChecks            = $unexpectedChecks
    strictStatusChecks          = $strictStatusChecks
    enforceAdmins               = [bool]$p.enforce_admins.enabled
    pullRequestRequired         = $pullRequestRequired
    requiredApprovalCount       = $requiredApprovalCount
    codeOwnerReviewRequired     = $codeOwnerReviewRequired
    lastPushApprovalRequired    = $lastPushApprovalRequired
    linearHistory               = [bool]$p.required_linear_history.enabled
    forcePushAllowed            = [bool]$p.allow_force_pushes.enabled
    deletionAllowed             = [bool]$p.allow_deletions.enabled
    conversationResolution      = [bool]$p.required_conversation_resolution.enabled
    squashMergeAllowed          = [bool]$r.allow_squash_merge
    mergeCommitAllowed          = [bool]$r.allow_merge_commit
    rebaseMergeAllowed          = [bool]$r.allow_rebase_merge
    deleteBranchOnMerge         = [bool]$r.delete_branch_on_merge
}

$result | ConvertTo-Json -Depth 10

if (
    -not $result.requiredChecksConfigured -or
    -not $result.strictStatusChecks -or
    -not $result.enforceAdmins -or
    -not $result.pullRequestRequired -or
    $result.requiredApprovalCount -ne 0 -or
    $result.codeOwnerReviewRequired -or
    $result.lastPushApprovalRequired -or
    -not $result.linearHistory -or
    $result.forcePushAllowed -or
    $result.deletionAllowed -or
    -not $result.conversationResolution -or
    -not $result.squashMergeAllowed -or
    $result.mergeCommitAllowed -or
    $result.rebaseMergeAllowed -or
    -not $result.deleteBranchOnMerge
) {
    exit 2
}

exit 0
