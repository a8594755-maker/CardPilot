#!/usr/bin/env node
// Import and convert solver data to CardPilot format
// Supports: PioSolver CSV, GTO+ JSON, SimplePostflop exports

import { readFileSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Parse PioSolver CSV export format
 * Expected format: Hand,Raise,Call,Fold
 */
function parsePioSolverCSV(csvContent, spot, sizing = "open2.5x") {
  const lines = csvContent.trim().split("\n");
  const headers = lines[0].toLowerCase().split(",");
  
  const hands = [];
  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(",");
    if (values.length < 4) continue;
    
    const hand = values[0].trim();
    const raise = parseFloat(values[1]) || 0;
    const call = parseFloat(values[2]) || 0;
    const fold = parseFloat(values[3]) || 0;
    
    // Normalize to sum to 1
    const sum = raise + call + fold;
    if (sum < 0.01) continue;
    
    hands.push({
      hand,
      strategy: {
        raise: round4(raise / sum),
        call: round4(call / sum),
        fold: round4(fold / sum)
      }
    });
  }
  
  return {
    spot,
    sizing,
    hands
  };
}

/**
 * Parse GTO+ JSON export format
 */
function parseGTOPlusJSON(jsonContent) {
  const data = JSON.parse(jsonContent);
  
  const spots = [];
  for (const spot of data.spots || []) {
    const hands = [];
    
    for (const [hand, strategy] of Object.entries(spot.ranges || {})) {
      const raise = strategy.raise || strategy.bet || 0;
      const call = strategy.call || strategy.check || 0;
      const fold = strategy.fold || 0;
      
      const sum = raise + call + fold;
      if (sum < 0.01) continue;
      
      hands.push({
        hand,
        strategy: {
          raise: round4(raise / sum),
          call: round4(call / sum),
          fold: round4(fold / sum)
        },
        ev: strategy.ev,
        equity: strategy.equity
      });
    }
    
    spots.push({
      spot: spot.name,
      sizing: spot.sizing || "open2.5x",
      description: spot.description,
      hands
    });
  }
  
  return spots;
}

/**
 * Convert to CardPilot chart format
 */
function convertToChartFormat(solverData, format = "cash_6max_100bb") {
  const chartRows = [];
  
  for (const spot of solverData.spots || []) {
    for (const handData of spot.hands) {
      chartRows.push({
        format,
        spot: spot.spot,
        hand: handData.hand,
        mix: {
          raise: handData.strategy.raise,
          call: handData.strategy.call,
          fold: handData.strategy.fold
        },
        notes: handData.tags || inferTags(handData)
      });
    }
  }
  
  return chartRows;
}

/**
 * Infer strategic tags from hand and strategy
 */
function inferTags(handData) {
  const tags = [];
  const { hand, strategy, equity } = handData;
  
  // Hand type tags
  if (hand[0] === "A") tags.push("A_BLOCKER");
  if (hand[0] === "K") tags.push("K_BLOCKER");
  if (hand.endsWith("s")) tags.push("SUITED_PLAYABILITY");
  if (hand[0] === hand[1]) tags.push("PAIR_VALUE");
  
  // Strategy tags
  if (strategy.raise > 0.7) {
    tags.push(equity > 0.6 ? "VALUE_BET" : "POLARIZED");
  } else if (strategy.raise > 0.3 && strategy.raise < 0.7) {
    tags.push("MIXED_STRATEGY");
  }
  
  if (strategy.call > 0.5) tags.push("DEFEND_RANGE");
  if (strategy.fold > 0.8) tags.push("LOW_PLAYABILITY");
  
  return tags.length > 0 ? tags : ["STANDARD_PLAY"];
}

/**
 * Main import function
 */
