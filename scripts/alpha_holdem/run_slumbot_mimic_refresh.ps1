$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$runs = @(
    @{
        Name = "slumbot_imitation_all413_plain_seed61_20260725"
        Source = "models/slumbot_imitation_recent15_seed46_300k_20260725/best.pt"
        Seed = "2026072561"
        RiskPower = "0"
    },
    @{
        Name = "slumbot_imitation_all413_risk05_seed62_20260725"
        Source = "models/slumbot_imitation_recent15_risk075_seed47_300k_20260725/best.pt"
        Seed = "2026072562"
        RiskPower = "0.5"
    }
)

foreach ($run in $runs) {
    Write-Output "START $($run.Name)"
    & python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
        --source-checkpoint $run.Source `
        --out-dir "models/$($run.Name)" `
        --roots models `
        --exclude-substring __no_such_token__ `
        --obs-version v4 `
        --actor opp `
        --street-min 0 `
        --street-max 3 `
        --max-rows 500000 `
        --seed $run.Seed `
        --device cuda `
        --epochs 8 `
        --batch-size 4096 `
        --lr 0.00002 `
        --weight-decay 0.00001 `
        --kl-coef 0.02 `
        --return-clip-bb 0 `
        --decision-risk-power $run.RiskPower `
        --decision-risk-cap 4 `
        --val-fraction 0.08
    if ($LASTEXITCODE -ne 0) {
        throw "$($run.Name) failed with exit code $LASTEXITCODE"
    }
    Write-Output "DONE $($run.Name)"
}
