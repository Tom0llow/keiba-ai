[CmdletBinding()]
param(
    [Parameter()][string]$CodexHome,
    [Parameter()][string]$CodexExecutablePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:InstallerCommandOutputRoot = $null

. (Join-Path $PSScriptRoot "..\agent\_path-security.ps1")

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$ArgumentList = @()
    )

    if ([string]::IsNullOrWhiteSpace([string]$script:InstallerCommandOutputRoot)) {
        throw "Installer command output directory is not initialized."
    }
    $outputId = [guid]::NewGuid().ToString("N")
    $stdoutPath = Join-Path $script:InstallerCommandOutputRoot ".codex-install-$outputId.stdout"
    $stderrPath = Join-Path $script:InstallerCommandOutputRoot ".codex-install-$outputId.stderr"

    try {
        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $FilePath @ArgumentList 1> $stdoutPath 2> $stderrPath
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorAction
        }

        $stdout = Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
        if ($exitCode -ne 0) {
            $detail = @($stdout, $stderr) | Where-Object {
                -not [string]::IsNullOrWhiteSpace([string]$_)
            }
            throw "Command failed ($exitCode): $FilePath $($ArgumentList -join ' ')`n$($detail -join "`n")"
        }
        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            Write-Verbose $stderr.Trim()
        }
        if ($null -eq $stdout) {
            return ""
        }
        return $stdout.Trim()
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Enter-GuardInstallationLock {
    param([Parameter(Mandatory = $true)][string]$DotGit)

    $lockPath = Join-Path $DotGit "codex-workflow.lock"
    if (Test-Path -LiteralPath $lockPath) {
        $lockItem = Get-Item -LiteralPath $lockPath -Force -ErrorAction Stop
        if (
            $lockItem.PSIsContainer -or
            ($lockItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
        ) {
            throw "Guard installation lock must be a regular file: $lockPath"
        }
    }

    try {
        return [System.IO.File]::Open(
            $lockPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    }
    catch [System.IO.IOException] {
        throw "Another guarded workflow or guard installation is active: $lockPath"
    }
}

function Publish-ImmutableGuardInstallation {
    param(
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$GuardRoot,
        [Parameter(Mandatory = $true)][string]$GuardStoreRoot
    )

    $resolvedStoreRoot = [System.IO.Path]::GetFullPath($GuardStoreRoot)
    $storePrefix = $resolvedStoreRoot + [System.IO.Path]::DirectorySeparatorChar
    foreach ($path in @($StagingRoot, $GuardRoot)) {
        $resolvedPath = [System.IO.Path]::GetFullPath($path)
        if (-not $resolvedPath.StartsWith(
            $storePrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Immutable guard path escaped the Codex user guard store: $resolvedPath"
        }
    }

    if (-not (Test-Path -LiteralPath $StagingRoot -PathType Container)) {
        throw "Guard staging directory is missing: $StagingRoot"
    }
    if (Test-Path -LiteralPath $GuardRoot) {
        throw "Refusing to overwrite immutable guard installation: $GuardRoot"
    }

    Move-Item -LiteralPath $StagingRoot -Destination $GuardRoot
}

function ConvertTo-GitHubRemoteCoordinates {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Role
    )

    $remoteUrl = $Url.Trim()
    $path = $null
    if ($remoteUrl -match '^https://github\.com/(?<path>[^?#]+?)(?:\.git)?/?$') {
        $path = [string]$Matches.path
    }
    elseif ($remoteUrl -match '^ssh://git@github\.com/(?<path>[^?#]+?)(?:\.git)?/?$') {
        $path = [string]$Matches.path
    }
    elseif ($remoteUrl -match '^git@github\.com:(?<path>[^?#]+?)(?:\.git)?/?$') {
        $path = [string]$Matches.path
    }
    else {
        throw "Guard installation requires a github.com $Role URL; found '$remoteUrl'."
    }

    $path = $path.Trim('/').TrimEnd('/')
    if ($path.EndsWith('.git', [System.StringComparison]::OrdinalIgnoreCase)) {
        $path = $path.Substring(0, $path.Length - 4)
    }
    if ($path -notmatch '^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+$') {
        throw "Could not derive a safe GitHub repository identity from $Role URL '$remoteUrl'."
    }

    return [pscustomobject]@{
        nameWithOwner = $path
        url           = $remoteUrl
    }
}

function ConvertTo-StarlarkString {
    param([Parameter(Mandatory = $true)][string]$Value)

    if ($Value.Contains("`r") -or $Value.Contains("`n")) {
        throw "Execpolicy values must not contain newlines."
    }
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
}

function New-GuardExecPolicyText {
    param(
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40,64}$')][string]$SourceSha,
        [Parameter(Mandatory = $true)][string]$ShellPath,
        [Parameter(Mandatory = $true)][string]$GitPath,
        [Parameter(Mandatory = $true)][string]$GhPath,
        [Parameter(Mandatory = $true)][string]$CodexPath,
        [Parameter(Mandatory = $true)][string[]]$AutonomousPaths,
        [Parameter(Mandatory = $true)][string]$MergePath,
        [Parameter(Mandatory = $true)][string[]]$ForbiddenWorkspacePaths
    )

    $allPaths = @($ShellPath, $GitPath, $GhPath, $CodexPath) + $AutonomousPaths + @($MergePath) + $ForbiddenWorkspacePaths
    foreach ($path in $allPaths) {
        if (-not [System.IO.Path]::IsPathRooted($path)) {
            throw "Generated execpolicy accepts only absolute paths: $path"
        }
    }

    $startPath = @($AutonomousPaths | Where-Object {
        [System.IO.Path]::GetFileName($_) -eq "start-task.ps1"
    })
    $workspaceStartPath = @($ForbiddenWorkspacePaths | Where-Object {
        [System.IO.Path]::GetFileName($_) -eq "start-task.ps1"
    })
    if ($startPath.Count -ne 1 -or $workspaceStartPath.Count -ne 1) {
        throw "Generated execpolicy requires one installed and one workspace start-task path."
    }

    $shellLiteral = ConvertTo-StarlarkString -Value $ShellPath
    $gitLiteral = ConvertTo-StarlarkString -Value $GitPath
    $ghLiteral = ConvertTo-StarlarkString -Value $GhPath
    $codexLiteral = ConvertTo-StarlarkString -Value $CodexPath
    $autonomousPathLines = ($AutonomousPaths | ForEach-Object {
        "            $(ConvertTo-StarlarkString -Value $_),"
    }) -join "`n"
    $workspacePathLines = ($ForbiddenWorkspacePaths | ForEach-Object {
        "            $(ConvertTo-StarlarkString -Value $_),"
    }) -join "`n"
    $mergePathLiteral = ConvertTo-StarlarkString -Value $MergePath
    $startPathLiteral = ConvertTo-StarlarkString -Value ([string]$startPath[0])
    $workspaceStartLiteral = ConvertTo-StarlarkString -Value ([string]$workspaceStartPath[0])

    return @"
# Managed by scripts/setup/install-guarded-wrappers.ps1.
# Repository: $Repository
# Guard source: $SourceSha
# Do not edit manually; reinstall from reviewed protected main.

prefix_rule(
    pattern = [
        $shellLiteral,
        "-NoProfile",
        "-File",
        [
$autonomousPathLines
        ],
    ],
    decision = "allow",
    justification = "Run the reviewed, hash-verified guard installed at this repository's protected absolute path.",
    match = [
        [$shellLiteral, "-NoProfile", "-File", $startPathLiteral, "-TaskName", "example"],
    ],
)

prefix_rule(
    pattern = [$shellLiteral, "-NoProfile", "-File", $mergePathLiteral],
    decision = "prompt",
    justification = "Final merge requires explicit approval of the exact MERGE_READY HEAD.",
    match = [
        [$shellLiteral, "-NoProfile", "-File", $mergePathLiteral, "-PrNumber", "1", "-ExpectedHeadSha", "0123456789012345678901234567890123456789"],
    ],
)

prefix_rule(
    pattern = [
        $shellLiteral,
        "-NoProfile",
        "-File",
        [
$workspacePathLines
        ],
    ],
    decision = "forbidden",
    justification = "Workspace wrapper sources are mutable; invoke only the installed absolute guard path.",
    match = [
        [$shellLiteral, "-NoProfile", "-File", $workspaceStartLiteral, "-TaskName", "example"],
    ],
)

# The recorded Git executable is used only as a child of the installed wrapper.
# A top-level invocation remains human-gated, and destructive clean/global
# working-directory forms fail closed.
prefix_rule(
    pattern = [$gitLiteral, "clean"],
    decision = "forbidden",
    justification = "Raw clean can irreversibly delete ignored or untracked content.",
)

prefix_rule(
    pattern = [$gitLiteral, "-C"],
    decision = "forbidden",
    justification = "Raw Git working-directory overrides bypass repository-scoped command rules.",
)

prefix_rule(
    pattern = [$gitLiteral],
    decision = "prompt",
    justification = "Top-level use of the installed guard's Git executable requires explicit approval.",
)

# The recorded GitHub CLI executable is used only as a child of the installed
# wrapper. Every top-level invocation fails closed so it cannot bypass the
# repository, PR, and exact-HEAD checks enforced by those wrappers.
prefix_rule(
    pattern = [$ghLiteral],
    decision = "forbidden",
    justification = "Use the installed guarded wrappers for all GitHub operations.",
)

# A nested Codex process could otherwise request its own sandbox or approval
# settings. Only the human-run installer invokes this recorded executable.
prefix_rule(
    pattern = [$codexLiteral],
    decision = "forbidden",
    justification = "Nested Codex execution is outside the guarded workflow.",
)
"@
}

