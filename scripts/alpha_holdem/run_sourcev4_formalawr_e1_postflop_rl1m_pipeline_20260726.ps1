$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Let the conservative-2M optimizer finish. Its read-only CUDA proxy probe may
# overlap this run because measured combined memory use remains well below the
# local 12 GiB limit.
$deadline = (Get-Date).AddHours(8)
while ((Get-Date) -lt $deadline) {
    $prior = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.Name -eq 'python.exe' -and
                $_.CommandLine -match 'train_v5.py' -and
                $_.CommandLine -match 'sourcev4_postflop_adapter128_rl_conservative2m_20260726'
            }
    )
    if ($prior.Count -eq 0) {
        break
    }
    Start-Sleep -Seconds 20
}
if ((Get-Date) -ge $deadline) {
    throw 'Timed out waiting for conservative-2M optimizer'
}

$runDir = 'models\sourcev4_formal100k_postflop_awr_e1_rl1m_20260726'
if (Test-Path -LiteralPath $runDir) {
    throw "Training output already exists: $runDir"
}

$source = 'models\sourcev4_slumbot_formal100k_postflop_awr_adapter256_mappingfix_20260726\epoch_1.pt'
& python -X utf8 -u scripts/alpha_holdem/train_v5.py `
    --device cuda `
    --workers 20 `
    --hands-per-iter 16384 `
    --total-hands 1262472 `
    --starting-stack 200 `
    --env-version v55preflopv2v4obs `
    --norm-layer gn `
    --lr 0.00001 `
    --ppo-epochs 2 `
    --ppo-target-kl 0.01 `
    --source-policy-kl-coef 1.0 `
    --policy-postflop-only `
    --separate-preflop-head `
    --postflop-adapter-hidden 256 `
    --adapter-only-training `
    --mini-batch-size 2048 `
    --epsilon 0 `
    --gamma 0.999 `
    --gae-lambda 1.0 `
    --delta1 3 `
    --entropy-coef 0.001 `
    --entropy-floor 0 `
    --k-best 5 `
    --pool-strategy loss-kbest `
    --self-play-fraction 0.25 `
    --opponent-assignment per-iteration `
    --rollout-mode multi `
    --rollout-envs-per-worker 16 `
    --inference-min-batch-slots 128 `
    --inference-batch-deadline-us 1000 `
    --snapshot-every 10 `
    --save-interval 1 `
    --archive-checkpoint-every 10 `
    --run-id sourcev4_formal100k_postflop_awr_e1_rl1m_20260726 `
    --run-dir $runDir `
    --out (Join-Path $runDir 'latest.pt') `
    --seed 20260757 `
    --max-runtime-seconds 21600 `
    --resume $source `
    --allow-resume `
    --reset-optimizer
if ($LASTEXITCODE -ne 0) {
    throw 'Formal100k AWR e1 postflop RL training failed'
}

$candidate = Join-Path $runDir 'latest.pt'
$proxy = 'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt'
$proxyResult = Join-Path $runDir 'proxy5000.json'
& python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $candidate `
    --hands 5000 `
    --opponents aggressive `
    --checkpoint-opponent $proxy `
    --checkpoint-opponent-only `
    --checkpoint-opponent-policy-mode greedy `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260749 `
    --policy-mode greedy `
    --out-json $proxyResult `
    --out-md (Join-Path $runDir 'proxy5000.md')
if ($LASTEXITCODE -ne 0) {
    throw 'Formal100k AWR e1 postflop RL proxy evaluation failed'
}

$result = Get-Content -LiteralPath $proxyResult -Raw | ConvertFrom-Json
$bb100 = [double]$result.results[0].bb100
$decision = [PSCustomObject]@{
    hypothesis = 'Conservative self-play can retain the formal100k Slumbot AWR teacher while improving off-teacher robustness.'
    source_checkpoint = (Resolve-Path -LiteralPath $source).Path
    new_training_hands_target = 1000000
    offline_teacher_decision_samples = 71895
    baseline_proxy_bb100 = 31.4362
    candidate_proxy_bb100 = $bb100
    candidate_proxy_ci95 = [double]$result.results[0].ci95_bb100
    launch_external = $bb100 -gt 31.4362
}
$decision |
    ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $runDir 'external_decision.json') -Encoding UTF8
if (-not $decision.launch_external) {
    exit 0
}

$externalDir = 'models\bench_sourcev4_formal100k_postflop_awr_e1_rl1m_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $candidate).Path `
    -Tag 'sourcev4_formal100k_postflop_awr_e1_rl1m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
