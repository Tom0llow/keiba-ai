[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40,64}$')][string]$ExpectedHeadSha
)

. (Join-Path $PSScriptRoot "_common.ps1")

function Read-TaskCloseReceipt {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][int]$PrNumber,
        [Parameter(Mandatory = $true)][string]$ExpectedHeadSha
    )

    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Task close receipt must be a regular file."
    }
    $receipt = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    $prefix = "codex-task.closed-pr$PrNumber-$($ExpectedHeadSha.ToLowerInvariant())-"
    if (
        [int]$receipt.version -ne 1 -or
        [int]$receipt.prNumber -ne $PrNumber -or
        -not [string]::Equals([string]$receipt.headSha, $ExpectedHeadSha, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals([string]$receipt.repoRoot, $RepoRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$receipt.stateHash -notmatch '^[0-9a-fA-F]{64}$' -or
        [string]$receipt.archiveName -notmatch ('^' + [regex]::Escape($prefix) + '[0-9a-f]{32}\.json$')
    ) {
        throw "Task close receipt does not match the requested repository, PR, and SHA."
    }
    return $receipt
}

function Assert-TaskCloseIdentity {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][int]$PrNumber,
        [Parameter(Mandatory = $true)][string]$ExpectedHeadSha
    )

    if (
        [int]$State.version -notin @(6, 7) -or
        [int]$State.prNumber -ne $PrNumber -or
        -not [string]::Equals([string]$State.headSha, $ExpectedHeadSha, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals([string]$State.repoRoot, $RepoRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::IsNullOrWhiteSpace([string]$State.pendingOperation)
    ) {
        throw "Task state does not match the completed PR/SHA or has a pending operation."
    }
    $null = Get-TaskOriginCoordinates -State $State
    $pr = Get-PrObject -PrNumber $PrNumber
    Assert-PrMatchesTask -Pr $pr -State $State
    if (
        [string]$pr.state -ne "MERGED" -or
        [string]::IsNullOrWhiteSpace([string]$pr.mergedAt) -or
        -not [string]::Equals([string]$pr.headRefOid, $ExpectedHeadSha, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Task close requires the same PR in MERGED state at the expected HEAD SHA with a mergedAt timestamp."
    }
    return $pr
}

$repoRoot = Set-RepoRoot
$null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Invoke-WithGuardedWorkflowLock -RepoRoot $repoRoot -Action {
    Assert-OriginExists
    Assert-GhAuthenticated
    $statePath = Get-TaskStatePath
    $gitDirectory = Split-Path -Parent $statePath
    $receiptPath = Join-Path $gitDirectory (
        "codex-task-close-pr$PrNumber-$($ExpectedHeadSha.ToLowerInvariant()).json"
    )
    $receipt = $null
    if (Test-Path -LiteralPath $receiptPath) {
        $receipt = Read-TaskCloseReceipt `
            -Path $receiptPath -RepoRoot $repoRoot `
            -PrNumber $PrNumber -ExpectedHeadSha $ExpectedHeadSha
    }

    if (Test-Path -LiteralPath $statePath) {
        $state = Load-TaskState -AllowDefaultBranch
        $pr = Assert-TaskCloseIdentity `
            -State $state -RepoRoot $repoRoot `
            -PrNumber $PrNumber -ExpectedHeadSha $ExpectedHeadSha
        if ((Get-CurrentBranch) -eq [string]$state.branch) {
            $localSha = Invoke-Git @("rev-parse", "HEAD")
            if (-not [string]::Equals($localSha, $ExpectedHeadSha, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Local task HEAD changed. Preserve task identity for separate review."
            }
        }
        $stateHash = (Get-FileHash -LiteralPath $statePath -Algorithm SHA256).Hash
        if ($null -eq $receipt) {
            $receipt = [ordered]@{
                version = 1
                repoRoot = $repoRoot
                prNumber = $PrNumber
                headSha = $ExpectedHeadSha
                stateHash = $stateHash
                archiveName = "codex-task.closed-pr$PrNumber-$($ExpectedHeadSha.ToLowerInvariant())-$([guid]::NewGuid().ToString('N')).json"
            }
            $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes(($receipt | ConvertTo-Json))
            $temporaryReceiptPath = Join-Path $gitDirectory (
                ".codex-task-close-" + [guid]::NewGuid().ToString("N") + ".tmp"
            )
            $stream = $null
            try {
                $stream = [System.IO.FileStream]::new(
                    $temporaryReceiptPath, [System.IO.FileMode]::CreateNew,
                    [System.IO.FileAccess]::Write, [System.IO.FileShare]::None
                )
                $stream.Write($bytes, 0, $bytes.Length)
                $stream.Flush($true)
                $stream.Dispose()
                $stream = $null
                [System.IO.File]::Move($temporaryReceiptPath, $receiptPath)
            }
            finally {
                if ($null -ne $stream) { $stream.Dispose() }
                if (Test-Path -LiteralPath $temporaryReceiptPath) {
                    Remove-Item -LiteralPath $temporaryReceiptPath -Force
                }
            }
        }
        if ($stateHash -ne [string]$receipt.stateHash) {
            throw "Task state changed after close was prepared. Preserve the active state and receipt."
        }
        $archivePath = Join-Path $gitDirectory ([string]$receipt.archiveName)
        # File.Move refuses an existing destination and leaves all Git refs intact.
        [System.IO.File]::Move($statePath, $archivePath)
    }
    else {
        if ($null -eq $receipt) {
            throw "No active task state or matching task close receipt."
        }
        $archivePath = Join-Path $gitDirectory ([string]$receipt.archiveName)
    }

    $archive = Get-Item -LiteralPath $archivePath -Force -ErrorAction Stop
    if ($archive.PSIsContainer -or ($archive.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Closed task archive must be a regular file."
    }
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne [string]$receipt.stateHash) {
        throw "Closed task archive hash differs from the recorded state. Preserve the archive and receipt."
    }
    $state = Get-Content -LiteralPath $archivePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $pr = Assert-TaskCloseIdentity `
        -State $state -RepoRoot $repoRoot `
        -PrNumber $PrNumber -ExpectedHeadSha $ExpectedHeadSha

    Write-GuardedResult @{
        operation = "close-task"
        number = $PrNumber
        url = [string]$pr.url
        state = [string]$pr.state
        headSha = $ExpectedHeadSha
        archivePath = $archivePath
        stateHash = [string]$receipt.stateHash
    }
}
