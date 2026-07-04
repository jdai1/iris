import { FormEvent, MouseEvent, ReactNode, useEffect, useRef, useState } from 'react';
import type { User as FirebaseUser } from 'firebase/auth';
import { getRedirectResult, onAuthStateChanged, signInWithPopup, signInWithRedirect, signOut } from 'firebase/auth';
import {
  Box,
  Button,
  Flex,
  Heading,
  SimpleGrid,
  Stack,
  Text,
} from '@chakra-ui/react';
import { ArrowUpRight, BookOpen, ChevronDown, GitFork, LayoutDashboard, LogOut, MoreVertical, Orbit, Search, Settings, Trash2, UserCircle, Users } from 'lucide-react';
import {
  addBookshelfCollectionItem,
  createBookshelfCollection,
  createBookshelfLink,
  deleteBookshelfCollection,
  getAgentConversation,
  getAgentConversations,
  getAdminCrawlJobs,
  getAdminDocuments,
  getAdminIndexRuns,
  getAdminOverview,
  getAdminSources,
  getBookshelf,
  getBookshelfCollections,
  getDocument,
  getDirectorySources,
  getMe,
  getSourceProfileAnalysis,
  removeBookshelfCollectionItem,
  searchCorpus,
  searchDocuments,
  setAuthTokenProvider,
  streamChatSearch,
  updateDocumentBookshelf,
} from './api';
import { auth, firebaseEnabled, googleProvider } from './firebase';
import { EmbeddingExplorer } from './EmbeddingExplorer';
import { GraphExplorer } from './GraphExplorer';
import { CorpusSearchForm } from './CorpusSearchForm';
import { DocumentCard } from './components/DocumentCard';
import { Pagination, ProfilePagination, type PageState } from './components/Pagination';
import { ProfileAnalysisCard } from './components/ProfileAnalysisCard';
import { StatusPill } from './components/StatusPill';
import type {
  AdminCrawlJob,
  AdminIndexRun,
  AdminOverview,
  AdminSource,
  AgentConversation,
  AgentConversationSummary,
  AgentStep,
  BookshelfCollection,
  BookshelfEntry,
  BookshelfStatus,
  DirectorySource,
  DirectorySourceSort,
  SortDirection,
  Page,
  SearchResult,
  Document,
  DocumentDetail,
  SourceProfileAnalysis,
  User as IrisUser,
} from './types';

type View = 'search' | 'bookshelf' | 'directory' | 'explore' | 'graph' | 'admin';
type ProfileTarget = { sourceId: number; domain: string } | null;
type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  results?: SearchResult[];
  steps?: AgentStep[];
  pending?: boolean;
};

const emptyPage = <T,>(): Page<T> => ({
  items: [],
  total: 0,
  limit: 50,
  offset: 0,
  has_next: false,
  has_previous: false,
});

const VIEW_STORAGE_KEY = 'iris.activeView';
const ACTIVE_CHAT_STORAGE_KEY = 'iris.activeChatId';
const SEARCH_RELOAD_STORAGE_KEY = 'iris.searchReloading';
const HISTORY_PAGE_SIZE = 15;
const views: View[] = ['search', 'bookshelf', 'directory', 'explore', 'graph', 'admin'];
const viewPaths: Record<View, string> = {
  search: '/search',
  bookshelf: '/bookshelf',
  directory: '/directory',
  explore: '/explore',
  graph: '/graph',
  admin: '/admin',
};

function initialView(): View {
  if (typeof window === 'undefined') return 'search';
  const pathView = viewFromPath(window.location.pathname);
  if (pathView) return pathView;
  const saved = window.localStorage.getItem(VIEW_STORAGE_KEY);
  return views.includes(saved as View) ? (saved as View) : 'search';
}

function viewFromPath(pathname: string): View | null {
  const normalized = pathname.replace(/\/+$/, '') || '/';
  if (normalized === '/') return null;
  if (normalized.startsWith('/directory/')) return 'directory';
  const match = views.find((view) => viewPaths[view] === normalized);
  return match ?? null;
}

function profileTargetFromPath(pathname: string): ProfileTarget {
  const normalized = pathname.replace(/\/+$/, '');
  if (!normalized.startsWith('/directory/')) return null;
  const domain = decodeURIComponent(normalized.slice('/directory/'.length)).trim();
  return domain ? { sourceId: 0, domain } : null;
}

function defaultArtifactWidth() {
  if (typeof window === 'undefined') return 560;
  const available = window.innerWidth - 208 - 24 - 32;
  return Math.min(900, Math.max(360, Math.round(available / 2)));
}

