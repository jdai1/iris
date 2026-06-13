import type { AdminCrawlJob, AdminIndexRun, AdminOverview, AdminSource, AgentChatResponse, AgentConversation, AgentConversationSummary, DigestRecommendation, Document, EmbeddingMap, EmbeddingNeighbor, GraphResponse, Page, SearchResponse, SourceProfileAnalysis } from './types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8001';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
      ...options,
    });
  } catch (err) {
    await new Promise((resolve) => setTimeout(resolve, 150));
    try {
      response = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
        ...options,
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

export function searchCorpus(query: string): Promise<SearchResponse> {
  return request<SearchResponse>(`/api/agentic-search?q=${encodeURIComponent(query)}`);
}

export function chatSearch(message: string, conversationId?: number): Promise<AgentChatResponse> {
  return request<AgentChatResponse>('/api/agent-chat', {
    method: 'POST',
    body: JSON.stringify({ message, limit: 12, conversation_id: conversationId }),
  });
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
  return request<EmbeddingMap>(`/api/embedding-map?limit=${limit}&document_type=essay`);
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
  return request<GraphResponse>(`/api/graph?${search.toString()}`);
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
