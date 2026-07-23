import type {
  AdminCrawlJob,
  AdminIndexRun,
  AdminOverview,
  AdminSource,
  AgentChatResponse,
  AgentConversation,
  AgentConversationSummary,
  AgentStreamEvent,
  BookshelfCollection,
  BookshelfCollectionVisibility,
  BookshelfEntry,
  BookshelfLinkCreate,
  BookshelfStatus,
  BookshelfUpdate,
  DirectorySource,
  DirectorySourceSort,
  SortDirection,
  Document,
  DocumentDetail,
  EmbeddingMap,
  FriendFeedItem,
  FriendRequests,
  Friendship,
  GraphResponse,
  Page,
  Person,
  SearchResponse,
  SearchScope,
  SourceProfileAnalysis,
  User,
  UserProfile,
  UserWebsite,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

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
    throw new Error(await responseErrorMessage(response, `Request failed: ${response.status}: ${url}`));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function responseErrorMessage(response: Response, fallback: string): Promise<string> {
  const raw = await response.text();
  if (!raw) return fallback;
  try {
    const payload = JSON.parse(raw) as { detail?: unknown };
    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail;
    }
  } catch {
    // Preserve non-JSON error bodies as-is.
  }
  return raw;
}

export function getMe(): Promise<User> {
  return request<User>('/api/me');
}

export function getMyProfile(): Promise<UserProfile> {
  return request<UserProfile>('/api/profile');
}

