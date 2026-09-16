param(
    [string]$Workspace = 'C:\Users\a8594\CardPilot',
    [string]$ArchiveRoot = 'C:\Users\a8594\CardPilot_legacy_20260829'
)

$ErrorActionPreference = 'Stop'

function Full([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
}

$Workspace = Full $Workspace
$ArchiveRoot = Full $ArchiveRoot
$workspacePrefix = $Workspace + '\'
$archivePrefix = $ArchiveRoot + '\'

if ($Workspace -ne 'C:\Users\a8594\CardPilot') {
    throw "Unexpected workspace: $Workspace"
}
if ($ArchiveRoot -eq $Workspace -or $ArchiveRoot.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Archive must be outside the workspace: $ArchiveRoot"
}
if ([System.IO.Path]::GetPathRoot($ArchiveRoot) -eq $ArchiveRoot) {
    throw "Archive cannot be a drive root: $ArchiveRoot"
}

function Assert-WorkspacePath([string]$Path) {
    $resolved = Full $Path
    if (-not $resolved.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside workspace: $resolved"
    }
    return $resolved
}

function Assert-ArchivePath([string]$Path) {
    $resolved = Full $Path
    if (-not $resolved.StartsWith($archivePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside archive: $resolved"
    }
    return $resolved
}

function Ensure-Parent([string]$Path) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
}

function Move-ToArchive([string]$Source, [string]$RelativeDestination) {
    $sourcePath = Assert-WorkspacePath $Source
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        return
    }
    $destination = Assert-ArchivePath (Join-Path $ArchiveRoot $RelativeDestination)
    if (Test-Path -LiteralPath $destination) {
        throw "Archive destination already exists: $destination"
    }
    Ensure-Parent $destination
    Move-Item -LiteralPath $sourcePath -Destination $destination
}

function Remove-WorkspacePath([string]$Path) {
    $resolved = Assert-WorkspacePath $Path
    if (Test-Path -LiteralPath $resolved) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

function Directory-Stats([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return @{ files = 0; bytes = 0 }
    }
    $files = Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue
    return @{
        files = $files.Count
        bytes = [long](($files | Measure-Object Length -Sum).Sum)
    }
}

Set-Location -LiteralPath $Workspace

$active = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match 'python|pwsh|powershell' -and
    $_.CommandLine -like "*$Workspace*" -and
    $_.CommandLine -match 'train_v5|counterfactual|play_slumbot|watch_|run_'
}
if ($active) {
    $ids = ($active | Select-Object -ExpandProperty ProcessId) -join ', '
    throw "Research processes are still active: $ids"
}

if (Test-Path -LiteralPath $ArchiveRoot) {
    if (Get-ChildItem -LiteralPath $ArchiveRoot -Force | Select-Object -First 1) {
        throw "Archive root already exists and is not empty: $ArchiveRoot"
    }
} else {
    New-Item -ItemType Directory -Path $ArchiveRoot -Force | Out-Null
}

$before = @{
    models = Directory-Stats (Join-Path $Workspace 'models')
    data = Directory-Stats (Join-Path $Workspace 'data')
    reports = Directory-Stats (Join-Path $Workspace 'reports')
    checkpoints = Directory-Stats (Join-Path $Workspace 'checkpoints')
    alpha_holdem = Directory-Stats (Join-Path $Workspace 'scripts\alpha_holdem')
    free_bytes = [long](Get-PSDrive -Name C).Free
}

$baselineSource = Join-Path $Workspace 'models\sourcev4_imitation_anchor_mixedselfplay10m_20260726'
$baselineFile = Join-Path $baselineSource 'latest.pt'
$baselineHash = (Get-FileHash -LiteralPath $baselineFile -Algorithm SHA256).Hash.ToLowerInvariant()
if ($baselineHash -ne '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428') {
    throw "Standard10 hash mismatch: $baselineHash"
}

$manifest = @{
    schema = 'cardpilot.cleanup.v1'
    started_at_utc = [DateTime]::UtcNow.ToString('o')
    workspace = $Workspace
    archive_root = $ArchiveRoot
    before = $before
    active_assets = @(
        'models/baseline/standard10',
        'data/teachers/cfr_v55_compact_v3_200bb_flops096_balanced_20260726',
        'scripts/alpha_holdem core files',
        'scripts/deep_cfr',
        'research'
    )
    cold_assets = @(
        '200bb raw CFR data',
        'full compact 200bb CFR teacher',
        'legacy reports',
        'legacy AlphaHoldem scripts',
        'legacy Deep-CFR checkpoints',
        'selected research parent/opponent checkpoints',
        'model experiment records and manifests'
    )
    baseline_sha256 = $baselineHash
}
[System.IO.File]::WriteAllText(
    (Join-Path $Workspace 'research\cleanup_20260829_pre.json'),
    ($manifest | ConvertTo-Json -Depth 8),
    [System.Text.UTF8Encoding]::new($false)
)

