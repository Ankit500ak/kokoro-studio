<#
.SYNOPSIS
    Package the large local data (excluded from git) into GitHub Release assets.

.DESCRIPTION
    Creates .zip parts under release-assets\ (gitignored), each safely under the
    2 GiB per-asset GitHub limit, covering:
      * backend\app\storage\media   - imported video library (subfolders split into parts)
      * videotemplate\              - template clips
      * backend\app\storage\kokoro.db - SQLite database (projects, library, uploads)

    Rends/ and audio/ are deliberately skipped: they are regeneratable output.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\pack-data.ps1 -Tag data-v1

.EXAMPLE
    # pack only the database
    powershell -ExecutionPolicy Bypass -File scripts\pack-data.ps1 -Tag data-v1 -SkipMedia -SkipTemplates
#>
param(
    [string]$OutDir = "",
    [string]$Tag = "data-v1",
    [string]$ReleaseName = "Kokoro Studio data",
    [int]$MaxPartMB = 1900,
    [switch]$SkipMedia,
    [switch]$SkipTemplates,
    [switch]$SkipDb,
    [switch]$Upload
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$Root = Split-Path -Parent $PSScriptRoot
if ($OutDir -eq "") { $OutDir = Join-Path $Root "release-assets" }
$Storage = Join-Path $Root "backend\app\storage"
$Media   = Join-Path $Storage "media"
$Templates = Join-Path $Root "videotemplate"
$Db      = Join-Path $Storage "kokoro.db"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$MaxBytes = [int64]$MaxPartMB * 1MB

function New-PartZip {
    param([string]$SourceDir, [string[]]$Files, [string]$ZipPath, [string]$RootDir)

    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    $zip = [System.IO.Compression.ZipFile]::Open($ZipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        # entries are stored relative to the repo root, so extracting a zip at the
        # repo root recreates the original folder layout
        $base = $RootDir.TrimEnd('\', '/')
        foreach ($f in $Files) {
            $rel = if ($f.Length -gt $base.Length) { $f.Substring($base.Length) } else { $f }
            $rel = $rel.TrimStart('\', '/').Replace('\', '/')
            if ([string]::IsNullOrWhiteSpace($rel)) { $rel = [System.IO.Path]::GetFileName($f) }
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f, $rel) | Out-Null
        }
    }
    finally {
        $zip.Dispose()
    }
    $size = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
    Write-Host ("  -> {0}  ({1} MB, {2} files)" -f (Split-Path $ZipPath -Leaf), $size, $Files.Count)
}

function New-ChunkedZips {
    param([string]$SourceDir, [string]$Prefix)

    if (-not (Test-Path $SourceDir)) {
        Write-Warning "Skipping missing: $SourceDir"
        return
    }
    $files = Get-ChildItem $SourceDir -Recurse -File | Sort-Object FullName
    if ($files.Count -eq 0) { Write-Warning "No files in $SourceDir"; return }

    $part = 1
    $bucket = New-Object System.Collections.Generic.List[string]
    $bucketBytes = [int64]0

    foreach ($f in $files) {
        if (($bucketBytes + $f.Length) -gt $MaxBytes -and $bucket.Count -gt 0) {
            $zipPath = Join-Path $OutDir ("{0}-part{1:D2}.zip" -f $Prefix, $part)
            New-PartZip -SourceDir $SourceDir -Files $bucket.ToArray() -ZipPath $zipPath -RootDir $Root
            $part++
            $bucket.Clear()
            $bucketBytes = 0
        }
        $bucket.Add($f.FullName)
        $bucketBytes += $f.Length
    }
    if ($bucket.Count -gt 0) {
        $zipPath = Join-Path $OutDir ("{0}-part{1:D2}.zip" -f $Prefix, $part)
        New-PartZip -SourceDir $SourceDir -Files $bucket.ToArray() -ZipPath $zipPath -RootDir $Root
    }
}

Write-Host "=== Kokoro Studio data packer ==="
Write-Host "Output: $OutDir"
Write-Host "Max part: $MaxPartMB MB (GitHub limit is 2048 MB)`n"

if (-not $SkipMedia) {
    Write-Host "[1/3] Media library ($Media)"
    if (Test-Path $Media) {
        Get-ChildItem $Media -Directory | ForEach-Object {
            Write-Host " Folder: $($_.Name)"
            New-ChunkedZips -SourceDir $_.FullName -Prefix ("media-" + ($_.Name -replace '[^A-Za-z0-9_\-]', '_'))
        }
    } else { Write-Warning "Media library not found - skipped" }
}

if (-not $SkipTemplates) {
    Write-Host "`n[2/3] Video templates ($Templates)"
    New-ChunkedZips -SourceDir $Templates -Prefix "videotemplate"
}

if (-not $SkipDb) {
    Write-Host "`n[3/3] Database"
    if (Test-Path $Db) {
        $zipPath = Join-Path $OutDir "kokoro-db.zip"
        if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
        $zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $Db, "backend/app/storage/kokoro.db") | Out-Null
            foreach ($side in @("kokoro.db-wal", "kokoro.db-shm")) {
                $p = Join-Path $Storage $side
                if (Test-Path $p) {
                    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $p, "backend/app/storage/$side") | Out-Null
                }
            }
        } finally { $zip.Dispose() }
        Write-Host ("  -> kokoro-db.zip ({0} MB)" -f [math]::Round((Get-Item $zipPath).Length / 1MB, 1))
    } else { Write-Warning "No database at $Db - skipped" }
}

$assets = Get-ChildItem $OutDir -Filter *.zip
$total = [math]::Round(($assets | Measure-Object Length -Sum).Sum / 1GB, 2)
Write-Host ("`nDone: {0} asset(s), {1} GB in {2}" -f $assets.Count, $total, $OutDir)

$tooBig = $assets | Where-Object { $_.Length -ge 2GB }
if ($tooBig) {
    Write-Error ("These exceed GitHub's 2 GiB per-file limit: " + (($tooBig | ForEach-Object Name) -join ", "))
}

if ($Upload) {
    Write-Host "`nPublishing release '$Tag'..."
    $env:GH_PROMPT_DISABLED = 1
    $notes = "Large local data for Kokoro Studio (media library, template clips, database). Download and extract to the repo root - see docs/GITHUB_SETUP.md."
    gh release view $Tag --repo heywinterbell/kokoro-studio > $null 2>&1
    if ($LASTEXITCODE -eq 0) {
        gh release upload $Tag $assets.FullName --repo heywinterbell/kokoro-studio --clobber
    } else {
        gh release create $Tag $assets.FullName --repo heywinterbell/kokoro-studio --title $ReleaseName --notes $notes
    }
    if ($LASTEXITCODE -ne 0) { throw "Publishing to GitHub failed" }
    Write-Host "Published: https://github.com/heywinterbell/kokoro-studio/releases/tag/$Tag"
} else {
    Write-Host "`nNext steps:"
    Write-Host "  gh release create $Tag " + (($assets | ForEach-Object FullName) -join ' ')
    Write-Host "  (or re-run with -Upload to do it automatically)"
}
