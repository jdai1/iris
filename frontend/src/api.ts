import type { AdminCrawlJob, AdminIndexRun, AdminOverview, AdminSource, DigestItem, Document, Page, SearchResponse, Source } from './types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function searchCorpus(query: string): Promise<SearchResponse> {
  return request<SearchResponse>(`/api/search?q=${encodeURIComponent(query)}`);
}

export function getDigest(): Promise<DigestItem[]> {
  return request<DigestItem[]>('/api/digest?limit=20');
}

export function sendFeedback(payload: {
  document_id: number;
  surface: string;
  action: string;
  search_id?: number | null;
  digest_item_id?: number | null;
}): Promise<{ ok: boolean }> {
  return request('/api/feedback', { method: 'POST', body: JSON.stringify(payload) });
}

export function getSources(): Promise<Source[]> {
  return request<Source[]>('/api/sources');
}

export function createSource(url: string, crawlNow = false): Promise<Source> {
  return request<Source>('/api/sources', {
    method: 'POST',
    body: JSON.stringify({ url, crawl_now: crawlNow, max_pages: 50, max_depth: 3 }),
  });
}

export function crawlSource(sourceId: number): Promise<unknown> {
  return request(`/api/sources/${sourceId}/crawl?max_pages=50&max_depth=3`, { method: 'POST' });
}

export function getAdminOverview(): Promise<AdminOverview> {
  return request<AdminOverview>('/api/admin/overview');
}

export function getAdminSources(params: { status?: string; q?: string; limit?: number; offset?: number } = {}): Promise<Page<AdminSource>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  if (params.status && params.status !== 'all') search.set('status', params.status);
  if (params.q) search.set('q', params.q);
  return request<Page<AdminSource>>(`/api/admin/sources?${search.toString()}`);
}

export function getAdminDocuments(params: { limit?: number; offset?: number; sourceId?: number; documentType?: string } = {}): Promise<Page<Document>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 100));
  search.set('offset', String(params.offset ?? 0));
  if (params.sourceId) search.set('source_id', String(params.sourceId));
  if (params.documentType && params.documentType !== 'all') search.set('document_type', params.documentType);
  return request<Page<Document>>(`/api/documents?${search.toString()}`);
}

export function getAdminCrawlJobs(params: { limit?: number; offset?: number; status?: string; sourceId?: number; indexRunId?: number } = {}): Promise<Page<AdminCrawlJob>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  if (params.status && params.status !== 'all') search.set('status', params.status);
  if (params.sourceId) search.set('source_id', String(params.sourceId));
  if (params.indexRunId) search.set('index_run_id', String(params.indexRunId));
  return request<Page<AdminCrawlJob>>(`/api/admin/crawl-jobs?${search.toString()}`);
}

export function getAdminIndexRuns(params: { limit?: number; offset?: number; status?: string } = {}): Promise<Page<AdminIndexRun>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  if (params.status && params.status !== 'all') search.set('status', params.status);
  return request<Page<AdminIndexRun>>(`/api/admin/index-runs?${search.toString()}`);
}