# Preserve selected model assets and compact metadata before removing model bulk.
$selectedRoot = Assert-ArchivePath (Join-Path $ArchiveRoot 'selected_assets')
New-Item -ItemType Directory -Path $selectedRoot -Force | Out-Null
$standardArchive = Join-Path $selectedRoot 'standard10'
New-Item -ItemType Directory -Path $standardArchive -Force | Out-Null
foreach ($name in @('latest.pt', 'experiment_record.json', 'run_manifest.json', 'h1_training_metrics.jsonl')) {
    $source = Join-Path $baselineSource $name
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $standardArchive $name)
    }
}

$cfParentArchive = Join-Path $selectedRoot 'cf160_parent'
New-Item -ItemType Directory -Path $cfParentArchive -Force | Out-Null
$cfRoot = Join-Path $Workspace 'models\sourcev4_standard10_bootstrap_cf160replay10m_20260826'
$cfCheckpoint = Join-Path $cfRoot 'checkpoints\checkpoint_iter000460_hands000015112468.pt'
if (Test-Path -LiteralPath $cfCheckpoint) {
    Copy-Item -LiteralPath $cfCheckpoint -Destination (Join-Path $cfParentArchive 'checkpoint_iter000460_hands000015112468.pt')
}
if (Test-Path -LiteralPath (Join-Path $cfRoot 'experiment_record.json')) {
    Copy-Item -LiteralPath (Join-Path $cfRoot 'experiment_record.json') -Destination $cfParentArchive
}

$opponentArchive = Join-Path $selectedRoot 'opponents'
New-Item -ItemType Directory -Path $opponentArchive -Force | Out-Null
foreach ($asset in @(
    @{ source = 'models\slumbot_free_anchor_position10m_20260727\latest.pt'; name = 'slumbot_free_anchor_position10m.pt' },
    @{ source = 'models\sourcev4_corrected_cfr96_anchor10_20260726\selected.pt'; name = 'corrected_cfr96_anchor10.pt' }
)) {
    $source = Join-Path $Workspace $asset.source
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $opponentArchive $asset.name)
    }
}

$modelRoot = Join-Path $Workspace 'models'
$modelRecordRoot = Assert-ArchivePath (Join-Path $ArchiveRoot 'model_records')
New-Item -ItemType Directory -Path $modelRecordRoot -Force | Out-Null
$metadataFiles = Get-ChildItem -LiteralPath $modelRoot -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -eq 'experiment_record.json' -or
    $_.Name -eq 'run_manifest.json' -or
    $_.Name -like 'manifest*.json'
}
foreach ($file in $metadataFiles) {
    $relative = [System.IO.Path]::GetRelativePath($modelRoot, $file.FullName)
    $destination = Assert-ArchivePath (Join-Path $modelRecordRoot $relative)
    Ensure-Parent $destination
    Copy-Item -LiteralPath $file.FullName -Destination $destination
}

# Cold storage: expensive or evidentiary assets, removed from the active workspace.
Move-ToArchive (Join-Path $Workspace 'data\cfr\pipeline_v3_hu_srp_200bb_legalallin_v2') 'data\cfr\pipeline_v3_hu_srp_200bb_legalallin_v2'
Move-ToArchive (Join-Path $Workspace 'data\cfr\pipeline_v3_hu_srp_200bb') 'data\cfr\pipeline_v3_hu_srp_200bb'
Move-ToArchive (Join-Path $Workspace 'data\training\cfr_v55_compact_200bb_flops32_sample05_20260726') 'data\training\cfr_v55_compact_200bb_flops32_sample05_20260726'
Move-ToArchive (Join-Path $Workspace 'checkpoints') 'checkpoints'
Move-ToArchive (Join-Path $Workspace 'reports') 'reports'
Move-ToArchive (Join-Path $Workspace 'scripts\alpha_holdem') 'scripts\alpha_holdem'

# Restore the deliberately small active AlphaHoldem code surface.
$coreFiles = @(
    '__init__.py',
    'environment.py',
    'environment_v55.py',
    'network.py',
    'network_hybrid_h1.py',
    'train_v5.py',
    'train_mp3_hybrid_h1.py',
    'v5_hybrid_h1_critic.py',
    'v5_hybrid_h2_targets.py',
    'v5_exp_w1_value_warmup.py',
    'play_slumbot.py',
    'bench_v55_slumbot.ps1',
    'combine_slumbot_logs.py',
    'slumbot_ci_from_hands.py',
    'v5_slumbot_promotion_gate.py',
    'audit_slumbot_session_independence.py',
    'analyze_dump.py',
    'v5_slumbot_loss_report.py',
    'v5_mirror_eval.py',
    'v5_training_curve_eval.py',
    'evaluate.py'
)
$activeAlpha = Join-Path $Workspace 'scripts\alpha_holdem'
New-Item -ItemType Directory -Path $activeAlpha -Force | Out-Null
$archivedAlpha = Join-Path $ArchiveRoot 'scripts\alpha_holdem'
foreach ($name in $coreFiles) {
    $source = Join-Path $archivedAlpha $name
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required AlphaHoldem core file missing: $source"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $activeAlpha $name)
}

