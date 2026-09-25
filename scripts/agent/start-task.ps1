[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$TaskName,
    [Parameter()][string]$BranchName,
    [Parameter()][ValidateNotNullOrEmpty()][string]$Base = "main"
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
$guardManifest = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Invoke-WithGuardedWorkflowLock -RepoRoot $repoRoot -Action {
$statePath = Get-TaskStatePath
if (Test-Path -LiteralPath $statePath) {
    $pendingState = Load-TaskState `
        -AllowDefaultBranch `
        -AllowPendingOperation "start"
    if ([string]$pendingState.pendingOperation -ne "start") {
        throw "An active guarded task already exists and is not a recoverable start operation."
    }
    if ([string]$pendingState.taskName -ne $TaskName) {
        throw "Pending task name '$($pendingState.taskName)' does not match '$TaskName'."
    }
    if ([string]$pendingState.base -ne $Base) {
        throw "Pending task base '$($pendingState.base)' does not match '$Base'."
    }
    if (
        -not [string]::IsNullOrWhiteSpace($BranchName) -and
        [string]$pendingState.branch -ne $BranchName
    ) {
        throw "Pending task branch '$($pendingState.branch)' does not match '$BranchName'."
    }

    Assert-CleanWorkingTree
    $pendingBranch = [string]$pendingState.branch
    $pendingStartSha = [string]$pendingState.startSha
    $coordinates = Get-TaskOriginCoordinates -State $pendingState
    $remoteBranch = Invoke-Git @(
        "ls-remote", "--heads", [string]$coordinates.pushUrl,
        "refs/heads/$pendingBranch"
    )
    if (-not [string]::IsNullOrWhiteSpace($remoteBranch)) {
        throw "Pending task recovery found an unexpected remote branch '$pendingBranch'."
    }

    $branchExists = Test-GitSuccess @(
        "show-ref", "--verify", "--quiet", "refs/heads/$pendingBranch"
    )
    if ($branchExists) {
        $branchSha = Invoke-Git @("rev-parse", "refs/heads/$pendingBranch")
        if (-not [string]::Equals(
            $branchSha,
            $pendingStartSha,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Pending task branch exists at an unexpected SHA; preserve it for manual review."
        }
    }

    $current = Get-CurrentBranch
    if ($current -eq [string]$pendingState.base) {
        if ($branchExists) {
            Invoke-Git @("switch", $pendingBranch) | Out-Null
        }
        else {
            Invoke-Git @("switch", "--create", $pendingBranch, $pendingStartSha) | Out-Null
        }
    }
    elseif ($current -eq $pendingBranch) {
        $currentSha = Invoke-Git @("rev-parse", "HEAD")
        if (-not [string]::Equals(
            $currentSha,
            $pendingStartSha,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Pending task checkout moved from its recorded starting SHA."
        }
    }
    else {
        throw "Pending task recovery requires '$($pendingState.base)' or '$pendingBranch'; current branch is '$current'."
    }

    Set-TaskStateFields `
        -AllowPendingOperation "start" `
        -Fields @{ pendingOperation = $null } | Out-Null

    Write-GuardedResult @{
        operation = "start-task"
        taskName  = [string]$pendingState.taskName
        branch    = $pendingBranch
        base      = [string]$pendingState.base
        startSha  = $pendingStartSha
        resumed   = $true
    }
    return
}

Assert-OriginExists
Assert-CleanWorkingTree
Assert-NoActiveTaskState

if ($Base -ne $script:DefaultBaseBranch) {
    throw "Autonomous tasks currently permit only base '$($script:DefaultBaseBranch)'."
}

$current = Get-CurrentBranch
if ($current -ne $Base) {
    throw "Start autonomous tasks from local '$Base'; current branch is '$current'."
}

if ([string]::IsNullOrWhiteSpace($BranchName)) {
    $BranchName = New-AgentBranchName -TaskName $TaskName
}
Assert-ValidAgentBranchName -Branch $BranchName

if (Test-GitSuccess @("show-ref", "--verify", "--quiet", "refs/heads/$BranchName")) {
    throw "Local branch '$BranchName' already exists."
}

$preflightScript = Join-Path $PSScriptRoot "github-preflight.ps1"
if (-not (Test-Path -LiteralPath $preflightScript)) {
    throw "Missing guarded preflight: $preflightScript"
}

try {
    $preflightText = Invoke-ExternalText -FilePath (Get-CurrentPowerShellPath) -ArgumentList @(
        "-NoProfile", "-File", $preflightScript
    )
}
catch {
    throw "GitHub preflight failed before task creation:`n$($_.Exception.Message)"
}

try {
    $preflight = $preflightText | ConvertFrom-Json
}
catch {
    throw "GitHub preflight did not return valid JSON:`n$preflightText"
}

$preflightSha = [string]$preflight.baseSha
if (
    [string]$preflight.status -ne "ok" -or
    [string]$preflight.operation -ne "github-preflight" -or
    [string]$preflight.baseBranch -ne $Base -or
    [string]::IsNullOrWhiteSpace([string]$preflight.repository) -or
    [string]::IsNullOrWhiteSpace([string]$preflight.repositoryOwner) -or
    -not [bool]$preflight.branchProtectionVerified -or
    [string]$preflight.baselineCi -ne "success" -or
    $preflightSha -notmatch '^[0-9a-fA-F]{40,64}$'
) {
    throw "GitHub preflight returned an invalid result:`n$preflightText"
}

$repository = Get-OriginGitHubCoordinates
if (
    -not [string]::Equals(
        [string]$preflight.repository,
        [string]$repository.nameWithOwner,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -or
    -not [string]::Equals(
        [string]$preflight.repositoryOwner,
        [string]$repository.owner,
        [System.StringComparison]::OrdinalIgnoreCase
    )
) {
    throw "GitHub preflight repository identity does not match origin."
}

$fetchUrl = [string]$repository.origin
Invoke-Git @(
    "fetch", "--prune", $fetchUrl,
    "refs/heads/$Base`:refs/remotes/origin/$Base"
) | Out-Null

if (-not (Test-GitSuccess @("rev-parse", "--verify", "origin/$Base"))) {
    throw "Remote base 'origin/$Base' was not found."
}

$startSha = Invoke-Git @("rev-parse", "origin/$Base")
if (-not [string]::Equals(
    $startSha.Trim(),
    $preflightSha.Trim(),
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "origin/$Base changed after preflight. Retry task creation from the new baseline."
}

Assert-GuardSourcesMatchCommit -Commit $startSha -Manifest $guardManifest

$pushUrl = [string]$repository.pushUrl
$remoteBranch = Invoke-Git @("ls-remote", "--heads", $pushUrl, "refs/heads/$BranchName")
if (-not [string]::IsNullOrWhiteSpace($remoteBranch)) {
    throw "Remote branch '$BranchName' already exists."
}

Save-TaskState `
    -RepoRoot $repoRoot `
    -Branch $BranchName `
    -Base $Base `
    -StartSha $startSha `
    -TaskName $TaskName `
    -Repository ([string]$repository.nameWithOwner) `
    -RepositoryOwner ([string]$repository.owner)

Invoke-Git @("switch", "--create", $BranchName, $startSha) | Out-Null

Set-TaskStateFields `
    -AllowPendingOperation "start" `
    -Fields @{ pendingOperation = $null } | Out-Null

Write-GuardedResult @{
    operation = "start-task"
    taskName  = $TaskName
    branch    = $BranchName
    base      = $Base
    startSha  = $startSha
    resumed   = $false
}
}
