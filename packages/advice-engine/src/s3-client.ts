/**
 * S3-compatible storage client for iDrive e2.
 * Used to download CFR binary strategies, JSONL files, and metadata.
 *
 * Environment variables:
 *   E2_ACCESS_KEY_ID     — S3 access key
 *   E2_SECRET_ACCESS_KEY — S3 secret key
 *   E2_ENDPOINT          — e.g. https://s3.us-east-1.idrivee2.com
 *   E2_BUCKET            — bucket name (default: cardpilot-cfr-data)
 *   E2_REGION            — region (default: us-east-1)
 */

import { S3Client, GetObjectCommand, ListObjectsV2Command } from "@aws-sdk/client-s3";

let _client: S3Client | null = null;

function getEnv(key: string, fallback?: string): string {
  return process.env[key] ?? fallback ?? "";
}

export function isS3Configured(): boolean {
  return !!(process.env.E2_ACCESS_KEY_ID && process.env.E2_SECRET_ACCESS_KEY);
}

export function getBucket(): string {
  return getEnv("E2_BUCKET", "cardpilot-cfr-data");
}

function getClient(): S3Client {
  if (_client) return _client;
  _client = new S3Client({
    region: getEnv("E2_REGION", "us-east-1"),
    endpoint: getEnv("E2_ENDPOINT", "https://s3.us-east-1.idrivee2.com"),
    credentials: {
      accessKeyId: getEnv("E2_ACCESS_KEY_ID"),
      secretAccessKey: getEnv("E2_SECRET_ACCESS_KEY"),
    },
    forcePathStyle: true,
  });
  return _client;
}

async function streamToBuffer(stream: NodeJS.ReadableStream): Promise<Buffer> {
  const chunks: Buffer[] = [];
  for await (const chunk of stream) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }
  return Buffer.concat(chunks);
}

/** Download a file from S3 as a Buffer. Returns null if not found. */
export async function downloadBuffer(key: string): Promise<Buffer | null> {
  try {
    const resp = await getClient().send(
      new GetObjectCommand({ Bucket: getBucket(), Key: key })
    );
    if (!resp.Body) return null;
    return streamToBuffer(resp.Body as NodeJS.ReadableStream);
  } catch (e: any) {
    if (e.name === "NoSuchKey" || e.$metadata?.httpStatusCode === 404) return null;
    throw e;
  }
}

/** Download a file from S3 as UTF-8 text. Returns null if not found. */
export async function downloadText(key: string): Promise<string | null> {
  const buf = await downloadBuffer(key);
  return buf ? buf.toString("utf-8") : null;
}

/** Download and parse a JSON file from S3. Returns null if not found. */
export async function downloadJson<T = unknown>(key: string): Promise<T | null> {
  const text = await downloadText(key);
  return text ? (JSON.parse(text) as T) : null;
}

/** List object keys under a prefix. */
export async function listKeys(prefix: string): Promise<string[]> {
  const client = getClient();
  const bucket = getBucket();
  const keys: string[] = [];
  let continuationToken: string | undefined;

  do {
    const resp = await client.send(
      new ListObjectsV2Command({
        Bucket: bucket,
        Prefix: prefix,
        ContinuationToken: continuationToken,
      })
    );
    if (resp.Contents) {
      for (const obj of resp.Contents) {
        if (obj.Key) keys.push(obj.Key);
      }
    }
    continuationToken = resp.IsTruncated ? resp.NextContinuationToken : undefined;
  } while (continuationToken);

  return keys;
}
