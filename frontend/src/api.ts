const DEFAULT_BASE = `${window.location.origin}`;

const apiBase =
  import.meta.env.VITE_API_BASE?.replace(/\/$/, "") ||
  DEFAULT_BASE.replace(/\/$/, "");

export type RipJobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface RipJobLogEntry {
  cursor: number;
  timestamp: string;
  level: string;
  message: string;
}

export interface RipJobView {
  job_id: string;
  status: RipJobStatus;
  theme_url: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  log_tail: {
    entries: RipJobLogEntry[];
    next_cursor: number;
  };
  download_url: string | null;
  error: string | null;
  download_size: number | null;
}

export interface CreateJobResponse {
  data: RipJobView;
}

export interface JobResponse {
  data: RipJobView;
}

export interface JobLogsResponse {
  data: {
    job_id: string;
    entries: RipJobLogEntry[];
    next_cursor: number;
    has_more: boolean;
  };
}

export async function createJob(themeUrl: string): Promise<RipJobView> {
  const res = await fetch(`${apiBase}/v1/rips`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ theme_url: themeUrl })
  });

  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    const message = payload?.error?.message ?? `Request failed (${res.status})`;
    throw new Error(message);
  }

  const json: CreateJobResponse = await res.json();
  return json.data;
}

export async function fetchJob(jobId: string): Promise<RipJobView> {
  const res = await fetch(`${apiBase}/v1/rips/${jobId}`);
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    const message = payload?.error?.message ?? `Request failed (${res.status})`;
    throw new Error(message);
  }
  const json: JobResponse = await res.json();
  return json.data;
}

export async function fetchLogs(
  jobId: string,
  since: number
): Promise<JobLogsResponse["data"]> {
  const query = new URLSearchParams({ since: since.toString() });
  const res = await fetch(`${apiBase}/v1/rips/${jobId}/logs?${query}`);
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    const message = payload?.error?.message ?? `Request failed (${res.status})`;
    throw new Error(message);
  }
  const json: JobLogsResponse = await res.json();
  return json.data;
}

export async function cancelJob(jobId: string): Promise<void> {
  const res = await fetch(`${apiBase}/v1/rips/${jobId}`, {
    method: "DELETE"
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    const message = payload?.error?.message ?? `Request failed (${res.status})`;
    throw new Error(message);
  }
}

