function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$Value)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        return ([System.BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-GuardRepositoryPolicyId {
    param(
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    $normalizedRepoRoot = (Get-NormalizedGuardPath -Path $RepoRoot).ToLowerInvariant()
    $repositoryPolicyKey = $Repository.ToLowerInvariant() + "`n" + $normalizedRepoRoot
    return (Get-Sha256Hex -Value $repositoryPolicyKey).Substring(0, 24)
}

function Get-GuardInstallationDirectoryName {
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[0-9a-fA-F]{24}$')]
        [string]$RepositoryPolicyId,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
        [string]$SourceSha,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[0-9a-fA-F]{32}$')]
        [string]$InstallationId
    )

    return (
        $RepositoryPolicyId.ToLowerInvariant() + "-" +
        $SourceSha.ToLowerInvariant() + "-" +
        $InstallationId.ToLowerInvariant()
    )
}

function Get-CodexCliVersionFromOutput {
    param([Parameter(Mandatory = $true)][string]$VersionOutput)

    $normalizedOutput = $VersionOutput.Trim()
    if ($normalizedOutput -notmatch '^codex-cli (?<version>[0-9]+\.[0-9]+\.[0-9]+)$') {
        throw "Unexpected Codex CLI version output: '$normalizedOutput'."
    }
    return [string]$Matches.version
}

function Get-AllowedCodexCliVersions {
    param([Parameter(Mandatory = $true)][string]$VersionFile)

    $versions = @(Get-Content -LiteralPath $VersionFile -ErrorAction Stop | ForEach-Object {
        $_.Trim()
    } | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    })
    if ($versions.Count -eq 0) {
        throw "Codex CLI version policy is empty: $VersionFile"
    }
    foreach ($version in $versions) {
        if ($version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
            throw "Invalid Codex CLI version '$version' in $VersionFile."
        }
    }
    if (@($versions | Sort-Object -Unique).Count -ne $versions.Count) {
        throw "Codex CLI version policy contains duplicates: $VersionFile"
    }
    return $versions
}

function Assert-CodexCliVersionAllowed {
    param(
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$VersionFile
    )

    $allowedVersions = @(Get-AllowedCodexCliVersions -VersionFile $VersionFile)
    if ($Version -notin $allowedVersions) {
        throw "Codex CLI version '$Version' is not approved by $VersionFile."
    }
}

if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) {
    if ($null -eq ("KeibaAi.GuardPathResolver" -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace KeibaAi
{
    public static class GuardPathResolver
    {
        private const uint OpenExisting = 3;
        private const uint FileFlagBackupSemantics = 0x02000000;

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(
            string fileName,
            uint desiredAccess,
            FileShare shareMode,
            IntPtr securityAttributes,
            uint creationDisposition,
            uint flagsAndAttributes,
            IntPtr templateFile
        );

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetFinalPathNameByHandleW(
            SafeFileHandle file,
            StringBuilder filePath,
            uint filePathLength,
            uint flags
        );

        public static string Resolve(string path)
        {
            SafeFileHandle handle = CreateFileW(
                path,
                0,
                FileShare.Read | FileShare.Write | FileShare.Delete,
                IntPtr.Zero,
                OpenExisting,
                FileFlagBackupSemantics,
                IntPtr.Zero
            );
            if (handle.IsInvalid)
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }

            try
            {
                StringBuilder buffer = new StringBuilder(512);
                uint length = GetFinalPathNameByHandleW(
                    handle,
                    buffer,
                    (uint)buffer.Capacity,
                    0
                );
                if (length == 0)
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                }
                if (length >= buffer.Capacity)
                {
                    buffer = new StringBuilder((int)length + 1);
                    length = GetFinalPathNameByHandleW(
                        handle,
                        buffer,
                        (uint)buffer.Capacity,
                        0
                    );
                    if (length == 0 || length >= buffer.Capacity)
                    {
                        throw new Win32Exception(Marshal.GetLastWin32Error());
                    }
                }

                string resolved = buffer.ToString();
                if (resolved.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase))
                {
                    return @"\\" + resolved.Substring(8);
                }
                if (resolved.StartsWith(@"\\?\", StringComparison.OrdinalIgnoreCase))
                {
                    return resolved.Substring(4);
                }
                return resolved;
            }
            finally
            {
                handle.Dispose();
            }
        }
    }
}
'@
    }
}

function Get-NormalizedGuardPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($fullPath)
    if (-not [string]::Equals(
        $fullPath,
        $root,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        $fullPath = $fullPath.TrimEnd(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
    }
    return $fullPath
}

function Get-CanonicalGuardPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw "Guard path canonicalization is supported only on Windows."
    }
    $resolved = [KeibaAi.GuardPathResolver]::Resolve(
        [System.IO.Path]::GetFullPath($Path)
    )
    return Get-NormalizedGuardPath -Path $resolved
}

