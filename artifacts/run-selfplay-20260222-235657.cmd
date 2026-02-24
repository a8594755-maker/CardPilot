@echo off
set PREFLOP_KEEP_EVERY=1
set EV_TRAIN_MC_ITERS=10
set EV_TRAIN_MC_MS=1
npx tsx apps/bot-client/src/self-play.ts --mode train --version v2 --servers 4000,4001,4002,4003,4004,4005,4006,4007,4008,4009,4010,4011 --shards 12 --max-rooms-per-server 30 --min-rate 65000 --min-rate-grace-min 4 --recover-rooms 1 --recover-cooldown-min 5 --quality-cooldown-min 2 >> "C:\Users\a8594\CardPilot\artifacts\selfplay-70pct-final-20260222-235657.log" 2>&1