function importSolverData(inputPath, outputPath, options = {}) {
  const {
    solver = "auto",
    format = "cash_6max_100bb",
    merge = false
  } = options;
  
  console.log(`[import] Reading from: ${inputPath}`);
  const content = readFileSync(inputPath, "utf-8");
  
  let solverData = {
    version: "1.0",
    solver: solver === "auto" ? detectSolverType(content, inputPath) : solver,
    format,
    spots: []
  };
  
  // Parse based on detected format
  if (solverData.solver === "piosolver" || inputPath.endsWith(".csv")) {
    const spot = options.spot || "BTN_unopened_open2.5x";
    const sizing = options.sizing || "open2.5x";
    const parsed = parsePioSolverCSV(content, spot, sizing);
    solverData.spots = [parsed];
  } else if (solverData.solver === "gto+" || inputPath.endsWith(".json")) {
    solverData.spots = parseGTOPlusJSON(content);
  } else {
    throw new Error(`Unsupported solver format: ${solverData.solver}`);
  }
  
  // Convert to chart format
  const chartRows = convertToChartFormat(solverData, format);
  
  // Merge with existing data if requested
  if (merge && outputPath) {
    try {
      const existing = JSON.parse(readFileSync(outputPath, "utf-8"));
      const merged = mergeCharts(existing, chartRows);
      writeFileSync(outputPath, JSON.stringify(merged, null, 2), "utf-8");
      console.log(`[import] Merged ${chartRows.length} hands into ${outputPath}`);
    } catch (err) {
      console.warn(`[import] Could not merge, writing new file:`, err.message);
      writeFileSync(outputPath, JSON.stringify(chartRows, null, 2), "utf-8");
    }
  } else if (outputPath) {
    writeFileSync(outputPath, JSON.stringify(chartRows, null, 2), "utf-8");
    console.log(`[import] Wrote ${chartRows.length} chart entries to ${outputPath}`);
  }
  
  return chartRows;
}

function detectSolverType(content, filename) {
  if (filename.endsWith(".csv")) return "piosolver";
  if (filename.endsWith(".json")) {
    try {
      const json = JSON.parse(content);
      if (json.solver) return json.solver;
      if (json.spots) return "gto+";
    } catch {}
  }
  return "custom";
}

function mergeCharts(existing, newRows) {
  const map = new Map();
  
  // Add existing
  for (const row of existing) {
    const key = `${row.format}|${row.spot}|${row.hand}`;
    map.set(key, row);
  }
  
  // Overwrite with new data
  for (const row of newRows) {
    const key = `${row.format}|${row.spot}|${row.hand}`;
    map.set(key, row);
  }
  
  return Array.from(map.values());
}

function round4(n) {
  return Math.round(n * 10000) / 10000;
}

// CLI usage
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  
  if (args.length < 1) {
    console.log(`
Usage: node import-solver-data.mjs <input> [options]

Options:
  --output, -o      Output file path (default: preflop_charts_solver.json)
  --solver, -s      Solver type: piosolver|gto+|auto (default: auto)
  --format, -f      Game format (default: cash_6max_100bb)
  --spot            Spot identifier for CSV import (e.g., BTN_unopened_open2.5x)
  --sizing          Sizing for CSV import (default: open2.5x)
  --merge, -m       Merge with existing chart data

Examples:
  # Import PioSolver CSV for BTN open
  node import-solver-data.mjs btn_open.csv --spot BTN_unopened_open2.5x
  
  # Import GTO+ JSON with merge
  node import-solver-data.mjs gtoplus_export.json --merge -o preflop_charts.json
    `);
    process.exit(0);
  }
  
  const inputPath = args[0];
  const options = {
    outputPath: join(__dirname, "preflop_charts_solver.json"),
    solver: "auto",
    format: "cash_6max_100bb",
    merge: false
  };
  
  for (let i = 1; i < args.length; i++) {
    if (args[i] === "--output" || args[i] === "-o") {
      options.outputPath = args[++i];
    } else if (args[i] === "--solver" || args[i] === "-s") {
      options.solver = args[++i];
    } else if (args[i] === "--format" || args[i] === "-f") {
      options.format = args[++i];
    } else if (args[i] === "--spot") {
      options.spot = args[++i];
    } else if (args[i] === "--sizing") {
      options.sizing = args[++i];
    } else if (args[i] === "--merge" || args[i] === "-m") {
      options.merge = true;
    }
  }
  
  try {
    importSolverData(inputPath, options.outputPath, options);
  } catch (err) {
    console.error("[import] Error:", err.message);
    process.exit(1);
  }
}

export { importSolverData, parsePioSolverCSV, parseGTOPlusJSON, convertToChartFormat };