# Keep one compact, current 200bb teacher active.
$teacherRoot = Join-Path $Workspace 'data\teachers'
New-Item -ItemType Directory -Path $teacherRoot -Force | Out-Null
$teacherSource = Join-Path $Workspace 'data\training\cfr_v55_compact_v3_200bb_flops096_balanced_20260726'
$teacherDestination = Join-Path $teacherRoot 'cfr_v55_compact_v3_200bb_flops096_balanced_20260726'
if (Test-Path -LiteralPath $teacherSource) {
    if (Test-Path -LiteralPath $teacherDestination) {
        throw "Active teacher destination already exists: $teacherDestination"
    }
    Move-Item -LiteralPath (Assert-WorkspacePath $teacherSource) -Destination (Assert-WorkspacePath $teacherDestination)
}

# Permanently remove rejected/redundant model weights and regenerable old data.
Remove-WorkspacePath $modelRoot
New-Item -ItemType Directory -Path (Join-Path $Workspace 'models\baseline\standard10') -Force | Out-Null
foreach ($file in Get-ChildItem -LiteralPath $standardArchive -File) {
    Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $Workspace 'models\baseline\standard10')
}
$baselineManifest = @{
    schema = 'cardpilot.baseline.v1'
    name = 'Standard10'
    policy = 'models/baseline/standard10/latest.pt'
    sha256 = $baselineHash
    lineage_training_hands = 10283876
    external = @{ hands = 20000; bb_per_100 = -11.4275; ci95 = @(-28.7124, 5.8574) }
}
[System.IO.File]::WriteAllText(
    (Join-Path $Workspace 'models\baseline\standard10\baseline.json'),
    ($baselineManifest | ConvertTo-Json -Depth 6),
    [System.Text.UTF8Encoding]::new($false)
)

foreach ($relative in @(
    'data\cfr',
    'data\training',
    'data\phase2',
    'data\nn-training',
    'data\v2',
    'data\preflop',
    'data\archive',
    'data\compare_gtoplus',
    'data\databases',
    'data\gto-comparison',
    'data\metadata'
)) {
    Remove-WorkspacePath (Join-Path $Workspace $relative)
}

foreach ($relative in @('logs', 'eval_logs', 'tmp', '.test_tmp', '.pytest_cache')) {
    Remove-WorkspacePath (Join-Path $Workspace $relative)
}

$rootLogs = Get-ChildItem -LiteralPath $Workspace -File | Where-Object { $_.Extension -eq '.log' }
foreach ($file in $rootLogs) {
    $verified = Assert-WorkspacePath $file.FullName
    Remove-Item -LiteralPath $verified -Force
}

$legacyDocsRoot = Assert-ArchivePath (Join-Path $ArchiveRoot 'legacy_docs')
New-Item -ItemType Directory -Path $legacyDocsRoot -Force | Out-Null
$legacyDocs = Get-ChildItem -LiteralPath (Join-Path $Workspace 'docs') -File -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -like 'V5_CURRENT_GOAL*'
}
foreach ($file in $legacyDocs) {
    $verified = Assert-WorkspacePath $file.FullName
    Move-Item -LiteralPath $verified -Destination (Join-Path $legacyDocsRoot $file.Name)
}
if (Test-Path -LiteralPath (Join-Path $Workspace 'CLAUDE.md')) {
    Move-Item -LiteralPath (Assert-WorkspacePath (Join-Path $Workspace 'CLAUDE.md')) -Destination (Join-Path $legacyDocsRoot 'CLAUDE.md')
}

$after = @{
    models = Directory-Stats (Join-Path $Workspace 'models')
    data = Directory-Stats (Join-Path $Workspace 'data')
    research = Directory-Stats (Join-Path $Workspace 'research')
    alpha_holdem = Directory-Stats (Join-Path $Workspace 'scripts\alpha_holdem')
    archive = Directory-Stats $ArchiveRoot
    free_bytes = [long](Get-PSDrive -Name C).Free
}
$manifest.completed_at_utc = [DateTime]::UtcNow.ToString('o')
$manifest.after = $after
$manifest.permanently_deleted_estimated_bytes = [long](
    ($before.models.bytes + $before.data.bytes + $before.alpha_holdem.bytes) -
    ($after.models.bytes + $after.data.bytes + $after.alpha_holdem.bytes + $after.archive.bytes)
)
[System.IO.File]::WriteAllText(
    (Join-Path $Workspace 'research\cleanup_20260829.json'),
    ($manifest | ConvertTo-Json -Depth 8),
    [System.Text.UTF8Encoding]::new($false)
)

Write-Output ($manifest | ConvertTo-Json -Depth 8)
