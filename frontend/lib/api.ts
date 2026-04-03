const CLOUD_RUN_URL = 'https://architecture-review-agent-vtqsnscssq-uc.a.run.app';

function getApiBase(): string {
  // Allow override via environment variable (set NEXT_PUBLIC_API_URL= for local dev)
  if (process.env.NEXT_PUBLIC_API_URL !== undefined) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  return CLOUD_RUN_URL;
}

export async function submitAnalysis(file: File, model: string): Promise<string> {
  const form = new FormData();
  form.append('document', file);
  form.append('model', model);

  const res = await fetch(`${getApiBase()}/api/analyze`, { method: 'POST', body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Server error' }));
    throw new Error((err as { detail?: string }).detail || 'Analysis request failed');
  }
  const data = (await res.json()) as { job_id: string };
  return data.job_id;
}

export interface ModelOption {
  value: string;
  label: string;
  badge: string;
}

export async function fetchModels(): Promise<{ models: ModelOption[]; default: string }> {
  const res = await fetch(`${getApiBase()}/api/models`);
  if (!res.ok) throw new Error('Failed to fetch models');
  return res.json();
}

export async function pollJobStatus(jobId: string): Promise<import('./types').JobStatus> {
  const res = await fetch(`${getApiBase()}/api/status/${jobId}`);
  if (!res.ok) throw new Error('Failed to fetch job status');
  return res.json() as Promise<import('./types').JobStatus>;
}

export async function fetchResults(jobId: string): Promise<import('./types').AnalysisResults> {
  const res = await fetch(`${getApiBase()}/api/results/${jobId}`);
  if (!res.ok) throw new Error('Failed to fetch results');
  return res.json() as Promise<import('./types').AnalysisResults>;
}
