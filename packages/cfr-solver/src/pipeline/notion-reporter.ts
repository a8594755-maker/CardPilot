// Notion progress reporter — pushes pipeline status to a Notion database every N minutes.
//
// Requires:
//   NOTION_API_TOKEN  — Notion integration token
//   NOTION_DATABASE_ID — Target database ID
//
// Notion database schema (create manually):
//   Name     (Title)        — Run ID
//   Status   (Select)       — In Progress / Complete / Failed
//   Progress (Number)       — 0-100
//   Completed (Number)      — Job count
//   Total    (Number)       — Job count
//   Failed   (Number)       — Job count
//   Workers  (Number)       — Active worker count
//   ETA      (Rich text)    — Human-readable
//   Configs  (Multi-select) — Config names
//   Updated  (Date)         — Last report time

import { Client } from '@notionhq/client';

export interface PipelineSnapshot {
  pending: number;
  running: number;
  completed: number;
  failed: number;
  total: number;
  etaHuman: string;
  avgSolveMs: number;
  activeWorkers: number;
  configs?: Record<string, { pending: number; running: number; completed: number; failed: number }>;
  workers?: Record<string, { running: number; completed: number; totalMs: number }>;
}

interface NotionReporterConfig {
  apiToken: string;
  databaseId: string;
  intervalMs?: number; // default 30min
}

export class NotionReporter {
  private client: Client;
  private databaseId: string;
  private intervalMs: number;
  private pageId: string | null = null;
  private runId: string;
  private timer: ReturnType<typeof setInterval> | null = null;
  private getStatus: () => PipelineSnapshot;

  constructor(config: NotionReporterConfig, getStatus: () => PipelineSnapshot) {
    this.client = new Client({ auth: config.apiToken });
    this.databaseId = config.databaseId;
    this.intervalMs = config.intervalMs ?? 30 * 60 * 1000;
    this.runId = `run-${new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '')}`;
    this.getStatus = getStatus;
  }

