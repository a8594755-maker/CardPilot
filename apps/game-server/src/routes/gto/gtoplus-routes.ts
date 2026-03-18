import { Router, type Request, type Response } from 'express';
import { existsSync } from 'fs';
import { join, resolve, basename } from 'path';
import {
  parseGtoPlusFile,
  scanGtoPlusDirectory,
  compareStrategies,
  type GtoPlusNodeStrategy,
} from '../../services/gto/gtoplus-parser.js';

// Cache parsed GTO+ data in memory
const cache = new Map<string, GtoPlusNodeStrategy>();

// Default sample directory — relative to project root
const DEFAULT_SAMPLE_DIR = resolve(process.cwd(), 'data/compare_gtoplus');

export function createGtoPlusRouter(): Router {
  const router = Router();

  /**
   * GET /gtoplus/samples — List available GTO+ sample files
   */
  router.get('/gtoplus/samples', async (req: Request, res: Response) => {
    try {
      const dir = (req.query.dir as string) || DEFAULT_SAMPLE_DIR;
      const files = scanGtoPlusDirectory(dir);
      res.json({
        directory: dir,
        files: files.map((f) => ({
          path: f,
          name: f.replace(/\\/g, '/').split('/').pop(),
        })),
      });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  /**
   * GET /gtoplus/parse — Parse a specific GTO+ file and return structured data
   */
  router.get('/gtoplus/parse', async (req: Request, res: Response) => {
    try {
      const file = req.query.file as string;
      if (!file) return res.status(400).json({ error: 'Missing file parameter' });

      // Try the exact path, or look inside the default sample dir
      let filePath = file;
      if (!existsSync(filePath)) {
        filePath = join(DEFAULT_SAMPLE_DIR, file);
      }
      if (!existsSync(filePath)) {
        return res.status(404).json({ error: 'File not found', path: filePath });
      }

      // Check cache
      if (cache.has(filePath)) {
        return res.json(cache.get(filePath)!);
      }

      const strategy = parseGtoPlusFile(filePath);
      cache.set(filePath, strategy);
      res.json(strategy);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  /**
   * GET /gtoplus/grid — Get the 13x13 hand class grid from a GTO+ file
   */
  router.get('/gtoplus/grid', async (req: Request, res: Response) => {
    try {
      const file = req.query.file as string;
      if (!file) return res.status(400).json({ error: 'Missing file parameter' });

      let filePath = file;
      if (!existsSync(filePath)) {
        filePath = join(DEFAULT_SAMPLE_DIR, file);
      }
      if (!existsSync(filePath)) {
        return res.status(404).json({ error: 'File not found' });
      }

      if (!cache.has(filePath)) {
        cache.set(filePath, parseGtoPlusFile(filePath));
      }
      const data = cache.get(filePath)!;

      res.json({
        fileName: data.fileName,
        actions: data.actions,
        grid: data.grid,
        context: data.context,
        summary: data.summary,
      });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  /**
   * GET /gtoplus/combos — Get all combo-level data from a GTO+ file
   */
  router.get('/gtoplus/combos', async (req: Request, res: Response) => {
    try {
      const file = req.query.file as string;
      const hand = req.query.hand as string | undefined;
      if (!file) return res.status(400).json({ error: 'Missing file parameter' });

      let filePath = file;
      if (!existsSync(filePath)) {
        filePath = join(DEFAULT_SAMPLE_DIR, file);
      }
      if (!existsSync(filePath)) {
        return res.status(404).json({ error: 'File not found' });
      }

      if (!cache.has(filePath)) {
        cache.set(filePath, parseGtoPlusFile(filePath));
      }
      const data = cache.get(filePath)!;

      // Optionally filter by hand class
      let combos = data.combos;
      if (hand) {
        combos = combos.filter((c) => {
          // Match by exact combo or by hand class
          return c.hand === hand || comboToClass(c.hand) === hand;
        });
      }

      res.json({
        fileName: data.fileName,
        actions: data.actions,
        totalCombos: combos.length,
        combos,
      });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  /**
   * POST /gtoplus/compare — Compare GTO+ grid against an EZ-GTO grid
   */
  router.post('/gtoplus/compare', async (req: Request, res: Response) => {
    try {
      const { gtoPlusFile, ezGtoGrid, actions } = req.body;

      let filePath = gtoPlusFile;
      if (!existsSync(filePath)) {
        filePath = join(DEFAULT_SAMPLE_DIR, gtoPlusFile);
      }
      if (!existsSync(filePath)) {
        return res.status(404).json({ error: 'GTO+ file not found' });
      }

      if (!cache.has(filePath)) {
        cache.set(filePath, parseGtoPlusFile(filePath));
      }
      const gtoPlusData = cache.get(filePath)!;

      const comparison = compareStrategies(
        gtoPlusData.grid,
        ezGtoGrid,
        actions || gtoPlusData.actions,
      );

      res.json({
        fileName: gtoPlusData.fileName,
        context: gtoPlusData.context,
        comparison,
      });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  /**
   * GET /gtoplus/paired — Find auto-paired OOP/IP files
   * Detects pairs by naming convention:
   *   <name>_OOP.txt / <name>_IP.txt
   *   <name>_1.txt / <name>_2.txt
   *   <name>.txt / <name>(2).txt
   */
  router.get('/gtoplus/paired', async (req: Request, res: Response) => {
    try {
      const dir = (req.query.dir as string) || DEFAULT_SAMPLE_DIR;
      const filePaths = scanGtoPlusDirectory(dir);
      const fileNames = filePaths.map((f) => basename(f));

      interface FilePair {
        name: string;
        oopFile: string;
        ipFile: string;
      }

      const pairs: FilePair[] = [];
      const paired = new Set<string>();

      for (const fPath of filePaths) {
        const fName = basename(fPath);
        if (paired.has(fName)) continue;

        const base = fName.replace(/\.txt$/i, '');

        // Pattern 1: <name>_OOP.txt / <name>_IP.txt
        if (base.endsWith('_OOP') || base.endsWith('_oop')) {
          const ipName = base.replace(/_[Oo][Oo][Pp]$/, '_IP.txt');
          const ipIdx = fileNames.indexOf(ipName);
          if (ipIdx === -1) {
            // Try lowercase
            const ipNameLower = base.replace(/_[Oo][Oo][Pp]$/, '_ip.txt');
            const ipIdxLower = fileNames.indexOf(ipNameLower);
            if (ipIdxLower !== -1) {
              pairs.push({
                name: base.replace(/_[Oo][Oo][Pp]$/, ''),
                oopFile: fName,
                ipFile: fileNames[ipIdxLower],
              });
              paired.add(fName);
              paired.add(fileNames[ipIdxLower]);
              continue;
            }
          } else {
            pairs.push({
              name: base.replace(/_[Oo][Oo][Pp]$/, ''),
              oopFile: fName,
              ipFile: fileNames[ipIdx],
            });
            paired.add(fName);
            paired.add(fileNames[ipIdx]);
            continue;
          }
        }

        // Pattern 2: <name>_1.txt / <name>_2.txt
        if (base.endsWith('_1')) {
          const pairName = base.replace(/_1$/, '_2') + '.txt';
          const pairIdx = fileNames.indexOf(pairName);
          if (pairIdx !== -1) {
            pairs.push({
              name: base.replace(/_1$/, ''),
              oopFile: fName,
              ipFile: fileNames[pairIdx],
            });
            paired.add(fName);
            paired.add(fileNames[pairIdx]);
            continue;
          }
        }

        // Pattern 3: <name>.txt / <name>(2).txt
        if (!base.includes('(')) {
          const pairName = base + '(2).txt';
          const pairIdx = fileNames.indexOf(pairName);
          if (pairIdx !== -1) {
            pairs.push({ name: base, oopFile: fName, ipFile: fileNames[pairIdx] });
            paired.add(fName);
            paired.add(fileNames[pairIdx]);
            continue;
          }
        }
      }

      const unpaired = fileNames.filter((f) => !paired.has(f));

      res.json({ pairs, unpaired });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  return router;
}

function comboToClass(hand: string): string {
  if (hand.length < 4) return hand;
  const RANK_ORDER = 'AKQJT98765432';
  const r1 = hand[0],
    s1 = hand[1],
    r2 = hand[2],
    s2 = hand[3];
  if (r1 === r2) return `${r1}${r2}`;
  const i1 = RANK_ORDER.indexOf(r1);
  const i2 = RANK_ORDER.indexOf(r2);
  const [hi, lo] = i1 < i2 ? [r1, r2] : [r2, r1];
  return `${hi}${lo}${s1 === s2 ? 's' : 'o'}`;
}
