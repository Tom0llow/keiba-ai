[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Title,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Body,
    [Parameter()][switch]$Draft
)

. (Join-Path $PSScriptRoot "_common.ps1")

function Set-GuardedPrBinding {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]$Pr
    )

    $newPrNumber = [int]$Pr.number
    $fields = @{
        prNumber = $newPrNumber
        prUrl    = [string]$Pr.url
    }
    if ([int]$State.prNumber -ne $newPrNumber) {
        # Review and merge-attempt evidence belongs to one exact PR identity.
        $fields.mergeReadyPrNumber = $null
        $fields.mergeReadySha = $null
        $fields.mergeReadyAt = $null
        $fields.mergeAttemptPrNumber = $null
        $fields.mergeAttemptHeadSha = $null
        $fields.mergeAttemptMethod = $null
        $fields.mergeAttemptAt = $null
    }
    Set-TaskStateFields -Fields $fields | Out-Null
}

$repoRoot = Set-RepoRoot
$null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Invoke-WithGuardedWorkflowLock -RepoRoot $repoRoot -Action {
$state = Load-TaskState
Assert-OriginExists
Assert-GhAuthenticated
Assert-CleanWorkingTree
Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha)

$branch = [string]$state.branch
$base = [string]$state.base
$localSha = Invoke-Git @("rev-parse", "HEAD")

$coordinates = Get-TaskOriginCoordinates -State $state
$pushUrl = [string]$coordinates.pushUrl
$remoteText = Invoke-Git @("ls-remote", "--heads", $pushUrl, "refs/heads/$branch")
if ([string]::IsNullOrWhiteSpace($remoteText)) {
    throw "Remote branch missing. Run push-task.ps1 first."
}

$remoteSha = ($remoteText -split "\s+")[0]
if ($remoteSha -ne $localSha) {
    throw "Remote task branch is not at local HEAD."
}

$headSelector = "$($state.repositoryOwner):$branch"
$prFields = "number,url,title,state,baseRefName,headRefName,headRefOid,headRepository,headRepositoryOwner,isDraft"
$existingJson = Invoke-GhRepo @(
    "pr", "list",
    "--head", $branch,
    "--base", $base,
    "--state", "open",
    "--limit", "100",
    "--json", $prFields
)
$existing = @($existingJson | ConvertFrom-Json | Where-Object {
    Test-PrHeadMatchesTask -Pr $_ -State $state
})

if ($existing.Count -gt 1) {
    throw "Multiple open PRs matched guarded head '$headSelector' and base '$base'."
}

if ($existing.Count -gt 0) {
    $pr = $existing[0]
    Assert-PrMatchesTask -Pr $pr -State $state -AllowPrRebinding
    if ([string]$pr.headRefOid -ne $localSha) {
        throw "Existing PR HEAD does not match local HEAD."
    }

    Set-GuardedPrBinding -State $state -Pr $pr

    Write-GuardedResult @{
        operation = "create-pr"
        created   = $false
        number    = [int]$pr.number
        url       = [string]$pr.url
        title     = [string]$pr.title
        base      = [string]$pr.baseRefName
        head      = [string]$pr.headRefName
        draft     = [bool]$pr.isDraft
        headSha   = $localSha
    }
    return
}

$args = @(
    "pr", "create",
    "--base", $base,
    "--head", $headSelector,
    "--title", $Title,
    "--body", $Body
)
if ($Draft) { $args += "--draft" }

Invoke-GhRepo $args | Out-Null

$prJson = Invoke-GhRepo @(
    "pr", "list",
    "--head", $branch,
    "--base", $base,
    "--state", "open",
    "--limit", "100",
    "--json", $prFields
)
$created = @($prJson | ConvertFrom-Json | Where-Object {
    Test-PrHeadMatchesTask -Pr $_ -State $state
})
if ($created.Count -ne 1) {
    throw "Created PR could not be uniquely resolved for guarded head '$headSelector'."
}
$pr = $created[0]

Assert-PrMatchesTask -Pr $pr -State $state -AllowPrRebinding
if ([string]$pr.headRefOid -ne $localSha) {
    throw "Created PR HEAD does not match local HEAD."
}

Set-GuardedPrBinding -State $state -Pr $pr

Write-GuardedResult @{
    operation = "create-pr"
    created   = $true
    number    = [int]$pr.number
    url       = [string]$pr.url
    title     = [string]$pr.title
    base      = [string]$pr.baseRefName
    head      = [string]$pr.headRefName
    draft     = [bool]$pr.isDraft
    headSha   = [string]$pr.headRefOid
}
}
