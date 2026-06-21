import type { AdminCrawlJob, AdminIndexRun, AdminOverview, AdminSource, AgentChatResponse, AgentConversation, AgentConversationSummary, AgentStreamEvent, DigestRecommendation, Document, EmbeddingMap, EmbeddingNeighbor, GraphResponse, Page, SourceProfileAnalysis, User } from './types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8001';

const apiCache = new Map<string, Promise<unknown>>();
let authTokenProvider: (() => Promise<string | null>) | null = null;

export function setAuthTokenProvider(provider: (() => Promise<string | null>) | null) {
  authTokenProvider = provider;
  apiCache.clear();
}

async function requestHeaders(headers?: HeadersInit): Promise<HeadersInit> {
  const token = authTokenProvider ? await authTokenProvider() : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(headers ?? {}),
  };
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers = await requestHeaders(options?.headers);
  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (err) {
    await new Promise((resolve) => setTimeout(resolve, 150));
    try {
      response = await fetch(url, {
        ...options,
        headers,
      });
    } catch (retryErr) {
      const message = retryErr instanceof Error ? retryErr.message : 'request failed';
      throw new Error(`${message}: ${url}`);
    }
  }
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}: ${url}`);
  }
  return response.json() as Promise<T>;
}

export function getMe(): Promise<User> {
  return request<User>('/api/me');
}

function cachedRequest<T>(key: string, path: string): Promise<T> {
  const existing = apiCache.get(key);
  if (existing) return existing as Promise<T>;
  const promise = request<T>(path).catch((err) => {
    apiCache.delete(key);
    throw err;
  });
  apiCache.set(key, promise);
  return promise;
}

export function chatSearch(message: string, conversationId?: number): Promise<AgentChatResponse> {
  return request<AgentChatResponse>('/api/agent-chat', {
    method: 'POST',
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
}

export async function streamChatSearch(
  message: string,
  conversationId: number | undefined,
  onEvent: (event: AgentStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/agent-chat/stream`, {
    method: 'POST',
    headers: await requestHeaders(),
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  });
  if (!response.ok || !response.body) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';
    for (const chunk of chunks) {
      const parsed = parseSseChunk(chunk);
      if (parsed) onEvent(parsed);
    }
    if (done) break;
  }

  const parsed = parseSseChunk(buffer);
  if (parsed) onEvent(parsed);
}

function parseSseChunk(chunk: string): AgentStreamEvent | null {
  const lines = chunk.split('\n');
  const eventLine = lines.find((line) => line.startsWith('event:'));
  const dataLines = lines.filter((line) => line.startsWith('data:'));
  if (!eventLine || dataLines.length === 0) return null;
  const event = eventLine.slice('event:'.length).trim();
  const data = JSON.parse(dataLines.map((line) => line.slice('data:'.length).trim()).join('\n'));
  return { event, data } as AgentStreamEvent;
}

export function getAgentConversations(): Promise<AgentConversationSummary[]> {
  return request<AgentConversationSummary[]>('/api/agent-conversations?limit=20');
}

export function getAgentConversation(conversationId: number): Promise<AgentConversation> {
  return request<AgentConversation>(`/api/agent-conversations/${conversationId}`);
}

export function getDigest(): Promise<DigestRecommendation[]> {
  return request<DigestRecommendation[]>('/api/digest?limit=20');
}

export function getEmbeddingMap(limit = 3000): Promise<EmbeddingMap> {
  return cachedRequest<EmbeddingMap>(
    `embedding-map:${limit}:essay`,
    `/api/embedding-map?limit=${limit}&document_type=essay`,
  );
}

export function getEmbeddingNeighbors(documentId: number, limit = 5): Promise<EmbeddingNeighbor[]> {
  return request<EmbeddingNeighbor[]>(`/api/documents/${documentId}/embedding-neighbors?limit=${limit}`);
}

export function getGraph(params: { mode?: 'sources' | 'documents'; limit?: number; domain?: string; sourceId?: number; documentId?: number } = {}): Promise<GraphResponse> {
  const search = new URLSearchParams();
  search.set('mode', params.mode ?? 'documents');
  search.set('limit', String(params.limit ?? 140));
  if (params.domain) search.set('domain', params.domain);
  if (params.sourceId) search.set('source_id', String(params.sourceId));
  if (params.documentId) search.set('document_id', String(params.documentId));
  const path = `/api/graph?${search.toString()}`;
  return cachedRequest<GraphResponse>(`graph:${search.toString()}`, path);
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

export function getAdminDocuments(params: { limit?: number; offset?: number; sourceId?: number; documentType?: string; crawlJobId?: number; indexRunId?: number } = {}): Promise<Page<Document>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 100));
  search.set('offset', String(params.offset ?? 0));
  if (params.sourceId) search.set('source_id', String(params.sourceId));
  if (params.documentType && params.documentType !== 'all') search.set('document_type', params.documentType);
  if (params.crawlJobId) search.set('crawl_job_id', String(params.crawlJobId));
  if (params.indexRunId) search.set('index_run_id', String(params.indexRunId));
  return request<Page<Document>>(`/api/documents?${search.toString()}`);
}

export function getSourceProfileAnalysis(sourceId: number): Promise<SourceProfileAnalysis | null> {
  return request<SourceProfileAnalysis | null>(`/api/sources/${sourceId}/profile-analysis`);
}

export function generateSourceProfileAnalysis(sourceId: number, force = false): Promise<SourceProfileAnalysis> {
  return request<SourceProfileAnalysis>(`/api/sources/${sourceId}/profile-analysis?force=${force ? 'true' : 'false'}`, { method: 'POST' });
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
