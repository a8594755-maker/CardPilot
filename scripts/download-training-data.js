/**
 * Download training data from HTTP server.
 * Usage: node scripts/download-training-data.js [mount-name]
 * If mount-name is omitted, downloads all mounts.
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = process.env.TRAINING_SERVER_URL || 'http://192.168.50.77:8080';
const PROJECT = path.resolve(__dirname, '..');

const MOUNTS = {
  'nn-training-c': path.join(PROJECT, 'EZ-GTO/data/nn-training'),
  'nn-training-d': path.join(PROJECT, 'EZ-GTO-data/nn-training'),
  'coaching-v1': path.join(PROJECT, 'EZ-GTO-data/coaching/hu_srp_100bb'),
  'coaching-v2': path.join(PROJECT, 'EZ-GTO-data/coaching/hu_srp_100bb_v2'),
};

async function main() {
  const filterMount = process.argv[2];

  // Fetch file listing
  console.log('Fetching file listing...');
  const listingJson = execSync(`curl -s ${BASE}/`, { maxBuffer: 10 * 1024 * 1024 }).toString();
  const listing = JSON.parse(listingJson);

  const mountsToDownload = filterMount ? [filterMount] : Object.keys(MOUNTS);

  for (const mount of mountsToDownload) {
    const dest = MOUNTS[mount];
    if (!dest) {
      console.error(`Unknown mount: ${mount}`);
      continue;
    }

    const files = listing[mount];
    if (!files) {
      console.error(`Mount ${mount} not found on server`);
      continue;
    }

    fs.mkdirSync(dest, { recursive: true });

    const totalBytes = files.reduce((s, f) => s + f.size, 0);
    console.log(
      `\n=== ${mount} === ${files.length} files, ${(totalBytes / 1073741824).toFixed(2)} GB → ${dest}`,
    );

    let downloaded = 0;
    let skipped = 0;

    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      const localPath = path.join(dest, f.name);

      // Skip if already exists with correct size
      if (fs.existsSync(localPath)) {
        const stat = fs.statSync(localPath);
        if (stat.size === f.size) {
          skipped++;
          continue;
        }
      }

      const pct = (((i + 1) / files.length) * 100).toFixed(0);
      console.log(`  [${pct}%] ${f.name} (${(f.size / 1048576).toFixed(1)} MB)...`);

      try {
        execSync(`curl -s -o "${localPath}" "${BASE}/${mount}/${f.name}"`, {
          timeout: 600000, // 10 min per file
        });
        downloaded++;
      } catch (e) {
        console.error(`    FAILED: ${f.name} - ${e.message}`);
      }
    }

    console.log(`  Done: ${downloaded} downloaded, ${skipped} skipped (already exist)`);
  }

  console.log('\nAll downloads complete.');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
