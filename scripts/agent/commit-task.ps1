[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Message
)

. (Join-Path $PSScriptRoot "_common.ps1")

function Assert-PendingCommitResult {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedParentSha,
        [Parameter(Mandatory = $true)][string]$ExpectedTreeSha,
        [Parameter(Mandatory = $true)][string]$ExpectedMessage
    )

    $commitLine = (Invoke-Git @("rev-list", "--parents", "-n", "1", "HEAD")).Trim()
    $commitParts = @($commitLine -split "\s+")
    if ($commitParts.Count -ne 2) {
        throw "Pending commit recovery requires a single-parent commit."
    }
    if (-not [string]::Equals(
        [string]$commitParts[1],
        $ExpectedParentSha,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Recovered commit parent does not match the write-ahead task state."
    }

    $actualTreeSha = (Invoke-Git @("rev-parse", "HEAD^{tree}")).Trim()
    if (-not [string]::Equals(
        $actualTreeSha,
        $ExpectedTreeSha,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Recovered commit tree does not match the write-ahead task state."
    }

    $actualMessage = (Invoke-Git @("log", "-1", "--format=%s", "HEAD")).Trim()
    if (-not [string]::Equals(
        $actualMessage,
        $ExpectedMessage,
        [System.StringComparison]::Ordinal
    )) {
        throw "Recovered commit message does not match the write-ahead task state."
    }
}

$repoRoot = Set-RepoRoot
$null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Invoke-WithGuardedWorkflowLock -RepoRoot $repoRoot -Action {
$state = Load-TaskState -AllowPendingOperation "commit"
Assert-ConventionalCommitMessage -Message $Message
Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha) -IncludeWorktree

$pendingOperation = [string]$state.pendingOperation
if (
    -not [string]::IsNullOrWhiteSpace($pendingOperation) -and
    [string]$state.pendingCommitMessage -ne $Message
) {
    throw "Commit retry message does not match the pending guarded commit."
}

if ([string]::IsNullOrWhiteSpace($pendingOperation)) {
    $status = Invoke-Git @("status", "--porcelain=v1", "--untracked-files=all")
    if ([string]::IsNullOrWhiteSpace($status)) {
        throw "Nothing to commit."
    }

    $alreadyStaged = Invoke-Git @("diff", "--cached", "--name-only", "--")
    if (-not [string]::IsNullOrWhiteSpace($alreadyStaged)) {
        throw "Commit wrapper requires an empty index; preserve or unstage existing staged changes first."
    }

    $parentSha = (Invoke-Git @("rev-parse", "HEAD")).Trim()
    $state = Set-TaskStateFields -Fields @{
        pendingOperation       = "commit"
        pendingCommitPhase     = "staging"
        pendingCommitParentSha = $parentSha
        pendingCommitTreeSha   = $null
        pendingCommitMessage   = $Message
    }
}

$parentSha = [string]$state.pendingCommitParentSha
$currentSha = (Invoke-Git @("rev-parse", "HEAD")).Trim()
$resumed = $false

if ([string]$state.pendingCommitPhase -eq "staging") {
    if (-not [string]::Equals(
        $currentSha,
        $parentSha,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "HEAD changed before the pending commit tree was recorded."
    }

    Invoke-Git @("add", "-A", "--", ".") | Out-Null
    Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha) -IncludeWorktree

    $staged = Invoke-Git @("diff", "--cached", "--name-only")
    if ([string]::IsNullOrWhiteSpace($staged)) {
        throw "No staged changes."
    }

    Assert-NoSensitiveStagedPaths
    Invoke-Git @("diff", "--cached", "--check") | Out-Null
    $treeSha = (Invoke-Git @("write-tree")).Trim()
    $state = Set-TaskStateFields `
        -AllowPendingOperation "commit" `
        -Fields @{
            pendingCommitPhase   = "committing"
            pendingCommitTreeSha = $treeSha
        }
}
else {
    $treeSha = [string]$state.pendingCommitTreeSha
}

$currentSha = (Invoke-Git @("rev-parse", "HEAD")).Trim()
if ([string]::Equals(
    $currentSha,
    $parentSha,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    $indexTreeSha = (Invoke-Git @("write-tree")).Trim()
    if (-not [string]::Equals(
        $indexTreeSha,
        $treeSha,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Staged tree changed after the guarded commit intent was recorded."
    }
    Invoke-Git @("commit", "-m", $Message) | Out-Null
}
else {
    $resumed = $true
}

Assert-PendingCommitResult `
    -ExpectedParentSha $parentSha `
    -ExpectedTreeSha $treeSha `
    -ExpectedMessage $Message

$sha = (Invoke-Git @("rev-parse", "HEAD")).Trim()

# Any new commit invalidates a prior merge-ready result. Clearing the pending
# intent is the final state transition, so a failed write remains retryable.
Set-TaskStateFields `
    -AllowPendingOperation "commit" `
    -Fields @{
        headSha                 = $sha
        mergeReadyPrNumber      = $null
        mergeReadySha           = $null
        mergeReadyAt            = $null
        mergeAttemptPrNumber    = $null
        mergeAttemptHeadSha     = $null
        mergeAttemptMethod      = $null
        mergeAttemptAt          = $null
        pendingOperation        = $null
        pendingCommitPhase      = $null
        pendingCommitParentSha  = $null
        pendingCommitTreeSha    = $null
        pendingCommitMessage    = $null
    } | Out-Null

Write-GuardedResult @{
    operation = "commit-task"
    branch    = [string]$state.branch
    commit    = $sha
    message   = $Message
    resumed   = $resumed
}
}
