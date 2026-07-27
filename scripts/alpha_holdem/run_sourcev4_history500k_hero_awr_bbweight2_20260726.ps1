$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$priorSelection = 'models\sourcev4_history500k_hero_bb_fullcorpus_awr_adapter256_20260726\short_common_seed_curve\selection.json'
$deadline = (Get-Date).AddHours(4)
while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $priorSelection) { break }
    $prior = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match
                    'run_sourcev4_history500k_hero_bb_fullcorpus_awr_20260726.ps1'
            }
    )
    if ($prior.Count -eq 0) {
        throw 'Full-corpus hero-BB pipeline exited before proxy selection'
    }
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $priorSelection)) {
    throw 'Timed out waiting for full-corpus hero-BB selection'
}

$outputDir = 'models\sourcev4_history500k_hero_awr_bbweight2_adapter256_20260726'
if (Test-Path -LiteralPath $outputDir) {
    throw "BB-weighted hero-AWR output already exists: $outputDir"
}
& python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
    --source-checkpoint 'models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt' `
    --out-dir $outputDir `
    --roots models `
    --exclude-substring '20260726' `
    --obs-version v4 `
    --raise-action-mapping auto `
    --actor hero `
    --street-min 0 `
    --street-max 3 `
    --max-rows 500000 `
    --min-rows 50000 `
    --seed 20260772 `
    --device cuda `
    --epochs 3 `
    --batch-size 2048 `
    --lr 0.0001 `
    --kl-coef 1.0 `
    --return-clip-bb 20 `
    --beta-bb 5 `
    --min-bucket-count 50 `
    --weight-min 0.05 `
    --weight-max 20 `
    --slice-balance-power 0.0 `
    --decision-risk-power 0.0 `
    --position-0-weight 2.0 `
    --val-fraction 0.05 `
    --postflop-adapter-hidden 256 `
    --policy-adapter-only
exit $LASTEXITCODE
