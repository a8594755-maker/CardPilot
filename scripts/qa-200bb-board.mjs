#!/usr/bin/env node
// Streaming per-board CFR convergence QA; bounded memory even for multi-GB raw exports.
import { createGunzip } from 'node:zlib';
import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
const path=process.argv[2];if(!path){console.error('usage: node scripts/qa-200bb-board.mjs <flop_NNN.jsonl.gz>');process.exit(1)}
const input=createReadStream(path);const stream=path.endsWith('.gz')?input.pipe(createGunzip()):input;const rl=createInterface({input:stream,crlfDelay:Infinity});let cnt=0,decisive=0,pure=0,sumMax=0,illegalPostAllin=0;const byActions={};
try{for await(const line of rl){if(!line.trim())continue;let o;try{o=JSON.parse(line)}catch{continue}if(!o.probs)continue;cnt++;const mx=Math.max(...o.probs);sumMax+=mx;if(mx>=.6)decisive++;if(mx>=.95)pure++;byActions[o.probs.length]=(byActions[o.probs.length]||0)+1;const parts=typeof o.key==='string'?o.key.split('|'):[];const segment=parts.length===5?parts[3].split('/').at(-1):'';if(segment?.endsWith('A')&&o.probs.length>2)illegalPostAllin++}}catch(e){console.error(`QA stream error: ${e}`);process.exit(3)}
const mean=cnt?sumMax/cnt:0,pct=cnt?100*decisive/cnt:0,pass=mean>=.55&&pct>=35&&cnt>100000&&illegalPostAllin===0;console.log(`board: ${path}`);console.log(`infosets: ${cnt.toLocaleString()}`);console.log(`mean maxProb: ${mean.toFixed(3)}`);console.log(`decisive (>=0.6): ${pct.toFixed(1)}% near-pure: ${cnt?(100*pure/cnt).toFixed(1):'0.0'}%`);console.log(`by #actions: ${JSON.stringify(byActions)}`);console.log(`illegal post-all-in extra-action rows: ${illegalPostAllin}`);console.log(`QA: ${pass?'PASS (converged + legal post-all-in)':'FAIL (convergence or post-all-in legality -> re-solve this board)'}`);process.exit(pass?0:2);
