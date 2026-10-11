[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40,64}$')][string]$ExpectedHeadSha,
    [Parameter()][ValidateNotNullOrEmpty()][string]$Title,
    [Parameter()][AllowEmptyString()][string]$Body,
    [Parameter()][switch]$Ready
)

. (Join-Path $PSScriptRoot "_common.ps1")

$updateTitle = $PSBoundParameters.ContainsKey("Title")
$updateBody = $PSBoundParameters.ContainsKey("Body")
if (-not $updateTitle -and -not $updateBody -and -not $Ready) {
    throw "Specify Title, Body, or Ready for the PR update."
}

$repoRoot = Set-RepoRoot
$null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Invoke-WithGuardedWorkflowLock -RepoRoot $repoRoot -Action {
    $state = Load-TaskState
    Assert-OriginExists
    Assert-GhAuthenticated
    Assert-CleanWorkingTree
    Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha)
    if ([int]$state.prNumber -ne $PrNumber) {
        throw "PR #$PrNumber is not the recorded task PR #$($state.prNumber)."
    }

    $snapshot = Get-VerifiedTaskHeadSnapshot `
        -PrNumber $PrNumber -State $state -ExpectedHeadSha $ExpectedHeadSha
    if ([string]$snapshot.pr.state -ne "OPEN") {
        throw "Only an OPEN task PR can be updated."
    }

    # A changed description or draft state invalidates the earlier review.
    $state = Set-TaskStateFields -Fields @{
        mergeReadyPrNumber = $null
        mergeReadySha = $null
        mergeReadyAt = $null
        mergeAttemptPrNumber = $null
        mergeAttemptHeadSha = $null
        mergeAttemptMethod = $null
        mergeAttemptAt = $null
    }

    $bodyPath = $null
    try {
        $editArguments = @("pr", "edit", "$PrNumber")
        if ($updateTitle) { $editArguments += @("--title", $Title) }
        if ($updateBody) {
            $bodyPath = Join-Path (Split-Path -Parent (Get-TaskStatePath)) (
                ".codex-pr-body-" + [guid]::NewGuid().ToString("N") + ".txt"
            )
            $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Body)
            $stream = [System.IO.FileStream]::new(
                $bodyPath,
                [System.IO.FileMode]::CreateNew,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::None
            )
            try {
                $stream.Write($bytes, 0, $bytes.Length)
                $stream.Flush($true)
            }
            finally { $stream.Dispose() }
            $editArguments += @("--body-file", $bodyPath)
        }
        if ($updateTitle -or $updateBody) {
            Invoke-GhRepo $editArguments | Out-Null
        }

        # Recheck identity and SHA before a second remote mutation.
        $snapshot = Get-VerifiedTaskHeadSnapshot `
            -PrNumber $PrNumber -State $state -ExpectedHeadSha $ExpectedHeadSha
        if ([string]$snapshot.pr.state -ne "OPEN") {
            throw "Task PR is no longer OPEN after its metadata update."
        }
        if ($Ready -and [bool]$snapshot.pr.isDraft) {
            Invoke-GhRepo @("pr", "ready", "$PrNumber") | Out-Null
        }

        $after = Get-VerifiedTaskHeadSnapshot `
            -PrNumber $PrNumber -State $state -ExpectedHeadSha $ExpectedHeadSha
        if ([string]$after.pr.state -ne "OPEN") {
            throw "Task PR is no longer OPEN after its update."
        }
        if ($updateTitle -and -not [string]::Equals(
            [string]$after.pr.title, $Title, [System.StringComparison]::Ordinal
        )) {
            throw "Updated PR title does not match the requested value. Retry update-pr.ps1."
        }
        if ($updateBody -and -not [string]::Equals(
            [string]$after.pr.body, $Body, [System.StringComparison]::Ordinal
        )) {
            throw "Updated PR body does not match the requested value. Retry update-pr.ps1."
        }
        if ($Ready -and [bool]$after.pr.isDraft) {
            throw "PR is still a draft. Retry update-pr.ps1 with Ready."
        }

        Write-GuardedResult @{
            operation = "update-pr"
            number = $PrNumber
            url = [string]$after.pr.url
            title = [string]$after.pr.title
            draft = [bool]$after.pr.isDraft
            baseSha = [string]$after.baseSha
            headSha = $ExpectedHeadSha
        }
    }
    finally {
        if ($null -ne $bodyPath -and (Test-Path -LiteralPath $bodyPath)) {
            Remove-Item -LiteralPath $bodyPath -Force
        }
    }
}
