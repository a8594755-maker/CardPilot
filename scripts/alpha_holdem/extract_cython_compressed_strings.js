#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

if (process.argv.length !== 4) {
  throw new Error(
    "usage: node extract_cython_compressed_strings.js INPUT_DIR OUTPUT_DIR",
  );
}

const inputDir = path.resolve(process.argv[2]);
const outputDir = path.resolve(process.argv[3]);
fs.mkdirSync(outputDir, { recursive: true });

function visit(directory) {
  const result = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      result.push(...visit(fullPath));
    } else if (entry.isFile() && entry.name.endsWith(".so")) {
      result.push(fullPath);
    }
  }
  return result;
}

const reports = [];
for (const source of visit(inputDir).sort()) {
  const data = fs.readFileSync(source);
  const streams = [];
  for (let offset = 0; offset + 2 < data.length; offset += 1) {
    if (
      data[offset] !== 0x78 ||
      ![0x01, 0x5e, 0x9c, 0xda].includes(data[offset + 1])
    ) {
      continue;
    }
    try {
      const inflated = zlib.inflateSync(data.subarray(offset));
      if (inflated.length >= 100) {
        streams.push({ offset, inflated });
      }
    } catch {
      // Most 0x78 byte pairs are not zlib stream starts.
    }
  }
  if (streams.length === 0) {
    continue;
  }
  const relative = path.relative(inputDir, source).replace(/[\\/]/g, "__");
  const destination = path.join(outputDir, `${relative}.strings.txt`);
  const body = streams
    .map(
      ({ offset, inflated }, index) =>
        `===== stream ${index + 1} offset ${offset} bytes ${inflated.length} =====\n` +
        inflated.toString("utf8").replace(/\0+/g, "\n"),
    )
    .join("\n\n");
  fs.writeFileSync(destination, body, "utf8");
  reports.push({
    source,
    destination,
    streams: streams.length,
    inflatedBytes: streams.reduce(
      (total, stream) => total + stream.inflated.length,
      0,
    ),
  });
}

process.stdout.write(`${JSON.stringify(reports, null, 2)}\n`);