function SearchView({ onOpenProfile }: { onOpenProfile: (sourceId: number, domain: string) => void }) {
  const [query, setQuery] = useState('');
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [history, setHistory] = useState<AgentConversationSummary[]>([]);
  const [historyQuery, setHistoryQuery] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [startedNewChat, setStartedNewChat] = useState(false);
  const [selectedResultMessageId, setSelectedResultMessageId] = useState<string | null>(null);
  const [searchesOpen, setSearchesOpen] = useState(false);
  const [artifactWidth, setArtifactWidth] = useState(defaultArtifactWidth);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const historyRef = useRef<HTMLDivElement | null>(null);
  const didLoadInitialConversation = useRef(false);
  const shouldRestoreConversation = useRef(
    typeof window !== 'undefined' && window.sessionStorage.getItem(SEARCH_RELOAD_STORAGE_KEY) === '1',
  );

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem(SEARCH_RELOAD_STORAGE_KEY);
    }
    loadInitialHistory();
    return () => {
      if (typeof window === 'undefined') return;
      if (window.sessionStorage.getItem(SEARCH_RELOAD_STORAGE_KEY) === '1') return;
      window.sessionStorage.removeItem(ACTIVE_CHAT_STORAGE_KEY);
    };
  }, []);

  useEffect(() => {
    function preserveChatForReload() {
      window.sessionStorage.setItem(SEARCH_RELOAD_STORAGE_KEY, '1');
    }
    window.addEventListener('beforeunload', preserveChatForReload);
    return () => window.removeEventListener('beforeunload', preserveChatForReload);
  }, []);

  useEffect(() => {
    if (conversationId) {
      window.sessionStorage.setItem(ACTIVE_CHAT_STORAGE_KEY, String(conversationId));
    } else {
      window.sessionStorage.removeItem(ACTIVE_CHAT_STORAGE_KEY);
    }
  }, [conversationId]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      refreshHistory(historyQuery);
    }, 160);
    return () => window.clearTimeout(timeout);
  }, [historyQuery]);

  const resultTurns = messages
    .map((message, index) => {
      if (message.role !== 'assistant' || !message.results?.length) return null;
      const userMessage = [...messages.slice(0, index)].reverse().find((item) => item.role === 'user');
      return {
        id: message.id,
        query: userMessage?.content ?? 'Previous search',
        results: message.results,
      };
    })
    .filter((item): item is { id: string; query: string; results: SearchResult[] } => Boolean(item));
  const selectedResultTurn =
    resultTurns.find((turn) => turn.id === selectedResultMessageId) ?? resultTurns[resultTurns.length - 1] ?? null;

  useEffect(() => {
    const latest = resultTurns[resultTurns.length - 1];
    if (!latest) {
      setSelectedResultMessageId(null);
      return;
    }
    if (!selectedResultMessageId || !resultTurns.some((turn) => turn.id === selectedResultMessageId)) {
      setSelectedResultMessageId(latest.id);
    }
  }, [resultTurns.length, selectedResultMessageId]);

  async function refreshHistory(nextQuery = historyQuery) {
    setHistoryLoading(true);
    try {
      const items = await getAgentConversations({ limit: HISTORY_PAGE_SIZE, q: nextQuery });
      setHistory(items);
      setHistoryHasMore(items.length === HISTORY_PAGE_SIZE);
    } catch {
      // History is secondary; leave the chat surface usable if it fails.
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadMoreHistory() {
    if (historyLoadingMore || historyLoading) return;
    setHistoryLoadingMore(true);
    try {
      const items = await getAgentConversations({ limit: HISTORY_PAGE_SIZE, offset: history.length, q: historyQuery });
      setHistory((current) => [...current, ...items]);
      setHistoryHasMore(items.length === HISTORY_PAGE_SIZE);
    } catch {
      // History is secondary; keep the current list intact.
    } finally {
      setHistoryLoadingMore(false);
    }
  }

  async function loadInitialHistory() {
    if (didLoadInitialConversation.current) return;
    didLoadInitialConversation.current = true;
    setHistoryLoading(true);
    try {
      const items = await getAgentConversations({ limit: HISTORY_PAGE_SIZE });
      setHistory(items);
      setHistoryHasMore(items.length === HISTORY_PAGE_SIZE);
      const activeChatId = Number(window.sessionStorage.getItem(ACTIVE_CHAT_STORAGE_KEY));
      if (shouldRestoreConversation.current && Number.isFinite(activeChatId) && activeChatId > 0) {
        await loadConversation(activeChatId);
      }
    } catch {
      // History is secondary; start on a clean chat if it fails.
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadConversation(id: number) {
    if (loading) return;
    setError(null);
    try {
      const conversation = await getAgentConversation(id);
      setConversationId(conversation.id);
      setStartedNewChat(false);
      setMessages(messagesFromConversation(conversation));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load chat');
    }
  }

  function startNewChat() {
    if (loading) return;
    setStartedNewChat(true);
    setConversationId(undefined);
    setMessages([]);
    setSelectedResultMessageId(null);
    setError(null);
  }

  function handleHistoryScroll() {
    const node = historyRef.current;
    if (!node || !historyHasMore || historyLoading || historyLoadingMore) return;
    if (node.scrollTop + node.clientHeight >= node.scrollHeight - 80) {
      loadMoreHistory();
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const message = query.trim();
    if (!message || loading) return;
    const turnId = Date.now().toString();
    const assistantId = `assistant-${turnId}`;
    setMessages((current) => [
      ...current,
      { id: `user-${turnId}`, role: 'user', content: message },
      { id: assistantId, role: 'assistant', content: '', steps: [], pending: true },
    ]);
    setQuery('');
    setLoading(true);
    setError(null);
    try {
      await streamChatSearch(message, conversationId, (event) => {
        if (event.event === 'conversation') {
          setConversationId(event.data.conversation_id);
          return;
        }
        if (event.event === 'step') {
          appendAssistantStep(assistantId, event.data.step);
          return;
        }
        if (event.event === 'tool_result') {
          replaceOrAppendAssistantStep(assistantId, event.data.step);
          return;
        }
        if (event.event === 'final') {
          setSelectedResultMessageId(assistantId);
          setSearchesOpen(false);
          setMessages((current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    content: event.data.answer,
                    results: event.data.results,
                    pending: false,
                  }
                : item,
            ),
          );
          refreshHistory();
        }
        if (event.event === 'error') {
          throw new Error(event.data.message);
        }
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId ? { ...item, content: 'Search failed before the agent could finish.', pending: false } : item,
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  function appendAssistantStep(assistantId: string, step: AgentStep) {
    if (isSyntheticStep(step)) return;
    setMessages((current) =>
      current.map((item) =>
        item.id === assistantId ? { ...item, steps: [...(item.steps ?? []), step] } : item,
      ),
    );
  }

  function replaceOrAppendAssistantStep(assistantId: string, step: AgentStep) {
    if (isSyntheticStep(step)) return;
    setMessages((current) =>
      current.map((item) => {
        if (item.id !== assistantId) return item;
        const steps = item.steps ?? [];
        const last = steps[steps.length - 1];
        if (last?.kind === 'tool' && last.tool === step.tool && last.hits === null) {
          return { ...item, steps: [...steps.slice(0, -1), step] };
        }
        return { ...item, steps: [...steps, step] };
      }),
    );
  }

  function startResizeArtifact(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = artifactWidth;
    function handleMove(moveEvent: PointerEvent) {
      const nextWidth = startWidth - (moveEvent.clientX - startX);
      setArtifactWidth(Math.min(900, Math.max(320, nextWidth)));
    }
    function handleUp() {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    }
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
  }

  return (
    <Box as="section" className="search-view">
      <div className="chat-page-grid">
        <aside className="chat-history-rail">
          <div className="chat-history-rail-header">
            <span>Chats</span>
            <button className="chat-new-button" type="button" onClick={startNewChat} aria-label="New chat" data-tooltip="New chat" data-tooltip-placement="bottom">
              +
            </button>
          </div>
          <form className="corpus-search chat-history-search" onSubmit={(event) => event.preventDefault()}>
            <Search size={15} />
            <input
              value={historyQuery}
              onChange={(event) => setHistoryQuery(event.target.value)}
              placeholder="Search chats"
            />
          </form>
          <div className="chat-history-list" ref={historyRef} onScroll={handleHistoryScroll}>
            {historyLoading && <div className="chat-history-empty">Loading chats...</div>}
            {!historyLoading && history.length === 0 && <div className="chat-history-empty">No saved chats yet.</div>}
            {!historyLoading &&
              history.map((item) => (
                <button
                  key={item.id}
                  className={item.id === conversationId ? 'chat-history-item chat-history-item-active' : 'chat-history-item'}
                  type="button"
                  onClick={() => loadConversation(item.id)}
                >
                  <span>{item.title || 'Untitled search'}</span>
                </button>
              ))}
            {!historyLoading && historyLoadingMore && <div className="chat-history-empty">Loading more...</div>}
          </div>
        </aside>

        <div className="chat-main-panel">

      {error && <div className="error">{error}</div>}

      {messages.length === 0 && (
        <div className="chat-composer chat-composer-start">
          <CorpusSearchForm
            className="search-box chat-input"
            value={query}
            onChange={setQuery}
            onSubmit={submit}
            placeholder={loading ? 'Iris is working...' : 'Message Iris...'}
            disabled={loading || !query.trim()}
            autoFocus
          />
        </div>
      )}

      <Box
        className={selectedResultTurn ? 'chat-shell chat-shell-with-artifact' : 'chat-shell'}
        style={selectedResultTurn ? { '--artifact-width': `${artifactWidth}px` } as React.CSSProperties : undefined}
      >
        <Box className="chat-layout">
          <div className="chat-transcript" ref={transcriptRef}>
            {messages.map((message) => (
              <div key={message.id} className={`chat-message chat-message-${message.role}`}>
                <div className="chat-role">{message.role === 'user' ? 'You' : 'Iris'}</div>
                {message.pending && !message.content ? (
                  <ThinkingState />
                ) : (
                  <MessageContent content={message.content} />
                )}
                {message.steps && message.steps.length > 0 && (
                  <details className="chat-activity">
                    <summary>Activity</summary>
                    <div className="chat-activity-body">
                      {message.steps.map((step, index) => (
                        <div key={`${step.kind}-${step.title}-${index}`} className="activity-row">
                          <span className="activity-dot" />
                          <div>
                            <strong>{activityTitle(step)}</strong>
                            <small>{activityMeta(step)}</small>
                          </div>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
        </Box>

        {selectedResultTurn && (
          <aside className="chat-artifact" aria-label="Search results">
            <button className="chat-artifact-resize" type="button" aria-label="Resize links panel" data-tooltip="Resize links panel" onPointerDown={startResizeArtifact} />
            <div className="chat-artifact-header">
              <span>Links</span>
              <small>{selectedResultTurn.results.length} result{selectedResultTurn.results.length === 1 ? '' : 's'}</small>
            </div>
            {resultTurns.length > 1 && (
              <div className="chat-artifact-tabs">
                <button
                  className="chat-artifact-tabs-toggle"
                  type="button"
                  onClick={() => setSearchesOpen((value) => !value)}
                  aria-expanded={searchesOpen}
                >
                  <span>Searches · {resultTurns.length}</span>
                  <ChevronDown size={14} className={searchesOpen ? 'history-chevron history-chevron-open' : 'history-chevron'} />
                </button>
                <button
                  className="chat-artifact-tab chat-artifact-tab-active"
                  type="button"
                  onClick={() => setSearchesOpen((value) => !value)}
                >
                  <span>{resultTurns.findIndex((turn) => turn.id === selectedResultTurn.id) + 1}</span>
                  <small>{selectedResultTurn.query}</small>
                </button>
                {searchesOpen && (
                  <div className="chat-artifact-tabs-menu">
                    {resultTurns.map((turn, index) => (
                      <button
                        key={turn.id}
                        className={turn.id === selectedResultTurn.id ? 'chat-artifact-tab chat-artifact-tab-active' : 'chat-artifact-tab'}
                        type="button"
                        onClick={() => {
                          setSelectedResultMessageId(turn.id);
                          setSearchesOpen(false);
                        }}
                      >
                        <span>{index + 1}</span>
                        <small>{turn.query}</small>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="chat-artifact-list">
              {selectedResultTurn.results.map((result) => (
                <DocumentCard
                  key={result.document.id}
                  document={result.document}
                  reason={result.reason}
                  score={result.score}
                  onOpenProfile={onOpenProfile}
                  compact
                />
              ))}
            </div>
          </aside>
        )}
        {messages.length > 0 && (
          <div className="chat-composer chat-composer-bottom">
            <CorpusSearchForm
              className="search-box chat-input"
              value={query}
              onChange={setQuery}
              onSubmit={submit}
              placeholder={loading ? 'Iris is working...' : conversationId ? 'Follow up...' : 'Message Iris...'}
              disabled={loading || !query.trim()}
              autoFocus
            />
          </div>
        )}
      </Box>
        </div>
      </div>
    </Box>
  );
}

function ThinkingState() {
  return (
    <p className="chat-pending" aria-live="polite">
      <span>Thinking</span>
      <span className="thinking-word" aria-hidden="true">
        <span>quietly</span>
        <span>through it</span>
        <span>with context</span>
        <span>ahead</span>
      </span>
    </p>
  );
}

function messagesFromConversation(conversation: AgentConversation): ChatMessage[] {
  return conversation.messages
    .filter((message) => !isLegacySyntheticAssistantMessage(message))
    .map((message) => ({
      id: `saved-${message.id}`,
      role: message.role === 'user' ? 'user' : 'assistant',
      content: message.content,
      steps: message.steps?.filter((step) => !isSyntheticStep(step)),
      results: message.results,
      pending: false,
    }));
}

function MessageContent({ content }: { content: string }) {
  const blocks = content.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  if (blocks.length === 0) return null;
  return (
    <div className="message-content">
      {blocks.map((block, blockIndex) => {
        const lines = block.split('\n').map((line) => line.trim()).filter(Boolean);
        const bulletLines = lines.filter((line) => line.startsWith('- '));
        if (bulletLines.length === lines.length) {
          return (
            <ul key={`${block}-${blockIndex}`}>
              {bulletLines.map((line, lineIndex) => (
                <li key={`${line}-${lineIndex}`}>{renderInlineMarkdown(line.slice(2))}</li>
              ))}
            </ul>
          );
        }
        return <p key={`${block}-${blockIndex}`}>{renderInlineMarkdown(block)}</p>;
      })}
    </div>
  );
}

function renderInlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function isSyntheticStep(step: AgentStep): boolean {
  if (step.kind !== 'tool') return true;
  if (step.title === 'Waiting for a corpus query') return true;
  if (step.title === 'Run OpenAI agent loop') return true;
  if (step.title === 'Agent final answer') return true;
  if (step.title === 'Persist selected citations') return true;
  return false;
}

function activityTitle(step: AgentStep): string {
  const tool = step.tool?.toLowerCase();
  if (tool === 'keyword') return 'Keyword';
  if (tool === 'semantic') return 'Semantic';
  if (tool === 'tags') return 'Tags';
  if (tool === 'categories') return 'Categories';
  return step.title.replace(/^Run\s+/i, '');
}

function activityMeta(step: AgentStep): string {
  if (typeof step.hits === 'number') return `${step.hits}`;
  return step.detail.replace(/^Top hits:\s*/i, '');
}

function isLegacySyntheticAssistantMessage(message: AgentConversation['messages'][number]): boolean {
  if (message.role !== 'assistant') return false;
  if (message.results.length > 0) return false;
  const steps = message.steps ?? [];
  const onlySyntheticSteps = steps.length > 0 && steps.every(isSyntheticStep);
  return onlySyntheticSteps && message.content.includes('Tell me what you want to find in the corpus');
}

type BookshelfViewKey = 'unread' | 'favorites' | 'reading-log' | `collection:${number}`;

function BookshelfView({ onDiscover }: { onDiscover: () => void }) {
  const [entries, setEntries] = useState<BookshelfEntry[]>([]);
  const [collections, setCollections] = useState<BookshelfCollection[]>([]);
  const [activeView, setActiveView] = useState<BookshelfViewKey>('unread');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addingLink, setAddingLink] = useState(false);
  const [addingCollectionDocs, setAddingCollectionDocs] = useState(false);
  const [creatingCollection, setCreatingCollection] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');
  const [linkTitle, setLinkTitle] = useState('');
  const [collectionName, setCollectionName] = useState('');
  const [collectionSearchQuery, setCollectionSearchQuery] = useState('');
  const [collectionSearchResults, setCollectionSearchResults] = useState<SearchResult[]>([]);
  const [collectionSearching, setCollectionSearching] = useState(false);
  const [addingDocumentId, setAddingDocumentId] = useState<number | null>(null);
  const [confirmDeleteCollectionId, setConfirmDeleteCollectionId] = useState<number | null>(null);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<Set<number>>(new Set());
  const [lastSelectedDocumentId, setLastSelectedDocumentId] = useState<number | null>(null);
  const [bulkMenuOpen, setBulkMenuOpen] = useState(false);
  const [drawerEntry, setDrawerEntry] = useState<BookshelfEntry | null>(null);
  const [drawerDetail, setDrawerDetail] = useState<DocumentDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const collectionDraftRef = useRef<HTMLInputElement | null>(null);
  const bookshelfPanelRef = useRef<HTMLDivElement | null>(null);
  const drawerRef = useRef<HTMLDivElement | null>(null);

  const tableRows = filterBookshelfEntries(entries, collections, activeView);
  const discoverLabel = 'Discover';
  const activeCollection = activeView.startsWith('collection:')
    ? collections.find((collection) => collection.id === Number(activeView.slice('collection:'.length))) ?? null
    : null;
  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [nextPage, loadedCollections] = await Promise.all([getBookshelf({ limit: 500 }), getBookshelfCollections()]);
      setEntries(nextPage.items);
      setCollections(loadedCollections.filter((collection) => collection.name.trim().toLowerCase() !== 'read next'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bookshelf failed');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (creatingCollection) collectionDraftRef.current?.focus();
  }, [creatingCollection]);

  useEffect(() => {
    setConfirmDeleteCollectionId(null);
    setAddingCollectionDocs(false);
    setCollectionSearchQuery('');
    setCollectionSearchResults([]);
    setSelectedDocumentIds(new Set());
    setLastSelectedDocumentId(null);
    setBulkMenuOpen(false);
  }, [activeView]);

  useEffect(() => {
    if (selectedDocumentIds.size === 0) setBulkMenuOpen(false);
  }, [selectedDocumentIds.size]);

  useEffect(() => {
    if (!drawerEntry) {
      setDrawerDetail(null);
      setDrawerError(null);
      return;
    }
    let cancelled = false;
    setDrawerLoading(true);
    setDrawerError(null);
    getDocument(drawerEntry.document.id)
      .then((detail) => {
        if (!cancelled) setDrawerDetail(detail);
      })
      .catch((err) => {
        if (!cancelled) setDrawerError(err instanceof Error ? err.message : 'Could not load document');
      })
      .finally(() => {
        if (!cancelled) setDrawerLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [drawerEntry?.document.id]);

  useEffect(() => {
    if (selectedDocumentIds.size === 0) return;
    function clearSelectionOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && bookshelfPanelRef.current?.contains(target)) return;
      setSelectedDocumentIds(new Set());
      setLastSelectedDocumentId(null);
      setBulkMenuOpen(false);
    }
    document.addEventListener('pointerdown', clearSelectionOnOutsideClick);
    return () => document.removeEventListener('pointerdown', clearSelectionOnOutsideClick);
  }, [selectedDocumentIds.size]);

  useEffect(() => {
    if (!drawerEntry) return;
    function closeDrawerOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && drawerRef.current?.contains(target)) return;
      setDrawerEntry(null);
    }
    document.addEventListener('pointerdown', closeDrawerOnOutsideClick);
    return () => document.removeEventListener('pointerdown', closeDrawerOnOutsideClick);
  }, [drawerEntry]);

  async function submitLink(event: FormEvent) {
    event.preventDefault();
    if (!linkUrl.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createBookshelfLink({
        url: linkUrl.trim(),
        title: linkTitle.trim() || null,
      });
      setLinkUrl('');
      setLinkTitle('');
      setAddingLink(false);
      setActiveView('unread');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save link');
    } finally {
      setSaving(false);
    }
  }

  async function submitCollection(event: FormEvent) {
    event.preventDefault();
    if (!collectionName.trim()) {
      setCreatingCollection(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const collection = await createBookshelfCollection({
        name: collectionName.trim(),
        description: null,
        visibility: 'private',
      });
      setCollectionName('');
      setCreatingCollection(false);
      setCollections((current) => [...current, collection]);
      setActiveView(`collection:${collection.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create collection');
    } finally {
      setSaving(false);
    }
  }

  async function deleteActiveCollection() {
    if (!activeCollection || saving) return;
    if (confirmDeleteCollectionId !== activeCollection.id) {
      setConfirmDeleteCollectionId(activeCollection.id);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await deleteBookshelfCollection(activeCollection.id);
      setCollections((current) => current.filter((collection) => collection.id !== activeCollection.id));
      setActiveView('unread');
      setCollectionSearchQuery('');
      setCollectionSearchResults([]);
      setConfirmDeleteCollectionId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete collection');
    } finally {
      setSaving(false);
    }
  }

  async function submitCollectionSearch(event: FormEvent) {
    event.preventDefault();
    const query = collectionSearchQuery.trim();
    if (!query) {
      setCollectionSearchResults([]);
      return;
    }
    setCollectionSearching(true);
    setError(null);
    try {
      const response = await searchDocuments(query, 8);
      setCollectionSearchResults(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not search corpus');
    } finally {
      setCollectionSearching(false);
    }
  }

  async function addResultToActiveCollection(result: SearchResult) {
    if (!activeCollection) return;
    setAddingDocumentId(result.document.id);
    setError(null);
    try {
      const collection = await addBookshelfCollectionItem(activeCollection.id, result.document.id);
      setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
      setEntries((current) => {
        if (current.some((entry) => entry.document.id === result.document.id)) return current;
        const entry = collection.items.find((item) => item.document.id === result.document.id);
        return entry ? [entry, ...current] : current;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add document');
    } finally {
      setAddingDocumentId(null);
    }
  }

  async function removeDocumentFromActiveView(documentId: number) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      if (activeCollection) {
        const collection = await removeBookshelfCollectionItem(activeCollection.id, documentId);
        setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
      } else if (activeView === 'favorites') {
        const entry = await updateDocumentBookshelf(documentId, { favorited: false });
        setEntries((current) => current.map((item) => (item.document.id === documentId ? entry : item)));
      } else {
        const entry = await updateDocumentBookshelf(documentId, { status: 'archived' });
        setEntries((current) => current.map((item) => (item.document.id === documentId ? entry : item)));
      }
      setSelectedDocumentIds((current) => {
        if (!current.has(documentId)) return current;
        const next = new Set(current);
        next.delete(documentId);
        return next;
      });
      setBulkMenuOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove document');
    } finally {
      setSaving(false);
    }
  }

  async function addSelectedToCollection(collectionId: number) {
    const documentIds = Array.from(selectedDocumentIds);
    if (documentIds.length === 0 || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updates = await Promise.all(documentIds.map((documentId) => addBookshelfCollectionItem(collectionId, documentId)));
      const collection = updates.at(-1);
      if (collection) {
        setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
      }
      setBulkMenuOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add selected documents');
    } finally {
      setSaving(false);
    }
  }

  async function removeSelectedFromActiveCollection() {
    if (selectedDocumentIds.size === 0 || saving) return;
    const documentIds = Array.from(selectedDocumentIds);
    setSaving(true);
    setError(null);
    try {
      if (activeCollection) {
        const updates = await Promise.all(documentIds.map((documentId) => removeBookshelfCollectionItem(activeCollection.id, documentId)));
        const collection = updates.at(-1);
        if (collection) {
          setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
        }
      } else if (activeView === 'favorites') {
        const updates = await Promise.all(documentIds.map((documentId) => updateDocumentBookshelf(documentId, { favorited: false })));
        setEntries((current) => mergeBookshelfEntryUpdates(current, updates));
      } else {
        const updates = await Promise.all(documentIds.map((documentId) => updateDocumentBookshelf(documentId, { status: 'archived' })));
        setEntries((current) => mergeBookshelfEntryUpdates(current, updates));
      }
      setSelectedDocumentIds(new Set());
      setLastSelectedDocumentId(null);
      setBulkMenuOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove selected documents');
    } finally {
      setSaving(false);
    }
  }

  function selectBookshelfRow(entry: BookshelfEntry, event: MouseEvent<HTMLDivElement>, forceSelect = false) {
    const target = event.target as HTMLElement;
    if (target.closest('a, button, select')) return;
    const documentId = entry.document.id;
    if (event.shiftKey && lastSelectedDocumentId !== null) {
      event.preventDefault();
      const startIndex = tableRows.findIndex((row) => row.document.id === lastSelectedDocumentId);
      const endIndex = tableRows.findIndex((row) => row.document.id === documentId);
      if (startIndex !== -1 && endIndex !== -1) {
        const [start, end] = startIndex < endIndex ? [startIndex, endIndex] : [endIndex, startIndex];
        setSelectedDocumentIds((current) => {
          const next = new Set(current);
          tableRows.slice(start, end + 1).forEach((row) => next.add(row.document.id));
          return next;
        });
        setLastSelectedDocumentId(documentId);
        return;
      }
    }
    if (!forceSelect && !event.metaKey && !event.ctrlKey) return;
    setSelectedDocumentIds((current) => {
      if (event.metaKey || event.ctrlKey) {
        const next = new Set(current);
        if (next.has(documentId)) {
          next.delete(documentId);
        } else {
          next.add(documentId);
        }
        return next;
      }
      return new Set([documentId]);
    });
    setLastSelectedDocumentId(documentId);
    if (forceSelect) setBulkMenuOpen(true);
  }

  function openBookshelfDrawer(entry: BookshelfEntry) {
    setDrawerEntry(entry);
  }

  return (
    <section className="bookshelf-view">
      <div className="bookshelf-playlist-shell">
        <aside className="bookshelf-rail">
          <div className="bookshelf-rail-label">Library</div>
          <button className={activeView === 'unread' ? 'bookshelf-rail-item bookshelf-rail-item-active' : 'bookshelf-rail-item'} type="button" onClick={() => setActiveView('unread')}>
            <span>Read next</span>
            <small>{entries.filter((entry) => entry.status === 'saved').length}</small>
          </button>
          <button className={activeView === 'favorites' ? 'bookshelf-rail-item bookshelf-rail-item-active' : 'bookshelf-rail-item'} type="button" onClick={() => setActiveView('favorites')}>
            <span>Favorites</span>
            <small>{entries.filter((entry) => entry.favorited).length}</small>
          </button>
          <button className={activeView === 'reading-log' ? 'bookshelf-rail-item bookshelf-rail-item-active' : 'bookshelf-rail-item'} type="button" onClick={() => setActiveView('reading-log')}>
            <span>Reading log</span>
            <small>{entries.filter((entry) => entry.status === 'read').length}</small>
          </button>
          <div className="bookshelf-rail-divider" />
          <div className="bookshelf-rail-section-heading">
            <span>Collections</span>
            <button
              type="button"
              onClick={() => {
                setCollectionName('');
                setCreatingCollection(true);
              }}
              aria-label="Create collection"
            >
              +
            </button>
          </div>
          {creatingCollection && (
            <form className="bookshelf-rail-draft" onSubmit={submitCollection}>
              <input
                ref={collectionDraftRef}
                value={collectionName}
                onChange={(event) => setCollectionName(event.target.value)}
                onBlur={() => {
                  if (!collectionName.trim()) setCreatingCollection(false);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    setCollectionName('');
                    setCreatingCollection(false);
                  }
                }}
                placeholder="Untitled collection"
                disabled={saving}
              />
            </form>
          )}
          {collections.map((collection) => (
            <button
              key={collection.id}
              className={activeView === `collection:${collection.id}` ? 'bookshelf-rail-item bookshelf-rail-item-active' : 'bookshelf-rail-item'}
              type="button"
              onClick={() => setActiveView(`collection:${collection.id}`)}
            >
              <span>{collection.name}</span>
              <small>{collection.items.length}</small>
            </button>
          ))}
        </aside>

        <div className="bookshelf-table-panel" ref={bookshelfPanelRef}>
          <div className="bookshelf-toolbar">
            <div className="bookshelf-toolbar-actions">
              <button className="bookshelf-add-filter" type="button">+ Add filter</button>
              {activeCollection && (
                <>
                  <button className="bookshelf-add-filter" type="button" onClick={() => setAddingCollectionDocs((value) => !value)}>
                    {addingCollectionDocs ? 'Done adding' : '+ Add documents'}
                  </button>
                  <button className="bookshelf-delete-collection" type="button" onClick={deleteActiveCollection} disabled={saving}>
                    {confirmDeleteCollectionId === activeCollection.id ? 'Confirm delete' : 'Delete collection'}
                  </button>
                </>
              )}
            </div>
            {selectedDocumentIds.size > 0 && bulkMenuOpen && (
              <div className="bookshelf-bulk-menu">
                <span>{selectedDocumentIds.size} selected</span>
                {collections.length > (activeCollection ? 1 : 0) && (
                  <select
                    value=""
                    onChange={(event) => {
                      const collectionId = Number(event.target.value);
                      if (collectionId) void addSelectedToCollection(collectionId);
                    }}
                    disabled={saving}
                    aria-label="Add selected documents to collection"
                  >
                    <option value="">Add to playlist...</option>
                    {collections
                      .filter((collection) => collection.id !== activeCollection?.id)
                      .map((collection) => (
                        <option key={collection.id} value={collection.id}>{collection.name}</option>
                      ))}
                  </select>
                )}
                <button type="button" onClick={removeSelectedFromActiveCollection} disabled={saving}>
                  <Trash2 size={13} />
                  Remove
                </button>
                <button type="button" onClick={() => setBulkMenuOpen(false)}>
                  Done
                </button>
              </div>
            )}
          </div>

          {activeCollection && addingCollectionDocs && (
            <form className="bookshelf-collection-search" onSubmit={submitCollectionSearch}>
              <label htmlFor="bookshelf-collection-search">Add documents</label>
              <div>
                <Search size={14} />
                <input
                  id="bookshelf-collection-search"
                  value={collectionSearchQuery}
                  onChange={(event) => setCollectionSearchQuery(event.target.value)}
                  placeholder="Keyword search corpus..."
                />
                <button type="submit" disabled={collectionSearching || !collectionSearchQuery.trim()}>
                  Search
                </button>
              </div>
              {collectionSearching && <p>Searching...</p>}
              {collectionSearchResults.length > 0 && (
                <div className="bookshelf-collection-results">
                  {collectionSearchResults.map((result) => {
                    const alreadyAdded = activeCollection.items.some((item) => item.document.id === result.document.id);
                    return (
                      <div key={result.document.id} className="bookshelf-collection-result">
                        <span>
                          <strong>{result.document.title ?? result.document.url}</strong>
                          <small>{result.document.source_domain}</small>
                        </span>
                        <button
                          type="button"
                          onClick={() => addResultToActiveCollection(result)}
                          disabled={alreadyAdded || addingDocumentId === result.document.id}
                        >
                          {alreadyAdded ? 'Added' : 'Add'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </form>
          )}

          {addingLink && (
            <form className="bookshelf-add-link bookshelf-add-link-compact" onSubmit={submitLink}>
              <input value={linkUrl} onChange={(event) => setLinkUrl(event.target.value)} placeholder="Paste a URL..." />
              <input value={linkTitle} onChange={(event) => setLinkTitle(event.target.value)} placeholder="Title override" />
              <Button type="submit" disabled={saving || !linkUrl.trim()} borderRadius="0">Save</Button>
            </form>
          )}

          {error && <div className="error">{error}</div>}
          <BookshelfTable
            rows={tableRows}
            selectedDocumentIds={selectedDocumentIds}
            selectionEnabled
            onRowClick={selectBookshelfRow}
            onOpenDetail={openBookshelfDrawer}
            onRemoveFromCurrent={removeDocumentFromActiveView}
          />
          {tableRows.length === 0 && (
            <div className="bookshelf-empty-cta">
              <h3>No rows yet</h3>
              <button className="bookshelf-discover-cta" type="button" onClick={activeCollection ? () => setAddingCollectionDocs(true) : onDiscover}>
                <Search size={15} />
                {discoverLabel}
              </button>
            </div>
          )}
        </div>
      </div>
      {drawerEntry && (
        <BookshelfDetailDrawer
          entry={drawerEntry}
          detail={drawerDetail}
          collections={collections}
          loading={drawerLoading}
          error={drawerError}
          drawerRef={drawerRef}
          onEntryChange={(entry) => {
            setDrawerEntry(entry);
            setEntries((current) => current.map((item) => (item.document.id === entry.document.id ? entry : item)));
            setCollections((current) =>
              current.map((collection) => ({
                ...collection,
                items: collection.items.map((item) => (item.document.id === entry.document.id ? entry : item)),
              })),
            );
          }}
          onClose={() => setDrawerEntry(null)}
        />
      )}
    </section>
  );
}

function filterBookshelfEntries(entries: BookshelfEntry[], collections: BookshelfCollection[], activeView: BookshelfViewKey): BookshelfEntry[] {
  let scoped = entries;
  if (activeView === 'favorites') {
    scoped = entries.filter((entry) => entry.favorited);
  } else if (activeView === 'unread') {
    scoped = entries.filter((entry) => entry.status === 'saved');
  } else if (activeView === 'reading-log') {
    scoped = entries.filter((entry) => entry.status === 'read');
  } else if (activeView.startsWith('collection:')) {
    const collectionId = Number(activeView.slice('collection:'.length));
    scoped = collections.find((collection) => collection.id === collectionId)?.items ?? [];
  }
  return scoped;
}

function notePreview(entry: BookshelfEntry): string {
  const text = (entry.note || entry.intent_note || '').trim();
  if (!text) return 'No note';
  return text.split('\n')[0];
}

function mergeBookshelfEntryUpdates(current: BookshelfEntry[], updates: BookshelfEntry[]): BookshelfEntry[] {
  const byDocumentId = new Map(updates.map((entry) => [entry.document.id, entry]));
  return current.map((entry) => byDocumentId.get(entry.document.id) ?? entry);
}

function BookshelfDetailDrawer({
  entry,
  detail,
  collections,
  loading,
  error,
  drawerRef,
  onEntryChange,
  onClose,
}: {
  entry: BookshelfEntry;
  detail: DocumentDetail | null;
  collections: BookshelfCollection[];
  loading: boolean;
  error: string | null;
  drawerRef: React.RefObject<HTMLDivElement | null>;
  onEntryChange: (entry: BookshelfEntry) => void;
  onClose: () => void;
}) {
  const document = detail ?? entry.document;
  const containingCollections = collections.filter((collection) =>
    collection.items.some((item) => item.document.id === entry.document.id),
  );
  const [noteDraft, setNoteDraft] = useState(entry.note ?? entry.intent_note ?? '');
  const [tagDraftOpen, setTagDraftOpen] = useState(false);
  const [tagDraft, setTagDraft] = useState('');
  const [savingNote, setSavingNote] = useState(false);
  const [savingTags, setSavingTags] = useState(false);
  const [referenceLimit, setReferenceLimit] = useState(5);
  const [referencedByLimit, setReferencedByLimit] = useState(5);

  useEffect(() => {
    setNoteDraft(entry.note ?? entry.intent_note ?? '');
    setTagDraft('');
    setTagDraftOpen(false);
  }, [entry.document.id]);

  useEffect(() => {
    const nextNote = noteDraft.trim();
    const currentNote = (entry.note ?? entry.intent_note ?? '').trim();
    if (nextNote === currentNote) return;
    const timeout = window.setTimeout(() => {
      setSavingNote(true);
      updateDocumentBookshelf(entry.document.id, { note: noteDraft })
        .then(onEntryChange)
        .finally(() => setSavingNote(false));
    }, 450);
    return () => window.clearTimeout(timeout);
  }, [entry.document.id, entry.note, entry.intent_note, noteDraft, onEntryChange]);

  async function addTag(event: FormEvent) {
    event.preventDefault();
    const tag = tagDraft.trim();
    if (!tag || entry.tags.includes(tag)) {
      setTagDraft('');
      setTagDraftOpen(false);
      return;
    }
    setSavingTags(true);
    try {
      const updated = await updateDocumentBookshelf(entry.document.id, { tags: [...entry.tags, tag] });
      onEntryChange(updated);
      setTagDraft('');
      setTagDraftOpen(false);
    } finally {
      setSavingTags(false);
    }
  }

  return (
    <aside ref={drawerRef} className="bookshelf-detail-drawer" aria-label="Bookshelf document details">
      <div className="bookshelf-detail-header">
        <div>
          <span>{document.source_domain}</span>
          <h3>
            {document.title ?? document.url}
            <a href={document.url} aria-label="Open document">
              <ArrowUpRight size={15} />
            </a>
          </h3>
        </div>
        <button type="button" onClick={onClose} aria-label="Close details">×</button>
      </div>

      <div className="bookshelf-detail-actions">
        {containingCollections.map((collection) => (
          <span key={collection.id}>{collection.name}</span>
        ))}
        {entry.favorited && <span>favorite</span>}
      </div>

      {loading && <div className="bookshelf-detail-muted">Loading details...</div>}
      {error && <div className="error">{error}</div>}

      <section className="bookshelf-detail-section">
        <h4>Summary</h4>
        <p>{document.summary || 'No summary yet.'}</p>
      </section>

      <section className="bookshelf-detail-section">
        <div className="bookshelf-detail-section-heading">
          <h4>Notes</h4>
          {savingNote && <span>Saving</span>}
        </div>
        <textarea
          className="bookshelf-detail-note-input"
          value={noteDraft}
          onChange={(event) => setNoteDraft(event.target.value)}
          placeholder="Add a note..."
        />
      </section>

      <section className="bookshelf-detail-section">
        <div className="bookshelf-detail-section-heading">
          <h4>Tags</h4>
          <button type="button" className="bookshelf-detail-add-tag" onClick={() => setTagDraftOpen((value) => !value)}>
            Add tag
          </button>
        </div>
        {tagDraftOpen && (
          <form className="bookshelf-detail-tag-form" onSubmit={addTag}>
            <input
              value={tagDraft}
              onChange={(event) => setTagDraft(event.target.value)}
              placeholder="New tag"
              disabled={savingTags}
              autoFocus
            />
          </form>
        )}
        {entry.tags.length > 0 || document.topics.length > 0 ? (
          <div className="bookshelf-detail-tags">
            {[...entry.tags, ...document.topics.filter((topic) => !entry.tags.includes(topic))].map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </div>
        ) : (
          <p>No tags yet.</p>
        )}
      </section>

      <div className="bookshelf-detail-reference-grid">
        <section className="bookshelf-detail-section">
          <h4>References</h4>
          {detail?.outgoing_links.length ? (
            <>
              <div className="bookshelf-detail-link-list">
                {detail.outgoing_links.slice(0, referenceLimit).map((link, index) => (
                  <a key={`${link.target_url}-${index}`} href={link.target_url}>
                    <strong>{link.anchor_text || link.target_domain || link.target_url}</strong>
                    <small>{link.target_domain || link.target_url}</small>
                    {link.context && <span>{link.context}</span>}
                  </a>
                ))}
              </div>
              {referenceLimit < detail.outgoing_links.length && (
                <button className="bookshelf-detail-more" type="button" onClick={() => setReferenceLimit((value) => value + 5)}>
                  More references
                </button>
              )}
            </>
          ) : (
            <p>No outgoing references indexed.</p>
          )}
        </section>

        <section className="bookshelf-detail-section">
          <h4>Referenced By</h4>
          {detail?.incoming_links.length ? (
            <>
              <div className="bookshelf-detail-link-list">
                {detail.incoming_links.slice(0, referencedByLimit).map((link, index) => (
                  <button key={`${link.source_document_id}-${index}`} type="button">
                    <strong>{link.anchor_text || `Document ${link.source_document_id}`}</strong>
                    <small>{link.target_url}</small>
                  </button>
                ))}
              </div>
              {referencedByLimit < detail.incoming_links.length && (
                <button className="bookshelf-detail-more" type="button" onClick={() => setReferencedByLimit((value) => value + 5)}>
                  More referenced by
                </button>
              )}
            </>
          ) : (
            <p>No incoming references indexed.</p>
          )}
        </section>
      </div>
    </aside>
  );
}

function entryDate(entry: BookshelfEntry): string {
  const value = entry.read_at ?? entry.first_seen_at ?? entry.favorited_at;
  if (!value) return '';
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function defaultDirectorySortDirection(sort: DirectorySourceSort): SortDirection {
  return sort === 'source' ? 'asc' : 'desc';
}

function directorySortLabel(label: string, sort: DirectorySourceSort, activeSort: DirectorySourceSort, direction: SortDirection): string {
  if (sort !== activeSort) return label;
  return `${label} ${direction === 'asc' ? '↑' : '↓'}`;
}

function BookshelfTable({
  rows,
  selectedDocumentIds,
  selectionEnabled,
  onRowClick,
  onOpenDetail,
  onRemoveFromCurrent,
}: {
  rows: BookshelfEntry[];
  selectedDocumentIds: Set<number>;
  selectionEnabled: boolean;
  onRowClick: (entry: BookshelfEntry, event: MouseEvent<HTMLDivElement>, forceSelect?: boolean) => void;
  onOpenDetail: (entry: BookshelfEntry) => void;
  onRemoveFromCurrent: (documentId: number) => void;
}) {
  const [openActionDocumentId, setOpenActionDocumentId] = useState<number | null>(null);
  const clickTimerRef = useRef<number | null>(null);

  function clearClickTimer() {
    if (clickTimerRef.current !== null) {
      window.clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
  }

  return (
    <div className="bookshelf-table" role="table" aria-label="Bookshelf documents">
      <div className="bookshelf-table-row bookshelf-table-head" role="row">
        <span>Title</span>
        <span>Tags</span>
        <span>Notes</span>
        <span>Date</span>
        <span />
        <span />
      </div>
      {rows.map((entry) => {
        const document = entry.document;
        const isSelected = selectedDocumentIds.has(document.id);
        return (
          <div
            key={document.id}
            className={isSelected ? 'bookshelf-table-row bookshelf-table-row-selected' : 'bookshelf-table-row'}
            role="row"
            aria-selected={selectionEnabled ? isSelected : undefined}
            onClick={(event) => {
              const target = event.target as HTMLElement;
              if (target.closest('a, button, select')) return;
              if (event.metaKey || event.ctrlKey || event.shiftKey) {
                onRowClick(entry, event);
                return;
              }
              clearClickTimer();
              clickTimerRef.current = window.setTimeout(() => {
                onOpenDetail(entry);
                clickTimerRef.current = null;
              }, 180);
            }}
            onMouseDown={(event) => {
              if (event.detail > 1) event.preventDefault();
            }}
            onDoubleClick={(event) => {
              event.preventDefault();
              clearClickTimer();
              onRowClick(entry, event, true);
            }}
          >
            <span className="bookshelf-table-title">
              <strong>
                {document.title ?? document.url}
                <a href={document.url} aria-label="Open document" onClick={(event) => event.stopPropagation()}>
                  <ArrowUpRight size={14} />
                </a>
              </strong>
              <small>{document.source_domain}</small>
            </span>
            <span className="bookshelf-table-tags">{entry.tags.slice(0, 3).join(', ')}</span>
            <span className={entry.note || entry.intent_note ? 'bookshelf-note-preview' : 'bookshelf-note-empty'}>
              {notePreview(entry)}
            </span>
            <span>{entryDate(entry)}</span>
            <span className={entry.favorited ? 'bookshelf-fav bookshelf-fav-on' : 'bookshelf-fav'}>
              {entry.favorited ? '♥' : '♡'}
            </span>
            <span className="bookshelf-row-actions">
              <button
                type="button"
                aria-label="Document actions"
                aria-expanded={openActionDocumentId === document.id}
                onClick={(event) => {
                  event.stopPropagation();
                  setOpenActionDocumentId((current) => (current === document.id ? null : document.id));
                }}
              >
                <MoreVertical size={14} />
              </button>
              {openActionDocumentId === document.id && (
                <div className="bookshelf-row-menu">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onRemoveFromCurrent(document.id);
                      setOpenActionDocumentId(null);
                    }}
                  >
                    <Trash2 size={13} />
                    Remove
                  </button>
                </div>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function DirectoryView({
  target,
  onOpenProfile,
  onDirectoryRoot,
}: {
  target: ProfileTarget;
  onOpenProfile: (sourceId: number, domain: string) => void;
  onDirectoryRoot: () => void;
}) {
  const [query, setQuery] = useState(target?.domain ?? '');
  const [selectedSource, setSelectedSource] = useState<AdminSource | null>(null);
  const [directoryPage, setDirectoryPage] = useState<Page<DirectorySource>>(emptyPage);
  const [directorySort, setDirectorySort] = useState<DirectorySourceSort>('inbound');
  const [directorySortDirection, setDirectorySortDirection] = useState<SortDirection>('desc');
  const [documentsPage, setDocumentsPage] = useState<Page<Document>>(emptyPage);
  const [profileAnalysis, setProfileAnalysis] = useState<SourceProfileAnalysis | null>(null);
  const [selected, setSelected] = useState<ProfileTarget>(target);
  const [documentPageState, setDocumentPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [directoryPageState, setDirectoryPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const didLoadDirectoryRef = useRef(false);

  useEffect(() => {
    setSelected(target);
    if (target) setQuery(target.domain);
  }, [target?.sourceId, target?.domain]);

  async function refresh(
    nextQuery = query,
    nextSelected = selected,
    nextPage = documentPageState,
    nextDirectoryPage = directoryPageState,
    nextSort = directorySort,
    nextSortDirection = directorySortDirection,
  ) {
    const firstLoad = !didLoadDirectoryRef.current;
    setLoading(firstLoad);
    setRefreshing(!firstLoad);
    setError(null);
    try {
      const normalizedQuery = nextQuery.trim();
      if (!nextSelected) {
        const tablePage = await getDirectorySources({
          status: 'indexed',
          q: normalizedQuery,
          sort: nextSort,
          direction: nextSortDirection,
          ...nextDirectoryPage,
        });
        setDirectoryPage(tablePage);
        setSelectedSource(null);
        setSelected(null);
        setDocumentsPage(emptyPage<Document>());
        setProfileAnalysis(null);
        return;
      }
      const sources = await getAdminSources({ status: 'indexed', q: normalizedQuery, limit: 25 });
      const source =
        (nextSelected?.sourceId ? sources.items.find((item) => item.id === nextSelected.sourceId) : null) ??
        sources.items.find((item) => item.canonical_domain === normalizedQuery.toLowerCase()) ??
        (normalizedQuery ? sources.items[0] : null) ??
        null;
      const nextProfile = source ? { sourceId: source.id, domain: source.canonical_domain } : null;
      setSelectedSource(source);
      setSelected(nextProfile);
      if (source && !nextSelected) setQuery(source.canonical_domain);
      const [documents, analysis] = nextProfile
        ? await Promise.all([
            getAdminDocuments({ ...nextPage, sourceId: nextProfile.sourceId, documentType: 'essay' }),
            getSourceProfileAnalysis(nextProfile.sourceId).catch(() => null),
          ])
        : [emptyPage<Document>(), null];
      setDocumentsPage(documents);
      setProfileAnalysis(analysis);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Directory failed');
    } finally {
      didLoadDirectoryRef.current = true;
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    const nextPage = { limit: 50, offset: 0 };
    setDocumentPageState(nextPage);
    const nextDirectoryPage = { limit: directoryPageState.limit, offset: 0 };
    setDirectoryPageState(nextDirectoryPage);
    refresh(target?.domain ?? '', target, nextPage, nextDirectoryPage);
  }, [target?.sourceId, target?.domain]);

  useEffect(() => {
    if (selected) return;
    const timeout = window.setTimeout(() => {
      const nextDirectoryPage = { limit: directoryPageState.limit, offset: 0 };
      setDirectoryPageState(nextDirectoryPage);
      refresh(query, null, documentPageState, nextDirectoryPage);
    }, 160);
    return () => window.clearTimeout(timeout);
  }, [query, selected?.domain]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextPage = { limit: documentPageState.limit, offset: 0 };
    const nextDirectoryPage = { limit: directoryPageState.limit, offset: 0 };
    setDocumentPageState(nextPage);
    setDirectoryPageState(nextDirectoryPage);
    refresh(query, null, nextPage, nextDirectoryPage);
  }

  function updateQuery(value: string) {
    setQuery(value);
  }

  function openSourceProfile(source: Pick<AdminSource, 'id' | 'canonical_domain'>) {
    const nextPage = { limit: documentPageState.limit, offset: 0 };
    const nextProfile = { sourceId: source.id, domain: source.canonical_domain };
    setQuery(source.canonical_domain);
    setSelected(nextProfile);
    setDocumentPageState(nextPage);
    refresh(source.canonical_domain, nextProfile, nextPage);
    onOpenProfile(source.id, source.canonical_domain);
  }

  function pageProfileDocuments(nextPage: PageState) {
    setDocumentPageState(nextPage);
    refresh(selected?.domain ?? query, selected, nextPage);
  }

  function updateDirectorySort(nextSort: DirectorySourceSort) {
    const nextPage = { limit: directoryPageState.limit, offset: 0 };
    const nextDirection: SortDirection = nextSort === directorySort ? (directorySortDirection === 'desc' ? 'asc' : 'desc') : defaultDirectorySortDirection(nextSort);
    setDirectorySort(nextSort);
    setDirectorySortDirection(nextDirection);
    setDirectoryPageState(nextPage);
    refresh(query, selected, documentPageState, nextPage, nextSort, nextDirection);
  }

  function pageDirectory(nextPage: PageState) {
    setDirectoryPageState(nextPage);
    refresh(query, selected, documentPageState, nextPage);
  }

  function selectDirectorySource(source: DirectorySource) {
    openSourceProfile({
      id: source.id,
      canonical_domain: source.canonical_domain,
    });
  }

  function showDirectoryRoot() {
    setSelected(null);
    setSelectedSource(null);
    setProfileAnalysis(null);
    setDocumentsPage(emptyPage<Document>());
    setQuery('');
    onDirectoryRoot();
    if (directoryPage.items.length === 0) {
      refresh('', null, documentPageState, { ...directoryPageState, offset: 0 });
    }
  }

  return (
    <Box as="section" className="directory-view">
      {selected ? (
        <button className="directory-back directory-back-top" type="button" onClick={showDirectoryRoot} aria-label="Back to sources">
          ←
        </button>
      ) : (
        <CorpusSearchForm
          className="search-box"
          value={query}
          onChange={updateQuery}
          onSubmit={submit}
          placeholder={loading ? 'Loading...' : 'Filter sources...'}
          disabled={loading}
        />
      )}

      {error && <div className="error">{error}</div>}
      {loading && <div className="empty-state">Loading...</div>}

      {!loading && !selected && (
        <div className="directory-table-panel">
          <div className={refreshing ? 'directory-table directory-table-refreshing' : 'directory-table'}>
            <div className="directory-table-row directory-table-head" role="row">
              <button type="button" onClick={() => updateDirectorySort('source')}>{directorySortLabel('Source', 'source', directorySort, directorySortDirection)}</button>
              <button type="button" onClick={() => updateDirectorySort('inbound')}>{directorySortLabel('Links', 'inbound', directorySort, directorySortDirection)}</button>
              <button type="button" onClick={() => updateDirectorySort('essays')}>{directorySortLabel('Corpus', 'essays', directorySort, directorySortDirection)}</button>
            </div>
            {directoryPage.items.map((source) => (
              <div key={source.id} className="directory-table-row" role="button" tabIndex={0} onClick={() => selectDirectorySource(source)} onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') selectDirectorySource(source);
              }}>
                <span className="directory-source-cell">
                  <strong>{source.canonical_domain}</strong>
                  <a href={source.url} aria-label="Open source" onClick={(event) => event.stopPropagation()}>
                    <ArrowUpRight size={15} />
                  </a>
                </span>
                <span className="directory-stat-pair">
                  <strong>{source.inbound_count}</strong>
                  <small>{source.outbound_count} out</small>
                </span>
                <span className="directory-stat-pair">
                  <strong>{source.essay_count}</strong>
                  <small>{source.document_count} docs</small>
                </span>
              </div>
            ))}
          </div>
          <ProfilePagination page={directoryPage} onChange={pageDirectory} />
        </div>
      )}

      {!loading && selected && (
        <div className="profile-panel directory-profile-page">
          <div className="profile-heading">
            <div>
              <h3>{profileAnalysis?.display_name || selectedSource?.canonical_domain || selected.domain}</h3>
              {profileAnalysis?.display_name && profileAnalysis.display_name !== selected.domain && <p>{selectedSource?.canonical_domain ?? selected.domain}</p>}
            </div>
            <a href={selectedSource?.url ?? `https://${selected.domain}`}>
              <ArrowUpRight size={16} />
            </a>
          </div>
          <ProfileAnalysisCard analysis={profileAnalysis} />
          <div className="profile-documents">
            {documentsPage.items.map((document) => (
              <DocumentCard
                key={document.id}
                document={document}
                reason={document.summary ? 'From this profile.' : 'Indexed essay from this profile.'}
                onOpenProfile={onOpenProfile}
                compact
              />
            ))}
          </div>
          <ProfilePagination page={documentsPage} onChange={pageProfileDocuments} />
        </div>
      )}
    </Box>
  );
}

function AdminView() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [sourcesPage, setSourcesPage] = useState<Page<AdminSource>>(emptyPage);
  const [documentsPage, setDocumentsPage] = useState<Page<Document>>(emptyPage);
  const [jobsPage, setJobsPage] = useState<Page<AdminCrawlJob>>(emptyPage);
  const [runsPage, setRunsPage] = useState<Page<AdminIndexRun>>(emptyPage);
  const [status, setStatus] = useState('indexed');
  const [query, setQuery] = useState('');
  const [documentSourceId, setDocumentSourceId] = useState<number | undefined>(undefined);
  const [documentType, setDocumentType] = useState('all');
  const [documentCrawlJobId, setDocumentCrawlJobId] = useState<number | undefined>(undefined);
  const [documentIndexRunId, setDocumentIndexRunId] = useState<number | undefined>(undefined);
  const [jobStatus, setJobStatus] = useState('all');
  const [jobSourceId, setJobSourceId] = useState<number | undefined>(undefined);
  const [jobRunId, setJobRunId] = useState<number | undefined>(undefined);
  const [runStatus, setRunStatus] = useState('all');
  const [sourcePageState, setSourcePageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [documentPageState, setDocumentPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [jobPageState, setJobPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [runPageState, setRunPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [activeTable, setActiveTable] = useState<'sources' | 'documents' | 'jobs' | 'runs'>('sources');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refreshId = useRef(0);

  async function refresh(
    nextStatus = status,
    nextQuery = query,
    nextDocumentSourceId = documentSourceId,
    nextDocumentType = documentType,
    nextSourcePage = sourcePageState,
    nextDocumentPage = documentPageState,
    nextJobPage = jobPageState,
    nextRunPage = runPageState,
    nextJobStatus = jobStatus,
    nextJobSourceId = jobSourceId,
    nextJobRunId = jobRunId,
    nextRunStatus = runStatus,
    nextDocumentCrawlJobId = documentCrawlJobId,
    nextDocumentIndexRunId = documentIndexRunId,
  ) {
    const requestId = refreshId.current + 1;
    refreshId.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const [overviewData, sourceData, documentData, jobData, runData] = await Promise.all([
        getAdminOverview(),
        getAdminSources({ status: nextStatus, q: nextQuery.trim(), ...nextSourcePage }),
        getAdminDocuments({
          ...nextDocumentPage,
          sourceId: nextDocumentSourceId,
          documentType: nextDocumentType,
          crawlJobId: nextDocumentCrawlJobId,
          indexRunId: nextDocumentIndexRunId,
        }),
        getAdminCrawlJobs({ ...nextJobPage, status: nextJobStatus, sourceId: nextJobSourceId, indexRunId: nextJobRunId }),
        getAdminIndexRuns({ ...nextRunPage, status: nextRunStatus }),
      ]);
      if (refreshId.current === requestId) {
        setOverview(overviewData);
        setSourcesPage(sourceData);
        setDocumentsPage(documentData);
        setJobsPage(jobData);
        setRunsPage(runData);
        setError(null);
      }
    } catch (err) {
      if (refreshId.current === requestId) {
        setError(err instanceof Error ? err.message : 'Admin data failed');
      }
    } finally {
      if (refreshId.current === requestId) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function updateStatus(nextStatus: string) {
    const nextPage = { ...sourcePageState, offset: 0 };
    setStatus(nextStatus);
    setSourcePageState(nextPage);
    refresh(nextStatus, query, documentSourceId, documentType, nextPage);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const nextPage = { ...sourcePageState, offset: 0 };
    setSourcePageState(nextPage);
    refresh(status, query, documentSourceId, documentType, nextPage);
  }

  function updateDocumentSource(value: string) {
    const nextSourceId = value ? Number(value) : undefined;
    const nextPage = { ...documentPageState, offset: 0 };
    setDocumentSourceId(nextSourceId);
    setDocumentCrawlJobId(undefined);
    setDocumentIndexRunId(undefined);
    setDocumentPageState(nextPage);
    refresh(status, query, nextSourceId, documentType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, undefined, undefined);
  }

  function updateDocumentType(nextType: string) {
    const nextPage = { ...documentPageState, offset: 0 };
    setDocumentType(nextType);
    setDocumentPageState(nextPage);
    refresh(status, query, documentSourceId, nextType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, documentCrawlJobId, documentIndexRunId);
  }

  function pageSources(nextPage: PageState) {
    setSourcePageState(nextPage);
    refresh(status, query, documentSourceId, documentType, nextPage);
  }

  function pageDocuments(nextPage: PageState) {
    setDocumentPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, nextPage);
  }

  function pageJobs(nextPage: PageState) {
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage);
  }

  function pageRuns(nextPage: PageState) {
    setRunPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, jobPageState, nextPage);
  }

  function updateJobStatus(nextStatus: string) {
    const nextPage = { ...jobPageState, offset: 0 };
    setJobStatus(nextStatus);
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage, runPageState, nextStatus);
  }

  function updateJobSource(value: string) {
    const nextSourceId = value ? Number(value) : undefined;
    const nextPage = { ...jobPageState, offset: 0 };
    setJobSourceId(nextSourceId);
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage, runPageState, jobStatus, nextSourceId);
  }

  function updateJobRun(value: string) {
    const nextRunId = value ? Number(value) : undefined;
    const nextPage = { ...jobPageState, offset: 0 };
    setJobRunId(nextRunId);
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage, runPageState, jobStatus, jobSourceId, nextRunId);
  }

  function updateRunStatus(nextStatus: string) {
    const nextPage = { ...runPageState, offset: 0 };
    setRunStatus(nextStatus);
    setRunPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, jobPageState, nextPage, jobStatus, jobSourceId, jobRunId, nextStatus);
  }

  function showDocumentsForJob(job: AdminCrawlJob) {
    const nextPage = { ...documentPageState, offset: 0 };
    setActiveTable('documents');
    setDocumentSourceId(job.source_id);
    setDocumentCrawlJobId(job.id);
    setDocumentIndexRunId(undefined);
    setDocumentPageState(nextPage);
    refresh(status, query, job.source_id, documentType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, job.id, undefined);
  }

  function showJobsForRun(run: AdminIndexRun) {
    const nextPage = { ...jobPageState, offset: 0 };
    setActiveTable('jobs');
    setJobRunId(run.id);
    setJobPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, documentPageState, nextPage, runPageState, jobStatus, jobSourceId, run.id, runStatus);
  }

  function showDocumentsForRun(run: AdminIndexRun) {
    const nextPage = { ...documentPageState, offset: 0 };
    setActiveTable('documents');
    setDocumentSourceId(undefined);
    setDocumentCrawlJobId(undefined);
    setDocumentIndexRunId(run.id);
    setDocumentPageState(nextPage);
    refresh(status, query, undefined, documentType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, undefined, run.id);
  }

  function clearDocumentScope() {
    const nextPage = { ...documentPageState, offset: 0 };
    setDocumentCrawlJobId(undefined);
    setDocumentIndexRunId(undefined);
    setDocumentPageState(nextPage);
    refresh(status, query, documentSourceId, documentType, sourcePageState, nextPage, jobPageState, runPageState, jobStatus, jobSourceId, jobRunId, runStatus, undefined, undefined);
  }

  const crawledSources = overview?.source_statuses.indexed ?? 0;
  const activeSources = overview?.source_statuses.crawling ?? 0;

  return (
    <section>
      <Flex className="section-header">
        <div>
          <Heading as="h2" fontSize="2xl" fontWeight="650">Admin</Heading>
          <Text color="iris.500" mt="1">Read-only database view for ingestion, crawl runs, sources, and documents.</Text>
        </div>
        <Button type="button" onClick={() => refresh()} variant="outline" borderRadius="0">
          Refresh
        </Button>
      </Flex>

      {error && <div className="error">{error}</div>}

      <SimpleGrid className="metric-grid" columns={{ base: 2, md: 3, xl: 6 }} gap="2.5">
        <Metric label="sources crawled" value={crawledSources} />
        <Metric label="active crawls" value={activeSources} />
        <Metric label="documents" value={overview?.totals.documents ?? 0} />
        <Metric label="essays" value={overview?.totals.essay_documents ?? 0} />
        <Metric label="links" value={overview?.totals.links ?? 0} />
        <Metric label="resolved links" value={overview?.totals.resolved_links ?? 0} />
      </SimpleGrid>

      <div className="admin-controls">
        <div className="tab-strip">
          {(['sources', 'documents', 'jobs', 'runs'] as const).map((table) => (
            <button
              key={table}
              type="button"
              className={activeTable === table ? 'active' : ''}
              onClick={() => setActiveTable(table)}
            >
              {table}
            </button>
          ))}
        </div>
        {activeTable === 'sources' && (
          <form className="admin-filter" onSubmit={submitSearch}>
            <select value={status} onChange={(event) => updateStatus(event.target.value)}>
              <option value="indexed">crawled/indexed</option>
              <option value="queued">queued</option>
              <option value="ignored">ignored</option>
              <option value="failed">failed</option>
              <option value="crawling">crawling</option>
              <option value="all">all</option>
            </select>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="filter domain" />
            <button type="submit">Apply</button>
          </form>
        )}
        {activeTable === 'documents' && (
          <div className="admin-document-controls">
            <div className="admin-filter">
              <select value={documentSourceId ?? ''} onChange={(event) => updateDocumentSource(event.target.value)}>
                <option value="">all sources, newest first</option>
                {sourcesPage.items
                  .filter((source) => source.document_count > 0)
                  .map((source) => (
                    <option key={source.id} value={source.id}>
                      {source.canonical_domain} ({source.document_count})
                    </option>
                  ))}
              </select>
              <select value={documentType} onChange={(event) => updateDocumentType(event.target.value)}>
                <option value="all">all document types</option>
                <option value="essay">essays</option>
                <option value="collection">collections</option>
              </select>
            </div>
            {(documentCrawlJobId || documentIndexRunId) && (
              <div className="admin-scope-banner">
                <span>
                  Showing documents inferred from {documentCrawlJobId ? `crawl job ${documentCrawlJobId}` : `index run ${documentIndexRunId}`}.
                </span>
                <button type="button" onClick={clearDocumentScope}>Clear scope</button>
              </div>
            )}
          </div>
        )}
        {activeTable === 'jobs' && (
          <div className="admin-filter admin-filter-wide">
            <select value={jobStatus} onChange={(event) => updateJobStatus(event.target.value)}>
              <option value="all">all job statuses</option>
              <option value="succeeded">succeeded</option>
              <option value="skipped">skipped</option>
              <option value="failed">failed</option>
              <option value="running">running</option>
            </select>
            <select value={jobSourceId ?? ''} onChange={(event) => updateJobSource(event.target.value)}>
              <option value="">all sources</option>
              {sourcesPage.items.map((source) => (
                <option key={source.id} value={source.id}>{source.canonical_domain}</option>
              ))}
            </select>
            <input
              value={jobRunId ?? ''}
              onChange={(event) => updateJobRun(event.target.value)}
              placeholder="index run id"
              inputMode="numeric"
            />
          </div>
        )}
        {activeTable === 'runs' && (
          <div className="admin-filter">
            <select value={runStatus} onChange={(event) => updateRunStatus(event.target.value)}>
              <option value="all">all run statuses</option>
              <option value="succeeded">succeeded</option>
              <option value="stopped">stopped</option>
              <option value="failed">failed</option>
              <option value="running">running</option>
            </select>
          </div>
        )}
      </div>

      {loading ? <div className="empty-state">Loading admin data...</div> : null}
      {!loading && activeTable === 'sources' && (
        <>
          <Pagination page={sourcesPage} onChange={pageSources} />
          <AdminSourcesTable sources={sourcesPage.items} />
          <Pagination page={sourcesPage} onChange={pageSources} />
        </>
      )}
      {!loading && activeTable === 'documents' && (
        <>
          <Pagination page={documentsPage} onChange={pageDocuments} />
          <AdminDocumentsTable
            documents={documentsPage.items}
            page={documentsPage}
            sourceName={sourcesPage.items.find((source) => source.id === documentSourceId)?.canonical_domain}
            crawlJobId={documentCrawlJobId}
            indexRunId={documentIndexRunId}
          />
          <Pagination page={documentsPage} onChange={pageDocuments} />
        </>
      )}
      {!loading && activeTable === 'jobs' && (
        <>
          <Pagination page={jobsPage} onChange={pageJobs} />
          <AdminJobsTable jobs={jobsPage.items} onShowDocuments={showDocumentsForJob} />
          <Pagination page={jobsPage} onChange={pageJobs} />
        </>
      )}
      {!loading && activeTable === 'runs' && (
        <>
          <Pagination page={runsPage} onChange={pageRuns} />
          <AdminRunsTable runs={runsPage.items} onShowJobs={showJobsForRun} onShowDocuments={showDocumentsForRun} />
          <Pagination page={runsPage} onChange={pageRuns} />
        </>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Box className="metric">
      <Text as="span">{label}</Text>
      <Text as="strong">{value.toLocaleString()}</Text>
    </Box>
  );
}

function AdminSourcesTable({ sources }: { sources: AdminSource[] }) {
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Domain</th>
            <th>Status</th>
            <th>Stored</th>
            <th>Essays</th>
            <th>Latest Crawl</th>
            <th>Why It Stopped</th>
            <th>Checked</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.id}>
              <td>
                <a href={source.url}>{source.canonical_domain}</a>
                {source.description && <small>{source.description}</small>}
              </td>
              <td><StatusPill value={source.status} /></td>
              <td>{source.document_count}</td>
              <td>{source.essay_count}</td>
              <td>{source.latest_job ? <JobLabel job={source.latest_job} /> : 'none'}</td>
              <td>{source.latest_job?.outcome ?? '-'}</td>
              <td>{formatDate(source.last_checked_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {sources.length === 0 && <div className="empty-state">No sources match this filter.</div>}
    </div>
  );
}

function AdminDocumentsTable({
  documents,
  page,
  sourceName,
  crawlJobId,
  indexRunId,
}: {
  documents: Document[];
  page: Page<Document>;
  sourceName?: string;
  crawlJobId?: number;
  indexRunId?: number;
}) {
  const scope = crawlJobId ? ` for crawl job ${crawlJobId}` : indexRunId ? ` for index run ${indexRunId}` : '';
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.items.length, page.total);
  return (
    <>
      <p className="admin-note">
        Showing {start}-{end} of {page.total} documents
        {sourceName ? ` from ${sourceName}` : ' across all sources'}{scope}.
      </p>
      <div className="admin-table-wrap">
        <table className="admin-table">
        <thead>
          <tr>
            <th>Document</th>
            <th>Source</th>
            <th>Type</th>
            <th>Published</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id}>
              <td>
                <div className="admin-document-cell">
                  <a href={document.url}>{document.title || document.url}</a>
                  <small className="admin-document-url">{document.url}</small>
                  {document.summary && <p>{document.summary}</p>}
                  {document.topics.length > 0 && (
                    <div className="admin-document-topics">
                      {document.topics.slice(0, 8).map((topic) => (
                        <span key={topic}>{topic}</span>
                      ))}
                    </div>
                  )}
                </div>
              </td>
              <td>{document.source_domain}</td>
              <td>{document.document_type}</td>
              <td>{formatDate(document.published_at)}</td>
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </>
  );
}

function AdminJobsTable({ jobs, onShowDocuments }: { jobs: AdminCrawlJob[]; onShowDocuments: (job: AdminCrawlJob) => void }) {
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Job</th>
            <th>Source</th>
            <th>Status</th>
            <th>Why It Stopped</th>
            <th>Fetched</th>
            <th>Docs</th>
            <th>Links</th>
            <th>Discovered</th>
            <th>Started</th>
            <th>Inspect</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td><JobLabel job={job} /></td>
              <td>{job.source_domain}</td>
              <td>
                <StatusPill value={job.status} />
                {job.error && <small>{job.error.split('\n')[0]}</small>}
              </td>
              <td>{job.outcome}</td>
              <td>{job.pages_fetched}</td>
              <td>
                {job.current_document_count}
                <small>{job.documents_indexed} essays accepted</small>
              </td>
              <td>{job.links_seen}</td>
              <td>{job.sources_discovered}</td>
              <td>{formatDate(job.started_at)}</td>
              <td>
                <button className="admin-inline-action" type="button" onClick={() => onShowDocuments(job)}>
                  View docs
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobLabel({ job }: { job: { id: number; index_run_id: number | null; pages_fetched?: number; documents_indexed?: number } }) {
  return (
    <span className="job-label">
      crawl job {job.id}
      {job.index_run_id ? <small>index run {job.index_run_id}</small> : <small>manual crawl</small>}
      {typeof job.pages_fetched === 'number' && typeof job.documents_indexed === 'number' && (
        <small>{job.pages_fetched} pages fetched / {job.documents_indexed} essay docs</small>
      )}
    </span>
  );
}

function AdminRunsTable({
  runs,
  onShowJobs,
  onShowDocuments,
}: {
  runs: AdminIndexRun[];
  onShowJobs: (run: AdminIndexRun) => void;
  onShowDocuments: (run: AdminIndexRun) => void;
}) {
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Plan</th>
            <th>Crawled</th>
            <th>Ignored</th>
            <th>Stored</th>
            <th>Errors</th>
            <th>Stop</th>
            <th>Inspect</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>{run.id}<small>{formatDate(run.started_at)}</small></td>
              <td><StatusPill value={run.status} /></td>
              <td>{run.attempted_sources}/{run.planned_sources}</td>
              <td>{run.crawled_sources}</td>
              <td>{run.ignored_sources}</td>
              <td>
                {run.current_document_count}
                <small>{run.documents_indexed} essays accepted</small>
              </td>
              <td>{run.errors}</td>
              <td>{run.stop_reason ?? '-'}</td>
              <td>
                <div className="admin-inline-actions">
                  <button className="admin-inline-action" type="button" onClick={() => onShowJobs(run)}>
                    View jobs
                  </button>
                  <button className="admin-inline-action" type="button" onClick={() => onShowDocuments(run)}>
                    View docs
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatDate(value: string | null | undefined) {
  if (!value) return '-';
  return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function IrisApp({ currentUser, onSignOut }: { currentUser: IrisUser | null; onSignOut: () => void }) {
  const [view, setView] = useState<View>(initialView);
  const [profileTarget, setProfileTarget] = useState<ProfileTarget>(() =>
    typeof window === 'undefined' ? null : profileTargetFromPath(window.location.pathname),
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement | null>(null);
  const applyingPopState = useRef(false);

  useEffect(() => {
    window.localStorage.setItem(VIEW_STORAGE_KEY, view);
    const nextPath =
      view === 'directory' && profileTarget?.domain
        ? `/directory/${encodeURIComponent(profileTarget.domain)}`
        : viewPaths[view];
    if (window.location.pathname !== nextPath) {
      if (applyingPopState.current) {
        window.history.replaceState(null, '', nextPath);
      } else {
        window.history.pushState(null, '', nextPath);
      }
    }
    applyingPopState.current = false;
  }, [view, profileTarget?.domain]);

  useEffect(() => {
    function handlePopState() {
      const nextView = viewFromPath(window.location.pathname) ?? 'search';
      setProfileTarget(profileTargetFromPath(window.location.pathname));
      applyingPopState.current = true;
      setView(nextView);
    }
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  useEffect(() => {
    if (view === 'admin' && !currentUser?.is_admin) {
      setView('search');
    }
  }, [currentUser?.is_admin, view]);

  useEffect(() => {
    if (!settingsOpen) return;
    function closeSettingsOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && settingsRef.current?.contains(target)) return;
      setSettingsOpen(false);
    }
    document.addEventListener('pointerdown', closeSettingsOnOutsideClick);
    return () => document.removeEventListener('pointerdown', closeSettingsOnOutsideClick);
  }, [settingsOpen]);

  function openProfile(sourceId: number, domain: string) {
    setProfileTarget({ sourceId, domain });
    setView('directory');
  }

  function openDirectoryRoot() {
    setProfileTarget(null);
    setView('directory');
  }

  const navItems: Array<{ view: View; label: string; icon: ReactNode; adminOnly?: boolean }> = [
    { view: 'search', label: 'Search', icon: <Search size={15} /> },
    { view: 'bookshelf', label: 'Bookshelf', icon: <BookOpen size={15} /> },
    { view: 'explore', label: 'Explore', icon: <Orbit size={15} /> },
    { view: 'graph', label: 'Graph', icon: <GitFork size={15} /> },
    { view: 'directory', label: 'Directory', icon: <Users size={15} /> },
    { view: 'admin', label: 'Admin', icon: <LayoutDashboard size={15} />, adminOnly: true },
  ];
  const visibleNavItems = navItems.filter((item) => !item.adminOnly || currentUser?.is_admin);

  return (
    <Box as="main" className="app-shell">
      <Box as="aside" className="sidebar">
        <Box className="sidebar-brand">
          <span>iris</span>
        </Box>
        <Stack as="nav" className="sidebar-nav" gap="1">
          {visibleNavItems.map((item) => (
            <Button
              key={item.view}
              type="button"
              onClick={() => {
                if (item.view === 'directory') {
                  openDirectoryRoot();
                } else {
                  setView(item.view);
                }
              }}
              variant="ghost"
              borderRadius="0"
              justifyContent="flex-start"
              data-active={view === item.view ? 'true' : undefined}
              bg="transparent"
              color={view === item.view ? 'iris.900' : 'iris.500'}
              fontSize="14px"
              fontWeight={view === item.view ? '600' : '500'}
              lineHeight="1"
              _hover={{
                bg: 'transparent',
                color: 'iris.900',
              }}
            >
              {item.icon}
              {item.label}
            </Button>
          ))}
        </Stack>
        {currentUser && (
          <div className="sidebar-settings" ref={settingsRef}>
            {settingsOpen && (
              <div className="settings-menu">
                <div className="settings-menu-row settings-menu-muted">
                  <UserCircle size={16} />
                  <span>{currentUser.email || currentUser.display_name}</span>
                </div>
                <div className="settings-menu-divider" />
                <button className="settings-menu-row" type="button" onClick={onSignOut}>
                  <LogOut size={16} />
                  <span>Log out</span>
                </button>
              </div>
            )}
            <button
              className="sidebar-settings-toggle"
              type="button"
              onClick={() => setSettingsOpen((value) => !value)}
              aria-expanded={settingsOpen}
            >
              <Settings size={17} />
              <span>Settings</span>
            </button>
            <div className="sidebar-settings-meta">
              {currentUser.display_name || currentUser.email}
            </div>
          </div>
        )}
      </Box>
      <Box className={view === 'explore' || view === 'graph' ? 'workspace workspace-fullscreen' : view === 'search' ? 'workspace workspace-search' : 'workspace'}>
        {view === 'search' && <SearchView onOpenProfile={openProfile} />}
        {view === 'bookshelf' && <BookshelfView onDiscover={() => setView('search')} />}
        {view === 'directory' && <DirectoryView target={profileTarget} onOpenProfile={openProfile} onDirectoryRoot={openDirectoryRoot} />}
        {view === 'explore' && <EmbeddingExplorer />}
        {view === 'graph' && <GraphExplorer onOpenProfile={openProfile} />}
        {view === 'admin' && currentUser?.is_admin && <AdminView />}
      </Box>
    </Box>
  );
}

export default function App() {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [currentUser, setCurrentUser] = useState<IrisUser | null>(null);
  const [authReady, setAuthReady] = useState(!firebaseEnabled);
  const [authError, setAuthError] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);

  useEffect(() => {
    if (!auth) {
      setAuthTokenProvider(null);
      return;
    }
    getRedirectResult(auth).catch((err) => {
      setAuthError(readAuthError(err, 'Sign-in failed'));
      setSigningIn(false);
    });
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setFirebaseUser(user);
      setCurrentUser(null);
      if (user) setAuthError(null);
      setAuthReady(true);
      setSigningIn(false);
      setAuthTokenProvider(user ? () => user.getIdToken() : null);
    });
    return () => {
      unsubscribe();
      setAuthTokenProvider(null);
    };
  }, []);

  useEffect(() => {
    if (!firebaseEnabled || !firebaseUser) return;
    let cancelled = false;
    getMe()
      .then((user) => {
        if (!cancelled) setCurrentUser(user);
      })
      .catch((err) => {
        if (!cancelled) setAuthError(err instanceof Error ? err.message : 'Could not load user');
      });
    return () => {
      cancelled = true;
    };
  }, [firebaseUser]);

  async function signIn() {
    if (!auth) return;
    setAuthError(null);
    setSigningIn(true);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err) {
      if (shouldUseRedirectSignIn(err)) {
        await signInWithRedirect(auth, googleProvider);
        return;
      }
      setAuthError(readAuthError(err, 'Sign-in failed'));
      setSigningIn(false);
    }
  }

  async function handleSignOut() {
    if (!auth) return;
    setAuthError(null);
    await signOut(auth);
  }

  if (!firebaseEnabled) return <IrisApp currentUser={null} onSignOut={() => {}} />;
  if (!authReady) return <div className="auth-shell auth-shell-center">Loading...</div>;
  if (!firebaseUser) return <AuthScreen error={authError} signingIn={signingIn} onSignIn={signIn} />;
  if (!currentUser && !authError) return <div className="auth-shell auth-shell-center">Loading...</div>;
  if (authError) return <AuthScreen error={authError} signingIn={signingIn} onSignIn={signIn} />;
  return <IrisApp currentUser={currentUser} onSignOut={handleSignOut} />;
}

function shouldUseRedirectSignIn(err: unknown): boolean {
  const code = typeof err === 'object' && err && 'code' in err ? String(err.code) : '';
  return code === 'auth/popup-blocked' || code === 'auth/cancelled-popup-request';
}

function readAuthError(err: unknown, fallback: string): string {
  const code = typeof err === 'object' && err && 'code' in err ? String(err.code) : '';
  if (code === 'auth/unauthorized-domain') {
    return 'This domain is not authorized in Firebase Authentication. Add the current localhost/domain to Authorized domains.';
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

function AuthScreen({ error, signingIn, onSignIn }: { error: string | null; signingIn: boolean; onSignIn: () => void }) {
  return (
    <main className="auth-shell">
      <section className="auth-landing">
        <div className="auth-content">
          <div className="auth-brand">
            <span>iris</span>
          </div>
          {error && <div className="error">{error}</div>}
          <button className="auth-link-button" type="button" onClick={onSignIn} disabled={signingIn}>
            <span>The good web is still out there</span>
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>
    </main>
  );
}