  async start(): Promise<void> {
    try {
      await this.client.databases.retrieve({ database_id: this.databaseId });
      console.log(`[Notion] Connected to database`);
    } catch (err) {
      console.error(`[Notion] Failed to connect — reporting disabled. Check NOTION_API_TOKEN and NOTION_DATABASE_ID.`);
      return;
    }

    await this.report();

    this.timer = setInterval(() => {
      this.report().catch(err => {
        console.error(`[Notion] Report failed:`, err);
      });
    }, this.intervalMs);

    console.log(`[Notion] Reporting every ${this.intervalMs / 60000} minutes`);
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async report(): Promise<void> {
    const status = this.getStatus();
    const progressPct = status.total > 0
      ? Math.round(status.completed / status.total * 1000) / 10
      : 0;

    const statusLabel = this.getStatusLabel(status);
    const configNames = Object.keys(status.configs ?? {});
    const detailsText = this.buildDetailsText(status);

    try {
      if (this.pageId) {
        await this.updatePage(statusLabel, progressPct, status);
        await this.replaceBody(detailsText);
      } else {
        await this.createPage(statusLabel, progressPct, status, configNames);
        await this.appendBody(detailsText);
      }
      console.log(`[Notion] Report sent: ${progressPct}% (${status.completed}/${status.total})`);
    } catch (err) {
      console.error(`[Notion] Report failed:`, err);
    }
  }

  private getStatusLabel(status: PipelineSnapshot): string {
    if (status.pending === 0 && status.running === 0 && status.completed > 0) return 'Complete';
    if (status.failed > 0 && status.failed === status.total) return 'Failed';
    return 'In Progress';
  }

  private buildDetailsText(status: PipelineSnapshot): string {
    const configLines = Object.entries(status.configs ?? {}).map(([name, cs]) => {
      const t = cs.pending + cs.running + cs.completed + cs.failed;
      const pct = t > 0 ? Math.round(cs.completed / t * 100) : 0;
      return `${name}: ${cs.completed}/${t} (${pct}%)`;
    });

    const workerLines = Object.entries(status.workers ?? {}).map(([wid, ws]) => {
      const avgS = ws.completed > 0 ? (ws.totalMs / ws.completed / 1000).toFixed(1) : '-';
      return `${wid}: ${ws.completed} done, ${ws.running} running, avg ${avgS}s`;
    });

    return [
      `## Configs`,
      ...configLines.map(l => `- ${l}`),
      '',
      `## Workers`,
      ...workerLines.map(l => `- ${l}`),
      '',
      `ETA: ${status.etaHuman}`,
      `Avg solve: ${status.avgSolveMs > 0 ? (status.avgSolveMs / 1000).toFixed(1) + 's' : 'N/A'}`,
      `Active workers: ${status.activeWorkers}`,
    ].join('\n');
  }

  private async createPage(
    statusLabel: string, progressPct: number, status: PipelineSnapshot, configNames: string[],
  ): Promise<void> {
    const response = await this.client.pages.create({
      parent: { database_id: this.databaseId },
      properties: {
        'Name': { title: [{ text: { content: this.runId } }] },
        'Status': { select: { name: statusLabel } },
        'Progress': { number: progressPct },
        'Completed': { number: status.completed },
        'Total': { number: status.total },
        'Failed': { number: status.failed },
        'Workers': { number: status.activeWorkers },
        'ETA': { rich_text: [{ text: { content: status.etaHuman || 'N/A' } }] },
        'Configs': { multi_select: configNames.map(n => ({ name: n })) },
        'Updated': { date: { start: new Date().toISOString() } },
      },
    });
    this.pageId = response.id;
  }

  private async updatePage(
    statusLabel: string, progressPct: number, status: PipelineSnapshot,
  ): Promise<void> {
    if (!this.pageId) return;
    await this.client.pages.update({
      page_id: this.pageId,
      properties: {
        'Status': { select: { name: statusLabel } },
        'Progress': { number: progressPct },
        'Completed': { number: status.completed },
        'Total': { number: status.total },
        'Failed': { number: status.failed },
        'Workers': { number: status.activeWorkers },
        'ETA': { rich_text: [{ text: { content: status.etaHuman || 'N/A' } }] },
        'Updated': { date: { start: new Date().toISOString() } },
      },
    });
  }

  private async replaceBody(text: string): Promise<void> {
    if (!this.pageId) return;
    // Delete existing blocks
    try {
      const existing = await this.client.blocks.children.list({ block_id: this.pageId });
      for (const block of existing.results) {
        await this.client.blocks.delete({ block_id: (block as any).id });
      }
    } catch {
      // Ignore errors during block cleanup
    }
    await this.appendBody(text);
  }

  private async appendBody(text: string): Promise<void> {
    if (!this.pageId) return;
    const blocks = this.textToBlocks(text);
    if (blocks.length > 0) {
      await this.client.blocks.children.append({
        block_id: this.pageId,
        children: blocks,
      });
    }
  }

  private textToBlocks(text: string): any[] {
    const blocks: any[] = [];
    for (const line of text.split('\n')) {
      if (line.startsWith('## ')) {
        blocks.push({
          object: 'block', type: 'heading_2',
          heading_2: { rich_text: [{ text: { content: line.slice(3) } }] },
        });
      } else if (line.startsWith('- ')) {
        blocks.push({
          object: 'block', type: 'bulleted_list_item',
          bulleted_list_item: { rich_text: [{ text: { content: line.slice(2) } }] },
        });
      } else if (line.trim()) {
        blocks.push({
          object: 'block', type: 'paragraph',
          paragraph: { rich_text: [{ text: { content: line } }] },
        });
      }
    }
    return blocks;
  }
}

/**
 * Try to start Notion reporting if env vars are configured.
 * Returns the reporter instance (or null if not configured).
 */
export function tryStartNotionReporter(
  getStatus: () => PipelineSnapshot,
): NotionReporter | null {
  const apiToken = process.env.NOTION_API_TOKEN;
  const databaseId = process.env.NOTION_DATABASE_ID;

  if (!apiToken || !databaseId) {
    console.log(`[Notion] NOTION_API_TOKEN or NOTION_DATABASE_ID not set — reporting disabled.`);
    return null;
  }

  const reporter = new NotionReporter({ apiToken, databaseId }, getStatus);
  reporter.start().catch(err => {
    console.error(`[Notion] Failed to start reporter:`, err);
  });
  return reporter;
}