$scriptsRoot = [System.IO.Directory]::GetParent($PSScriptRoot).FullName
$repoRoot = [System.IO.Path]::GetFullPath(
    [System.IO.Directory]::GetParent($scriptsRoot).FullName
)
Assert-NoReparsePointInPath -Path $repoRoot -Role "Repository checkout"
Assert-CanonicalPhysicalPath -Path $repoRoot -Role "Repository checkout"
Set-Location -LiteralPath $repoRoot

$dotGit = Join-Path $repoRoot ".git"
if (-not (Test-Path -LiteralPath $dotGit -PathType Container)) {
    throw "Guard installation requires a standard checkout with a .git directory."
}
$dotGitItem = Get-Item -LiteralPath $dotGit -Force
if ($dotGitItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
    throw "The .git directory must not be a symbolic link or junction."
}
Assert-NoReparsePointInPath -Path $dotGit -Role "Repository Git directory"
Assert-CanonicalPhysicalPath -Path $dotGit -Role "Repository Git directory"
$script:InstallerCommandOutputRoot = $dotGit

$installationLock = Enter-GuardInstallationLock -DotGit $dotGit
try {

$currentProcess = Get-Process -Id $PID
$shellPath = [System.IO.Path]::GetFullPath([string]$currentProcess.Path)
Assert-TrustedPowerShellHostPath -ShellPath $shellPath -RepoRoot $repoRoot

$gitPath = Resolve-TrustedCommandPath `
    -Name "git" `
    -ExpectedFileNames @("git.exe") `
    -RepoRoot $repoRoot `
    -Role "Git executable"
$ghPath = Resolve-TrustedCommandPath `
    -Name "gh" `
    -ExpectedFileNames @("gh.exe") `
    -RepoRoot $repoRoot `
    -Role "GitHub CLI executable"
$tarPath = Resolve-TrustedCommandPath `
    -Name "tar" `
    -ExpectedFileNames @("tar.exe") `
    -RepoRoot $repoRoot `
    -Role "tar executable"
$codexPath = if ([string]::IsNullOrWhiteSpace($CodexExecutablePath)) {
    Resolve-TrustedCommandPath `
        -Name "codex.exe" `
        -ExpectedFileNames @("codex.exe") `
        -RepoRoot $repoRoot `
        -Role "Native Codex CLI executable"
}
else {
    Assert-TrustedCommandPath `
        -CommandPath $CodexExecutablePath `
        -ExpectedFileNames @("codex.exe") `
        -RepoRoot $repoRoot `
        -Role "Native Codex CLI executable"
}
$codexVersionOutput = Invoke-Checked -FilePath $codexPath -ArgumentList @("--version")
$codexVersion = Get-CodexCliVersionFromOutput -VersionOutput $codexVersionOutput
$codexVersionPolicyPath = Join-Path $repoRoot "scripts\guard-tests\codex-cli-version.txt"
Assert-CodexCliVersionAllowed `
    -Version $codexVersion `
    -VersionFile $codexVersionPolicyPath

if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        $CodexHome = $env:CODEX_HOME
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        $CodexHome = Join-Path $env:USERPROFILE ".codex"
    }
    else {
        throw "Specify -CodexHome because neither CODEX_HOME nor USERPROFILE is available."
    }
}
$resolvedCodexHome = [System.IO.Path]::GetFullPath($CodexHome)
if (-not (Test-Path -LiteralPath $resolvedCodexHome)) {
    throw "Codex home must already exist before guard installation: $resolvedCodexHome"
}
$codexHomeItem = Get-Item -LiteralPath $resolvedCodexHome -Force -ErrorAction Stop
if (
    -not $codexHomeItem.PSIsContainer -or
    ($codexHomeItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
) {
    throw "Codex home must be a real directory, not a symbolic link or junction."
}
Assert-NoReparsePointInPath -Path $resolvedCodexHome -Role "Codex home"
Assert-CanonicalPhysicalPath -Path $resolvedCodexHome -Role "Codex home"
Assert-PathOutsideKnownSandboxWritableRoots `
    -Path $resolvedCodexHome `
    -RepoRoot $repoRoot `
    -Role "Codex home"

$rulesRoot = Join-Path $resolvedCodexHome "rules"
if (-not (Test-Path -LiteralPath $rulesRoot)) {
    New-Item -ItemType Directory -Path $rulesRoot | Out-Null
}
$rulesRootItem = Get-Item -LiteralPath $rulesRoot -Force -ErrorAction Stop
if (
    -not $rulesRootItem.PSIsContainer -or
    ($rulesRootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
) {
    throw "Codex user rules path must be a real directory, not a symbolic link or junction."
}
Assert-NoReparsePointInPath -Path $rulesRoot -Role "Codex user rules directory"
Assert-CanonicalPhysicalPath -Path $rulesRoot -Role "Codex user rules directory"
Assert-PathOutsideKnownSandboxWritableRoots `
    -Path $rulesRoot `
    -RepoRoot $repoRoot `
    -Role "Codex user rules directory"

$currentBranch = Invoke-Checked -FilePath $gitPath -ArgumentList @("branch", "--show-current")
if ($currentBranch -ne "main") {
    throw "Install the guard only from local main; current branch is '$currentBranch'."
}

$status = Invoke-Checked -FilePath $gitPath -ArgumentList @(
    "status", "--porcelain=v1", "--untracked-files=all"
)
if (-not [string]::IsNullOrWhiteSpace($status)) {
    throw "Install the guard only from a clean working tree.`n$status"
}

$fetchUrlText = Invoke-Checked -FilePath $gitPath -ArgumentList @(
    "remote", "get-url", "--all", "origin"
)
$pushUrlText = Invoke-Checked -FilePath $gitPath -ArgumentList @(
    "remote", "get-url", "--push", "--all", "origin"
)
$fetchUrls = @($fetchUrlText -split "`r?`n" | Where-Object {
    -not [string]::IsNullOrWhiteSpace($_)
})
$pushUrls = @($pushUrlText -split "`r?`n" | Where-Object {
    -not [string]::IsNullOrWhiteSpace($_)
})
if ($fetchUrls.Count -ne 1 -or $pushUrls.Count -ne 1) {
    throw "Origin must have exactly one fetch URL and one resolved push URL."
}
$fetchRemote = ConvertTo-GitHubRemoteCoordinates -Url ([string]$fetchUrls[0]) -Role "fetch"
$pushRemote = ConvertTo-GitHubRemoteCoordinates -Url ([string]$pushUrls[0]) -Role "push"
if (-not [string]::Equals(
    [string]$fetchRemote.nameWithOwner,
    [string]$pushRemote.nameWithOwner,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Origin push repository '$($pushRemote.nameWithOwner)' does not match fetch repository '$($fetchRemote.nameWithOwner)'."
}

$null = Invoke-Checked -FilePath $gitPath -ArgumentList @(
    "fetch", "--prune", [string]$fetchRemote.url,
    "refs/heads/main`:refs/remotes/origin/main"
)

$sourceSha = Invoke-Checked -FilePath $gitPath -ArgumentList @("rev-parse", "origin/main")
$localSha = Invoke-Checked -FilePath $gitPath -ArgumentList @("rev-parse", "HEAD")
if ($sourceSha -notmatch '^[0-9a-fA-F]{40,64}$') {
    throw "origin/main resolved to an invalid commit ID: '$sourceSha'."
}
if (-not [string]::Equals(
    $sourceSha,
    $localSha,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Local main must exactly match origin/main before guard installation."
}

$sourcePaths = @(
    "scripts/agent/_common.ps1",
    "scripts/agent/_path-security.ps1",
    "scripts/agent/commit-task.ps1",
    "scripts/agent/create-pr.ps1",
    "scripts/agent/github-preflight.ps1",
    "scripts/agent/inspect-ci.ps1",
    "scripts/agent/inspect-pr.ps1",
    "scripts/agent/merge-ready.ps1",
    "scripts/agent/merge-task.ps1",
    "scripts/agent/push-task.ps1",
    "scripts/agent/start-task.ps1",
    "scripts/agent/wait-ci.ps1",
    "scripts/guard-tests/codex-cli-version.txt",
    "scripts/github/verify-main-protection.ps1"
)

foreach ($sourcePath in $sourcePaths) {
    $null = Invoke-Checked -FilePath $gitPath -ArgumentList @(
        "cat-file", "-e", "$sourceSha`:$sourcePath"
    )
}

$installId = [guid]::NewGuid().ToString("N")
$repositoryPolicyId = Get-GuardRepositoryPolicyId `
    -Repository ([string]$fetchRemote.nameWithOwner) `
    -RepoRoot $repoRoot
$guardDirectoryName = Get-GuardInstallationDirectoryName `
    -RepositoryPolicyId $repositoryPolicyId `
    -SourceSha $sourceSha `
    -InstallationId $installId

$guardStoreRoot = Join-Path $resolvedCodexHome "guarded-repositories"
if (-not (Test-Path -LiteralPath $guardStoreRoot)) {
    New-Item -ItemType Directory -Path $guardStoreRoot | Out-Null
}
$guardStoreItem = Get-Item -LiteralPath $guardStoreRoot -Force -ErrorAction Stop
if (
    -not $guardStoreItem.PSIsContainer -or
    ($guardStoreItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
) {
    throw "The guarded repository store must be a real directory, not a symbolic link or junction."
}
Assert-NoReparsePointInPath -Path $guardStoreRoot -Role "Guarded repository store"
Assert-CanonicalPhysicalPath -Path $guardStoreRoot -Role "Guarded repository store"
Assert-PathOutsideKnownSandboxWritableRoots `
    -Path $guardStoreRoot `
    -RepoRoot $repoRoot `
    -Role "Guarded repository store"

$guardRoot = Join-Path $guardStoreRoot $guardDirectoryName
Assert-PathOutsideKnownSandboxWritableRoots `
    -Path $guardRoot `
    -RepoRoot $repoRoot `
    -Role "Guard installation target"
$stagingRoot = Join-Path $guardStoreRoot ".$guardDirectoryName.staging"
$archivePath = Join-Path $guardStoreRoot ".$guardDirectoryName.tar"
$metadataRoot = Join-Path $dotGit "codex-guard"
$metadataStagingRoot = Join-Path $dotGit "codex-guard.metadata-$installId"
$metadataBackupPath = $null
$newGuardPublished = $false
$previousMetadataMoved = $false
$newMetadataActivated = $false
$policySwapStarted = $false
$policyActivated = $false
$retainPolicyRollback = $false
$guardStorePrefix = [System.IO.Path]::GetFullPath($guardStoreRoot) +
    [System.IO.Path]::DirectorySeparatorChar
$gitPrefix = [System.IO.Path]::GetFullPath($dotGit) +
    [System.IO.Path]::DirectorySeparatorChar

$autonomousEntrypoints = @(
    "scripts/agent/github-preflight.ps1",
    "scripts/agent/start-task.ps1",
    "scripts/agent/commit-task.ps1",
    "scripts/agent/push-task.ps1",
    "scripts/agent/create-pr.ps1",
    "scripts/agent/wait-ci.ps1",
    "scripts/agent/inspect-pr.ps1",
    "scripts/agent/inspect-ci.ps1",
    "scripts/agent/merge-ready.ps1"
)
$mergeEntrypoint = "scripts/agent/merge-task.ps1"
$allEntrypoints = @($autonomousEntrypoints + $mergeEntrypoint)
$installedEntrypointPaths = @($allEntrypoints | ForEach-Object {
    [System.IO.Path]::GetFullPath((Join-Path $guardRoot $_))
})
$workspaceForbiddenSources = @(
    $sourcePaths +
    "scripts/github/configure-main-protection.ps1" +
    "scripts/setup/install-guarded-wrappers.ps1"
)
$workspaceForbiddenPaths = @($workspaceForbiddenSources | ForEach-Object {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $_))
})
$installedAutonomousPaths = $installedEntrypointPaths[0..($autonomousEntrypoints.Count - 1)]
$installedMergePath = $installedEntrypointPaths[-1]

$policyFileName = "guarded-repository-$repositoryPolicyId.rules"
$policyPath = Join-Path $rulesRoot $policyFileName
$policyInstallTempPath = Join-Path $rulesRoot (
    ".$policyFileName.$installId.tmp"
)
$policyRollbackPath = Join-Path $rulesRoot (
    ".$policyFileName.$installId.rollback"
)
$generatedPolicyPath = Join-Path $stagingRoot "guard-execpolicy.rules"
$invocationPath = Join-Path $stagingRoot "guard-invocation.json"

$hadExistingPolicy = Test-Path -LiteralPath $policyPath
if ($hadExistingPolicy) {
    $existingPolicyItem = Get-Item -LiteralPath $policyPath -Force -ErrorAction Stop
    if (
        $existingPolicyItem.PSIsContainer -or
        ($existingPolicyItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
    ) {
        throw "Refusing to replace a non-regular managed policy path: $policyPath"
    }
    $existingPolicy = Get-Content -LiteralPath $policyPath -Raw
    $expectedRepositoryHeader = "# Repository: $($fetchRemote.nameWithOwner)"
    if (
        $existingPolicy -notmatch '(?m)^# Managed by scripts/setup/install-guarded-wrappers\.ps1\.$' -or
        -not $existingPolicy.Contains($expectedRepositoryHeader)
    ) {
        throw "Refusing to overwrite an execpolicy file not owned by this installer: $policyPath"
    }
}

foreach ($managedPath in @($guardRoot, $stagingRoot, $archivePath)) {
    $resolvedManagedPath = [System.IO.Path]::GetFullPath($managedPath)
    if (-not $resolvedManagedPath.StartsWith(
        $guardStorePrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Guard installation path escaped the Codex user guard store: $resolvedManagedPath"
    }
}

if (-not [System.IO.Path]::GetFullPath($metadataStagingRoot).StartsWith(
    $gitPrefix,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Guard metadata staging path escaped .git."
}

try {
    New-Item -ItemType Directory -Path $stagingRoot | Out-Null

    $archiveArguments = @(
        "-c", "core.autocrlf=false",
        "-c", "core.eol=lf",
        "archive",
        "--format=tar",
        "--output=$archivePath",
        $sourceSha,
        "--"
    ) + $sourcePaths
    $null = Invoke-Checked -FilePath $gitPath -ArgumentList $archiveArguments
    $null = Invoke-Checked -FilePath $tarPath -ArgumentList @(
        "-xf", $archivePath, "-C", $stagingRoot
    )

    $emptyHooksPath = Join-Path $stagingRoot "empty-hooks"
    New-Item -ItemType Directory -Path $emptyHooksPath | Out-Null

    $policyText = New-GuardExecPolicyText `
        -Repository ([string]$fetchRemote.nameWithOwner) `
        -SourceSha $sourceSha `
        -ShellPath $shellPath `
        -GitPath $gitPath `
        -GhPath $ghPath `
        -CodexPath $codexPath `
        -AutonomousPaths $installedAutonomousPaths `
        -MergePath $installedMergePath `
        -ForbiddenWorkspacePaths $workspaceForbiddenPaths
    [System.IO.File]::WriteAllText(
        $generatedPolicyPath,
        $policyText,
        [System.Text.UTF8Encoding]::new($false)
    )

    $scriptPaths = [ordered]@{}
    for ($index = 0; $index -lt $allEntrypoints.Count; $index++) {
        $scriptPaths[[string]$allEntrypoints[$index]] =
            [string]$installedEntrypointPaths[$index]
    }
    $invocation = [ordered]@{
        version            = 2
        repository         = [string]$fetchRemote.nameWithOwner
        repositoryPolicyId = $repositoryPolicyId
        installationId     = $installId
        sourceSha          = $sourceSha
        shellPath          = $shellPath
        gitPath            = $gitPath
        ghPath             = $ghPath
        codexPath          = $codexPath
        codexVersion       = $codexVersion
        guardRoot          = $guardRoot
        policyPath         = $policyPath
        scripts            = $scriptPaths
    }
    [System.IO.File]::WriteAllText(
        $invocationPath,
        ($invocation | ConvertTo-Json -Depth 10),
        [System.Text.UTF8Encoding]::new($false)
    )

    $policyCheckOutput = Invoke-Checked -FilePath $codexPath -ArgumentList @(
        "execpolicy", "check",
        "--rules", $generatedPolicyPath,
        "--",
        $shellPath, "-NoProfile", "-File", $installedAutonomousPaths[1],
        "-TaskName", "example"
    )
    try {
        $policyCheck = $policyCheckOutput | ConvertFrom-Json
    }
    catch {
        throw "Codex execpolicy self-check returned invalid JSON:`n$policyCheckOutput"
    }
    if ([string]$policyCheck.decision -ne "allow") {
        throw "Generated guard policy self-check decision was '$($policyCheck.decision)', not 'allow'."
    }

    $manifestEntries = @($sourcePaths | ForEach-Object {
        $sourcePath = $_
        $installedPath = [System.IO.Path]::GetFullPath((Join-Path $stagingRoot $sourcePath))
        $stagingPrefix = [System.IO.Path]::GetFullPath($stagingRoot) +
            [System.IO.Path]::DirectorySeparatorChar
        if (-not $installedPath.StartsWith(
            $stagingPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Archived path escaped staging root: $sourcePath"
        }

        $installedItem = Get-Item -LiteralPath $installedPath -Force -ErrorAction Stop
        if (
            $installedItem.PSIsContainer -or
            ($installedItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
        ) {
            throw "Guard source must be a regular file: $sourcePath"
        }

        $sourceBlob = Invoke-Checked -FilePath $gitPath -ArgumentList @(
            "rev-parse", "$sourceSha`:$sourcePath"
        )
        $installedBlob = Invoke-Checked -FilePath $gitPath -ArgumentList @(
            "hash-object", "--no-filters", $installedPath
        )
        if (-not [string]::Equals(
            $sourceBlob,
            $installedBlob,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Archived guard content differs from its commit blob: $sourcePath"
        }

        [ordered]@{
            sourcePath = $sourcePath
            sourceBlob = $sourceBlob
            sha256     = (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash
        }
    })

    $parseFailures = New-Object System.Collections.Generic.List[string]
    foreach ($sourcePath in ($sourcePaths | Where-Object { $_.EndsWith(".ps1") })) {
        $installedPath = Join-Path $stagingRoot $sourcePath
        $parseTokens = $null
        $parseErrors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile(
            $installedPath,
            [ref]$parseTokens,
            [ref]$parseErrors
        )
        foreach ($parseError in $parseErrors) {
            $parseFailures.Add("${sourcePath}:$($parseError.Extent.StartLineNumber): $($parseError.Message)")
        }
    }
    if ($parseFailures.Count -gt 0) {
        throw "Guarded script parse failure:`n$($parseFailures -join "`n")"
    }

    $manifest = [ordered]@{
        version            = 4
        repository         = [string]$fetchRemote.nameWithOwner
        repositoryPolicyId = $repositoryPolicyId
        installationId     = $installId
        repoRoot           = $repoRoot
        guardRoot          = $guardRoot
        shellPath          = $shellPath
        gitPath            = $gitPath
        ghPath             = $ghPath
        codexPath          = $codexPath
        codexVersion       = $codexVersion
        sourceRef          = "origin/main"
        sourceSha          = $sourceSha
        installedAt        = (Get-Date).ToUniversalTime().ToString("o")
        files              = $manifestEntries
    }
    $manifestPath = Join-Path $stagingRoot "guard-manifest.json"
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

    Publish-ImmutableGuardInstallation `
        -StagingRoot $stagingRoot `
        -GuardRoot $guardRoot `
        -GuardStoreRoot $guardStoreRoot
    $newGuardPublished = $true

    New-Item -ItemType Directory -Path $metadataStagingRoot | Out-Null
    Copy-Item `
        -LiteralPath (Join-Path $guardRoot "guard-invocation.json") `
        -Destination (Join-Path $metadataStagingRoot "guard-invocation.json")

    if (Test-Path -LiteralPath $metadataRoot) {
        $metadataItem = Get-Item -LiteralPath $metadataRoot -Force -ErrorAction Stop
        if ($metadataItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Refusing to replace reparse-point repository guard metadata: $metadataRoot"
        }
        $metadataBackupPath = Join-Path $dotGit (
            "codex-guard.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')-$installId"
        )
        Move-Item -LiteralPath $metadataRoot -Destination $metadataBackupPath
        $previousMetadataMoved = $true
    }

    Move-Item -LiteralPath $metadataStagingRoot -Destination $metadataRoot
    $newMetadataActivated = $true

    if ($hadExistingPolicy) {
        Copy-Item -LiteralPath $policyPath -Destination $policyRollbackPath
    }

    $installedGeneratedPolicyPath = Join-Path $guardRoot "guard-execpolicy.rules"
    Copy-Item -LiteralPath $installedGeneratedPolicyPath -Destination $policyInstallTempPath
    $policySwapStarted = $true
    Move-Item -LiteralPath $policyInstallTempPath -Destination $policyPath -Force
    $policyActivated = $true

    Write-Output "Installed guarded wrappers from origin/main $sourceSha"
    Write-Output "Location: $guardRoot"
    Write-Output "Repository invocation metadata: $metadataRoot"
    Write-Output "Installed repository-and-checkout-bound Codex policy: $policyPath"
    Write-Output "Restart Codex before invoking guarded wrappers."
    if ($null -ne $metadataBackupPath) {
        Write-Output "Previous repository metadata retained at: $metadataBackupPath"
    }
}
catch {
    $installationError = $_
    $rollbackErrors = New-Object System.Collections.Generic.List[string]

    if ($policySwapStarted) {
        try {
            if ($hadExistingPolicy -and (Test-Path -LiteralPath $policyRollbackPath)) {
                Copy-Item -LiteralPath $policyRollbackPath -Destination $policyPath -Force
            }
            elseif ($policyActivated -and (Test-Path -LiteralPath $policyPath)) {
                Remove-Item -LiteralPath $policyPath -Force
            }
        }
        catch {
            if ($hadExistingPolicy) {
                $retainPolicyRollback = $true
                $rollbackErrors.Add(
                    "policy: $($_.Exception.Message) Previous policy backup retained at '$policyRollbackPath'."
                )
            }
            else {
                $rollbackErrors.Add("policy: $($_.Exception.Message)")
            }
        }
    }

    if ($newMetadataActivated -and (Test-Path -LiteralPath $metadataRoot)) {
        try {
            Remove-Item -LiteralPath $metadataRoot -Recurse -Force
        }
        catch {
            $rollbackErrors.Add("repository metadata: $($_.Exception.Message)")
        }
    }
    if ($previousMetadataMoved -and (Test-Path -LiteralPath $metadataBackupPath)) {
        try {
            Move-Item -LiteralPath $metadataBackupPath -Destination $metadataRoot
        }
        catch {
            $rollbackErrors.Add("previous repository metadata: $($_.Exception.Message)")
        }
    }

    if ($newGuardPublished -and (Test-Path -LiteralPath $guardRoot)) {
        try {
            Remove-Item -LiteralPath $guardRoot -Recurse -Force
        }
        catch {
            $rollbackErrors.Add("guard installation: $($_.Exception.Message)")
        }
    }
    if ($rollbackErrors.Count -gt 0) {
        throw @"
Guard installation failed and rollback was incomplete.

Installation error:
$($installationError.Exception.Message)

Rollback errors:
- $($rollbackErrors -join "`n- ")
"@
    }
    throw $installationError
}
finally {
    foreach ($cleanupPath in @($archivePath, $stagingRoot)) {
        if (-not (Test-Path -LiteralPath $cleanupPath)) {
            continue
        }
        $resolvedCleanupPath = [System.IO.Path]::GetFullPath($cleanupPath)
        if (-not $resolvedCleanupPath.StartsWith(
            $guardStorePrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Cleanup path escaped the Codex user guard store: $resolvedCleanupPath"
        }
        Remove-Item -LiteralPath $resolvedCleanupPath -Recurse -Force
    }

    if (Test-Path -LiteralPath $metadataStagingRoot) {
        $resolvedMetadataStaging = [System.IO.Path]::GetFullPath($metadataStagingRoot)
        if (-not $resolvedMetadataStaging.StartsWith(
            $gitPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Metadata cleanup path escaped .git: $resolvedMetadataStaging"
        }
        Remove-Item -LiteralPath $resolvedMetadataStaging -Recurse -Force
    }


    $policyCleanupPaths = @($policyInstallTempPath)
    if (-not $retainPolicyRollback) {
        $policyCleanupPaths += $policyRollbackPath
    }
    foreach ($policyTemporaryPath in $policyCleanupPaths) {
        if (-not (Test-Path -LiteralPath $policyTemporaryPath)) {
            continue
        }
        $resolvedPolicyTemp = [System.IO.Path]::GetFullPath($policyTemporaryPath)
        $rulesPrefix = [System.IO.Path]::GetFullPath($rulesRoot) +
            [System.IO.Path]::DirectorySeparatorChar
        if (-not $resolvedPolicyTemp.StartsWith(
            $rulesPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Policy cleanup path escaped the Codex user rules directory: $resolvedPolicyTemp"
        }
        Remove-Item -LiteralPath $resolvedPolicyTemp -Force
    }
}
}
finally {
    $installationLock.Dispose()
}
