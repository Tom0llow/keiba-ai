[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("guard-native-" + [guid]::NewGuid().ToString("N"))
$previousEncoding = [Console]::OutputEncoding
try {
    $null = New-Item -ItemType Directory -Path $testRoot
    $probePath = Join-Path $testRoot "probe.exe"
    $compiler = Join-Path $env:SystemRoot "System32/WindowsPowerShell/v1.0/powershell.exe"
    $compileScript = @'
Add-Type -OutputAssembly '__PROBE__' -OutputType ConsoleApplication -TypeDefinition @"
using System;
using System.Text;
public static class Probe {
    public static int Main(string[] args) {
        var output = Console.OpenStandardOutput();
        var error = Console.OpenStandardError();
        foreach (string value in args) {
            byte[] line = Encoding.UTF8.GetBytes(Convert.ToBase64String(Encoding.UTF8.GetBytes(value)) + "\n");
            output.Write(line, 0, line.Length);
        }
        byte[] tail = Encoding.UTF8.GetBytes("\u65e5\u672c\u8a9e  \n");
        output.Write(tail, 0, tail.Length);
        byte[] diagnostic = Encoding.UTF8.GetBytes(new string('e', 131072));
        error.Write(diagnostic, 0, diagnostic.Length);
        return 0;
    }
}
"@
'@
    $compileScript = $compileScript.Replace("__PROBE__", $probePath.Replace("'", "''"))
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($compileScript))
    & $compiler -NoProfile -EncodedCommand $encoded
    if ($LASTEXITCODE -ne 0) { throw "Native fixture compilation failed." }

    . (Join-Path $repoRoot "scripts/agent/_common.ps1")
    $script:TrustedCommandOutputRoot = $testRoot
    [Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding(932)
    $arguments = @('fix: handle "quoted" values', '', 'C:\path with spaces\', "line one`nline two", ([string][char]0x65e5))
    $expected = ($arguments | ForEach-Object {
        [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_)) + "`n"
    }) -join ""
    $expected += ([string][char]0x65e5 + [char]0x672c + [char]0x8a9e + "  `n")
    $actual = Invoke-ExternalText -FilePath $probePath -ArgumentList $arguments -RawOutput
    if ($actual -cne $expected) {
        throw "Native arguments or UTF-8 stdout changed (including empty values, quotes, and trailing whitespace)."
    }
    if ([Console]::OutputEncoding.CodePage -ne 932) {
        throw "Native execution changed the caller's output encoding."
    }
    if (@(Get-ChildItem -LiteralPath $testRoot -Filter '.codex-command-*').Count -ne 0) {
        throw "Native execution left command-output files behind."
    }
    Write-Output "Native process regression passed."
}
finally {
    [Console]::OutputEncoding = $previousEncoding
    $resolvedRoot = [System.IO.Path]::GetFullPath($testRoot)
    $tempPrefix = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolvedRoot.StartsWith($tempPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a fixture outside the temporary directory."
    }
    Remove-Item -LiteralPath $resolvedRoot -Recurse -Force -ErrorAction SilentlyContinue
}