export function updateMyProfile(payload: {
  username?: string;
  display_name?: string | null;
  bio?: string | null;
}): Promise<UserProfile> {
  return request<UserProfile>('/api/profile', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function attachProfileWebsite(payload: {
  url: string;
  label?: string | null;
}): Promise<UserWebsite> {
  return request<UserWebsite>('/api/profile/websites', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteProfileWebsite(websiteId: number): Promise<void> {
  return request<void>(`/api/profile/websites/${websiteId}`, { method: 'DELETE' });
}

export function findUsers(q: string, limit = 20): Promise<Person[]> {
  const search = new URLSearchParams({ q, limit: String(limit) });
  return request<Person[]>(`/api/users?${search.toString()}`);
}

export function getUserProfile(username: string): Promise<UserProfile> {
  return request<UserProfile>(`/api/users/${encodeURIComponent(username)}`);
}

export function getFriends(): Promise<Friendship[]> {
  return request<Friendship[]>('/api/friends');
}

export function getFriendRequests(): Promise<FriendRequests> {
  return request<FriendRequests>('/api/friends/requests');
}

export function sendFriendRequest(userId: number): Promise<Friendship> {
  return request<Friendship>('/api/friends/requests', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  });
}

export function acceptFriendRequest(friendshipId: number): Promise<Friendship> {
  return request<Friendship>(`/api/friends/requests/${friendshipId}/accept`, {
    method: 'POST',
  });
}

export function removeFriendRequest(friendshipId: number): Promise<void> {
  return request<void>(`/api/friends/requests/${friendshipId}`, {
    method: 'DELETE',
  });
}

export function disconnectFriend(friendshipId: number): Promise<void> {
  return request<void>(`/api/friends/${friendshipId}`, { method: 'DELETE' });
}

export function getFriendsFeed(params: { limit?: number; offset?: number } = {}): Promise<Page<FriendFeedItem>> {
  const search = new URLSearchParams({
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return request<Page<FriendFeedItem>>(`/api/friends/feed?${search.toString()}`);
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

function clearCachePrefix(prefix: string) {
  for (const key of apiCache.keys()) {
    if (key.startsWith(prefix)) apiCache.delete(key);
  }
}

function clearBookshelfCache() {
  clearCachePrefix('bookshelf:');
}

function clearConversationCache() {
  clearCachePrefix('agent-conversations:');
}

export function chatSearch(
  message: string,
  conversationUuid?: string,
  scope: SearchScope = 'all',
): Promise<AgentChatResponse> {
  clearConversationCache();
  return request<AgentChatResponse>('/api/agent-chat', {
    method: 'POST',
    body: JSON.stringify({ message, conversation_uuid: conversationUuid, scope }),
  });
}

export async function streamChatSearch(
  message: string,
  conversationUuid: string | undefined,
  scope: SearchScope,
  onEvent: (event: AgentStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  clearConversationCache();
  const response = await fetch(`${API_BASE}/api/agent-chat/stream`, {
    method: 'POST',
    headers: await requestHeaders(),
    body: JSON.stringify({ message, conversation_uuid: conversationUuid, scope }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(await responseErrorMessage(response, `Request failed: ${response.status}`));
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
  clearConversationCache();
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

export function getAgentConversations(params: { limit?: number; offset?: number; q?: string } = {}): Promise<AgentConversationSummary[]> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 100));
  search.set('offset', String(params.offset ?? 0));
  if (params.q?.trim()) search.set('q', params.q.trim());
  return cachedRequest<AgentConversationSummary[]>(
    `agent-conversations:${search.toString()}`,
    `/api/agent-conversations?${search.toString()}`,
  );
}

export function getAgentConversation(conversationUuid: string): Promise<AgentConversation> {
  return cachedRequest<AgentConversation>(`agent-conversations:detail:${conversationUuid}`, `/api/agent-conversations/${conversationUuid}`);
}

export function searchCorpus(query: string, limit = 50): Promise<SearchResponse> {
  const search = new URLSearchParams();
  search.set('q', query);
  search.set('limit', String(limit));
  return request<SearchResponse>(`/api/search?${search.toString()}`);
}

export function searchDocuments(query: string, limit = 8): Promise<SearchResponse> {
  const search = new URLSearchParams();
  search.set('q', query);
  search.set('limit', String(limit));
  return request<SearchResponse>(`/api/documents/search?${search.toString()}`);
}

export function getDocument(documentUuid: string): Promise<DocumentDetail> {
  return cachedRequest<DocumentDetail>(`document:${documentUuid}`, `/api/documents/${documentUuid}`);
}

export function getBookshelf(params: { status?: BookshelfStatus | 'favorite'; limit?: number; offset?: number } = {}): Promise<Page<BookshelfEntry>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 100));
  search.set('offset', String(params.offset ?? 0));
  if (params.status) search.set('status', params.status);
  return cachedRequest<Page<BookshelfEntry>>(`bookshelf:entries:${search.toString()}`, `/api/bookshelf?${search.toString()}`);
}

export function updateDocumentBookshelf(documentUuid: string, payload: BookshelfUpdate): Promise<BookshelfEntry> {
  clearBookshelfCache();
  return request<BookshelfEntry>(`/api/documents/${documentUuid}/bookshelf`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function createBookshelfLink(payload: BookshelfLinkCreate): Promise<BookshelfEntry> {
  clearBookshelfCache();
  return request<BookshelfEntry>('/api/bookshelf/links', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getBookshelfCollections(): Promise<BookshelfCollection[]> {
  return cachedRequest<BookshelfCollection[]>('bookshelf:collections', '/api/bookshelf/collections');
}

export function createBookshelfCollection(payload: { name: string; description?: string | null; visibility?: BookshelfCollectionVisibility }): Promise<BookshelfCollection> {
  clearBookshelfCache();
  return request<BookshelfCollection>('/api/bookshelf/collections', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateBookshelfCollection(collectionId: number, payload: { name?: string | null; description?: string | null; visibility?: BookshelfCollectionVisibility | null }): Promise<BookshelfCollection> {
  clearBookshelfCache();
  return request<BookshelfCollection>(`/api/bookshelf/collections/${collectionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteBookshelfCollection(collectionId: number): Promise<void> {
  clearBookshelfCache();
  return request<void>(`/api/bookshelf/collections/${collectionId}`, {
    method: 'DELETE',
  });
}

export function addBookshelfCollectionItem(collectionId: number, documentUuid: string): Promise<BookshelfCollection> {
  clearBookshelfCache();
  return request<BookshelfCollection>(`/api/bookshelf/collections/${collectionId}/items`, {
    method: 'POST',
    body: JSON.stringify({ document_uuid: documentUuid }),
  });
}

export function removeBookshelfCollectionItem(collectionId: number, documentUuid: string): Promise<BookshelfCollection> {
  clearBookshelfCache();
  return request<BookshelfCollection>(`/api/bookshelf/collections/${collectionId}/items/${documentUuid}`, {
    method: 'DELETE',
  });
}

export function getEmbeddingMap(limit = 3000): Promise<EmbeddingMap> {
  return cachedRequest<EmbeddingMap>(
    `embedding-map:${limit}:essay`,
    `/api/embedding-map?limit=${limit}&document_type=essay`,
  );
}

export function getGraph(params: { mode?: 'sources' | 'documents'; limit?: number; domain?: string; sourceId?: number; documentUuid?: string; depth?: number } = {}): Promise<GraphResponse> {
  const search = new URLSearchParams();
  search.set('mode', params.mode ?? 'documents');
  search.set('limit', String(params.limit ?? 140));
  if (params.domain) search.set('domain', params.domain);
  if (params.sourceId) search.set('source_id', String(params.sourceId));
  if (params.documentUuid) search.set('document_uuid', params.documentUuid);
  if (params.depth) search.set('depth', String(params.depth));
  const path = `/api/graph?${search.toString()}`;
  return cachedRequest<GraphResponse>(`graph:${search.toString()}`, path);
}

export function searchGraphSources(q: string, limit = 12): Promise<AdminSource[]> {
  const search = new URLSearchParams();
  search.set('q', q);
  search.set('limit', String(limit));
  return request<AdminSource[]>(`/api/graph/sources/search?${search.toString()}`);
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

export function getDirectorySources(params: { status?: string; q?: string; sort?: DirectorySourceSort; direction?: SortDirection; limit?: number; offset?: number } = {}): Promise<Page<DirectorySource>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  search.set('sort', params.sort ?? 'inbound');
  search.set('direction', params.direction ?? 'desc');
  if (params.status && params.status !== 'all') search.set('status', params.status);
  if (params.q) search.set('q', params.q);
  return request<Page<DirectorySource>>(`/api/directory/sources?${search.toString()}`);
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
