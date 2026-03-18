import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Worker } from 'node:worker_threads';
import { Router, type Request, type Response } from 'express';
import {
  createJob,
  getJob,
  getJobs,
  cancelJob,
  completeJob,
  failJob,
  createProgressCallback,
  updateJobProgress,
  type SolveJobConfig,
} from '../../services/gto/solve-manager.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Plain .mjs worker — uses compiled cfr-solver dist/, no tsx needed
const WORKER_PATH = resolve(__dirname, '../../workers/solver-worker.mjs');

export function createSolverRouter(): Router {
  const router = Router();

  router.post('/solve', async (req: Request, res: Response) => {
    try {
      const config = req.body as SolveJobConfig;

      // Validate required fields
      if (!config.board || config.board.length < 3) {
        return res.status(400).json({ error: 'board must have at least 3 cards' });
      }
      if (!config.oopRange || config.oopRange.length === 0) {
        return res.status(400).json({ error: 'oopRange must not be empty' });
      }
      if (!config.ipRange || config.ipRange.length === 0) {
        return res.status(400).json({ error: 'ipRange must not be empty' });
      }

      const job = createJob(config);

      // Start solver in a Worker thread — doesn't block the event loop
      runSolverWorker(job.id, config).catch((err) => {
        console.error(`Solver job failed: jobId=${job.id}`, err);
      });

      res.json({ jobId: job.id, status: job.status });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  router.get('/solve/:jobId', async (req: Request, res: Response) => {
    try {
      const job = getJob(req.params.jobId);
      if (!job) return res.status(404).json({ error: 'Job not found' });
      res.json(job);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  router.get('/solve', async (_req: Request, res: Response) => {
    try {
      res.json({ jobs: getJobs() });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  router.delete('/solve/:jobId', async (req: Request, res: Response) => {
    try {
      const success = cancelJob(req.params.jobId);
      if (!success) return res.status(404).json({ error: 'Job not found or already complete' });
      res.json({ cancelled: true });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  return router;
}

// ─── Worker-based solver ───

async function runSolverWorker(jobId: string, config: SolveJobConfig) {
  const job = getJob(jobId);
  if (!job) return;
  job.status = 'running';
  job.startedAt = new Date().toISOString();

  updateJobProgress(jobId, { totalIterations: config.iterations });

  const onProgress = createProgressCallback(jobId);

  return new Promise<void>((resolvePromise, rejectPromise) => {
    const worker = new Worker(WORKER_PATH, {
      workerData: {
        configName: config.configName,
        iterations: config.iterations,
        board: config.board,
        oopRange: config.oopRange,
        ipRange: config.ipRange,
        treeConfig: config.treeConfig,
        cwd: process.cwd(),
      },
    });

    worker.on('message', (msg: { type: string; [key: string]: unknown }) => {
      switch (msg.type) {
        case 'progress':
          onProgress(msg.iter as number, msg.elapsed as number);
          break;

        case 'complete':
          updateJobProgress(jobId, {
            elapsed: msg.elapsed as number,
            infoSets: msg.infoSets as number,
            exploitability: msg.exploitability as number,
          });
          completeJob(jobId);
          resolvePromise();
          break;

        case 'error':
          failJob(jobId, msg.message as string);
          rejectPromise(new Error(msg.message as string));
          break;
      }
    });

    worker.on('error', (err: Error) => {
      failJob(jobId, err.message);
      rejectPromise(err);
    });

    worker.on('exit', (code) => {
      if (code !== 0 && job.status === 'running') {
        failJob(jobId, `Worker exited with code ${code}`);
        rejectPromise(new Error(`Worker exited with code ${code}`));
      }
    });
  });
}