function Test-GuardPathWithinRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $normalizedPath = Get-NormalizedGuardPath -Path $Path
    $normalizedRoot = Get-NormalizedGuardPath -Path $Root
    if ([string]::Equals(
        $normalizedPath,
        $normalizedRoot,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        return $true
    }

    $rootPrefix = $normalizedRoot
    if (-not $rootPrefix.EndsWith(
        [System.IO.Path]::DirectorySeparatorChar.ToString(),
        [System.StringComparison]::Ordinal
    )) {
        $rootPrefix += [System.IO.Path]::DirectorySeparatorChar
    }
    return $normalizedPath.StartsWith(
        $rootPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Assert-PathOutsideKnownSandboxWritableRoots {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Role
    )

    if (Test-GuardPathWithinRoot -Path $Path -Root $RepoRoot) {
        throw "$Role must be outside the sandbox-writable repository."
    }
    $temporaryRoot = Get-NormalizedGuardPath -Path ([System.IO.Path]::GetTempPath())
    if (Test-GuardPathWithinRoot -Path $Path -Root $temporaryRoot) {
        throw "$Role must be outside the sandbox-writable temporary directory."
    }
}

function Assert-NoReparsePointInPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Role
    )

    $currentPath = [System.IO.Path]::GetFullPath($Path)
    while ($null -ne $currentPath) {
        $item = Get-Item -LiteralPath $currentPath -Force -ErrorAction Stop
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "$Role must not traverse a symbolic link, junction, or other reparse point: $currentPath"
        }

        $parent = [System.IO.Directory]::GetParent($currentPath)
        if ($null -eq $parent) {
            break
        }
        $currentPath = $parent.FullName
    }
}

function Assert-CanonicalPhysicalPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Role
    )

    $lexicalPath = Get-NormalizedGuardPath -Path $Path
    $physicalPath = Get-CanonicalGuardPath -Path $Path
    if (-not [string]::Equals(
        $lexicalPath,
        $physicalPath,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "$Role must use its canonical physical path; aliases are forbidden: '$lexicalPath' resolves to '$physicalPath'."
    }
}

function Assert-TrustedPowerShellHostPath {
    param(
        [Parameter(Mandatory = $true)][string]$ShellPath,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw "Guard installation and execution are supported only on Windows."
    }

    $shellItem = Get-Item -LiteralPath $ShellPath -Force -ErrorAction Stop
    if (
        $shellItem.PSIsContainer -or
        ($shellItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or
        $shellItem.Name -notin @("pwsh.exe", "powershell.exe")
    ) {
        throw "Guarded execution requires a regular pwsh.exe or powershell.exe executable."
    }
    Assert-NoReparsePointInPath -Path $ShellPath -Role "PowerShell executable"
    Assert-CanonicalPhysicalPath -Path $ShellPath -Role "PowerShell executable"

    if (Test-GuardPathWithinRoot -Path $ShellPath -Root $RepoRoot) {
        throw "PowerShell executable must be outside the writable repository."
    }

    $windowsRoot = [System.IO.Directory]::GetParent(
        [System.Environment]::SystemDirectory
    ).FullName
    $trustedShellRoots = @(
        $windowsRoot,
        [System.Environment]::GetFolderPath(
            [System.Environment+SpecialFolder]::ProgramFiles
        ),
        [System.Environment]::GetFolderPath(
            [System.Environment+SpecialFolder]::ProgramFilesX86
        )
    ) | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and
        (Test-Path -LiteralPath $_ -PathType Container)
    } | ForEach-Object {
        Get-CanonicalGuardPath -Path $_
    } | Sort-Object -Unique

    $trustedShell = @($trustedShellRoots | Where-Object {
        Test-GuardPathWithinRoot -Path $ShellPath -Root $_
    }).Count -gt 0
    if (-not $trustedShell) {
        throw "PowerShell executable must be installed under the Windows or Program Files directory."
    }
}

function Assert-TrustedCommandPath {
    param(
        [Parameter(Mandatory = $true)][string]$CommandPath,
        [Parameter(Mandatory = $true)][string[]]$ExpectedFileNames,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Role
    )

    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw "$Role validation is supported only on Windows."
    }

    $commandItem = Get-Item -LiteralPath $CommandPath -Force -ErrorAction Stop
    if (
        $commandItem.PSIsContainer -or
        ($commandItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or
        $commandItem.Name -notin $ExpectedFileNames
    ) {
        throw "$Role must be a regular expected command file: $($ExpectedFileNames -join ', ')."
    }

    Assert-NoReparsePointInPath -Path $CommandPath -Role $Role
    Assert-CanonicalPhysicalPath -Path $CommandPath -Role $Role
    Assert-PathOutsideKnownSandboxWritableRoots `
        -Path $CommandPath `
        -RepoRoot $RepoRoot `
        -Role $Role

    return Get-NormalizedGuardPath -Path $CommandPath
}

function Resolve-TrustedCommandPath {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$ExpectedFileNames,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Role
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) {
        throw "Required command '$Name' was not found in PATH."
    }

    $pathProperty = $command.PSObject.Properties["Path"]
    if ($null -eq $pathProperty -or [string]::IsNullOrWhiteSpace([string]$pathProperty.Value)) {
        throw "$Role must resolve to a filesystem command, not '$($command.CommandType)'."
    }

    $resolvedCommandPath = Get-CanonicalGuardPath -Path ([string]$pathProperty.Value)
    return Assert-TrustedCommandPath `
        -CommandPath $resolvedCommandPath `
        -ExpectedFileNames $ExpectedFileNames `
        -RepoRoot $RepoRoot `
        -Role $Role
}
