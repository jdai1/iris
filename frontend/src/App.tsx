import { FormEvent, ReactNode, useEffect, useRef, useState } from 'react';
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
import { ArrowUpRight, BookOpen, ChevronDown, GitFork, History, LayoutDashboard, LogOut, Orbit, PenLine, Search, Settings, UserCircle, Users } from 'lucide-react';
import {
  getAgentConversation,
  getAgentConversations,
  getAdminCrawlJobs,
  getAdminDocuments,
  getAdminIndexRuns,
  getAdminOverview,
  getAdminSources,
  getDigest,
  getMe,
  getSourceProfileAnalysis,
  setAuthTokenProvider,
  streamChatSearch,
} from './api';
import { auth, firebaseEnabled, googleProvider } from './firebase';
import { EmbeddingExplorer } from './EmbeddingExplorer';
import { GraphExplorer } from './GraphExplorer';
import { CorpusSearchForm } from './CorpusSearchForm';
import { DocumentCard } from './components/DocumentCard';
import { Pagination, ProfilePagination, type PageState } from './components/Pagination';
import { ProfileAnalysisCard } from './components/ProfileAnalysisCard';
import { StatusPill } from './components/StatusPill';
import type { AdminCrawlJob, AdminIndexRun, AdminOverview, AdminSource, AgentConversation, AgentConversationSummary, AgentStep, DigestRecommendation, Page, SearchResult, Document, SourceProfileAnalysis, User as IrisUser } from './types';

type View = 'search' | 'digest' | 'directory' | 'explore' | 'graph' | 'admin';
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
const views: View[] = ['search', 'digest', 'directory', 'explore', 'graph', 'admin'];

function initialView(): View {
  if (typeof window === 'undefined') return 'search';
  const saved = window.localStorage.getItem(VIEW_STORAGE_KEY);
  return views.includes(saved as View) ? (saved as View) : 'search';
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
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<AgentConversationSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [startedNewChat, setStartedNewChat] = useState(false);
  const [selectedResultMessageId, setSelectedResultMessageId] = useState<string | null>(null);
  const [searchesOpen, setSearchesOpen] = useState(false);
  const [artifactWidth, setArtifactWidth] = useState(defaultArtifactWidth);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const didLoadInitialConversation = useRef(false);

  useEffect(() => {
    loadInitialHistory();
  }, []);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

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

  async function refreshHistory() {
    setHistoryLoading(true);
    try {
      const items = await getAgentConversations();
      setHistory(items);
    } catch {
      // History is secondary; leave the chat surface usable if it fails.
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadInitialHistory() {
    if (didLoadInitialConversation.current) return;
    didLoadInitialConversation.current = true;
    setHistoryLoading(true);
    try {
      const items = await getAgentConversations();
      setHistory(items);
      if (items[0]) {
        const conversation = await getAgentConversation(items[0].id);
        setConversationId(conversation.id);
        setMessages(messagesFromConversation(conversation));
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
      setHistoryOpen(false);
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
    setHistoryOpen(false);
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
      <div className="chat-topbar">
        <div className="chat-topbar-spacer" />
        <div className="chat-history">
          <div className="chat-history-actions">
            <button
              className="chat-history-toggle"
              type="button"
              onClick={() => {
                setHistoryOpen((value) => !value);
                if (!historyOpen) refreshHistory();
              }}
              aria-expanded={historyOpen}
            >
              <History size={14} />
              Chats
              <ChevronDown size={14} className={historyOpen ? 'history-chevron history-chevron-open' : 'history-chevron'} />
            </button>
            {(messages.length > 0 || conversationId) && (
              <button className="chat-new-button" type="button" onClick={startNewChat} aria-label="New chat" title="New chat">
                <PenLine size={16} />
              </button>
            )}
          </div>
          {historyOpen && (
            <div className="chat-history-panel">
              {historyLoading && <div className="chat-history-empty">Loading chats...</div>}
              {!historyLoading && history.length === 0 && <div className="chat-history-empty">No saved chats yet.</div>}
              {!historyLoading &&
                history.slice(0, 8).map((item) => (
                  <button
                    key={item.id}
                    className={item.id === conversationId ? 'chat-history-item chat-history-item-active' : 'chat-history-item'}
                    type="button"
                    onClick={() => loadConversation(item.id)}
                  >
                    <span>{item.title || 'Untitled search'}</span>
                    <small>{item.message_count} messages · {formatDate(item.updated_at)}</small>
                  </button>
                ))}
            </div>
          )}
        </div>
      </div>

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
                            <strong>{step.title}</strong>
                            <small>
                              {typeof step.hits === 'number' ? `${step.hits} hits` : step.detail}
                              {typeof step.hits === 'number' && step.detail ? ` · ${step.detail}` : ''}
                            </small>
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
            <button className="chat-artifact-resize" type="button" aria-label="Resize links panel" onPointerDown={startResizeArtifact} />
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

function isLegacySyntheticAssistantMessage(message: AgentConversation['messages'][number]): boolean {
  if (message.role !== 'assistant') return false;
  if (message.results.length > 0) return false;
  const steps = message.steps ?? [];
  const onlySyntheticSteps = steps.length > 0 && steps.every(isSyntheticStep);
  return onlySyntheticSteps && message.content.includes('Tell me what you want to find in the corpus');
}

function DigestView({ onOpenProfile }: { onOpenProfile: (sourceId: number, domain: string) => void }) {
  const [items, setItems] = useState<DigestRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setItems(await getDigest());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Digest failed');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  if (loading) return <div className="empty-state">Loading digest...</div>;

  return (
    <section>
      <Flex className="section-header">
        <div>
          <Heading as="h2" fontSize="2xl" fontWeight="650">Digest</Heading>
          <Text color="iris.500" mt="1">Old and new corpus items ranked by fit, quality, and graph signal.</Text>
        </div>
        <Button type="button" onClick={refresh} variant="outline" borderRadius="0">Refresh</Button>
      </Flex>
      <Stack gap="3">
        {error && <div className="error">{error}</div>}
        {items.map((item) => (
          <DocumentCard
            key={item.document.id}
            document={item.document}
            reason={item.reason}
            score={item.score}
            onOpenProfile={onOpenProfile}
          />
        ))}
        {items.length === 0 && <div className="empty-state">No digest items yet. Add and crawl a source.</div>}
      </Stack>
    </section>
  );
}

function DirectoryView({ target, onOpenProfile }: { target: ProfileTarget; onOpenProfile: (sourceId: number, domain: string) => void }) {
  const [query, setQuery] = useState(target?.domain ?? '');
  const [selectedSource, setSelectedSource] = useState<AdminSource | null>(null);
  const [suggestions, setSuggestions] = useState<AdminSource[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [documentsPage, setDocumentsPage] = useState<Page<Document>>(emptyPage);
  const [profileAnalysis, setProfileAnalysis] = useState<SourceProfileAnalysis | null>(null);
  const [selected, setSelected] = useState<ProfileTarget>(target);
  const [documentPageState, setDocumentPageState] = useState<PageState>({ limit: 50, offset: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const suppressSuggestionsRef = useRef(false);

  useEffect(() => {
    setSelected(target);
    if (target) setQuery(target.domain);
  }, [target?.sourceId, target?.domain]);

  async function refresh(nextQuery = query, nextSelected = selected, nextPage = documentPageState) {
    setLoading(true);
    setError(null);
    try {
      const normalizedQuery = nextQuery.trim();
      if (!nextSelected && !normalizedQuery) {
        setSelectedSource(null);
        setSelected(null);
        setDocumentsPage(emptyPage<Document>());
        setProfileAnalysis(null);
        return;
      }
      const sources = await getAdminSources({ status: 'indexed', q: normalizedQuery, limit: 25 });
      const source =
        (nextSelected && sources.items.find((item) => item.id === nextSelected.sourceId)) ??
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
      setLoading(false);
    }
  }

  useEffect(() => {
    const nextPage = { limit: 50, offset: 0 };
    setDocumentPageState(nextPage);
    refresh(target?.domain ?? '', target, nextPage);
  }, [target?.sourceId, target?.domain]);

  useEffect(() => {
    const normalized = query.trim();
    if (suppressSuggestionsRef.current) {
      suppressSuggestionsRef.current = false;
      setSuggestionsOpen(false);
      return;
    }
    if (!normalized) {
      setSuggestions([]);
      setSuggestionsOpen(false);
      return;
    }
    let mounted = true;
    getAdminSources({ status: 'indexed', q: normalized, limit: 8 })
      .then((page) => {
        if (!mounted) return;
        setSuggestions(page.items);
        setSuggestionsOpen(true);
      })
      .catch(() => {
        if (!mounted) return;
        setSuggestions([]);
        setSuggestionsOpen(false);
      });
    return () => {
      mounted = false;
    };
  }, [query]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextPage = { limit: documentPageState.limit, offset: 0 };
    setDocumentPageState(nextPage);
    setSuggestionsOpen(false);
    refresh(query, null, nextPage);
  }

  function updateQuery(value: string) {
    setQuery(value);
    setSuggestionsOpen(Boolean(value.trim()));
  }

  function selectSuggestion(source: AdminSource) {
    const nextPage = { limit: documentPageState.limit, offset: 0 };
    const nextProfile = { sourceId: source.id, domain: source.canonical_domain };
    suppressSuggestionsRef.current = true;
    setQuery(source.canonical_domain);
    setSelected(nextProfile);
    setSelectedSource(source);
    setDocumentPageState(nextPage);
    setSuggestionsOpen(false);
    refresh(source.canonical_domain, nextProfile, nextPage);
  }

  function pageProfileDocuments(nextPage: PageState) {
    setDocumentPageState(nextPage);
    refresh(selected?.domain ?? query, selected, nextPage);
  }

  return (
    <Box as="section" className="directory-view">
      <CorpusSearchForm
        className="search-box"
        value={query}
        onChange={updateQuery}
        onSubmit={submit}
        placeholder={loading ? 'Loading...' : 'Find a person or domain...'}
        disabled={loading || !query.trim()}
      >
        {suggestionsOpen && suggestions.length > 0 && (
          <div className="directory-suggestions">
            {suggestions.map((source) => (
              <button key={source.id} type="button" onClick={() => selectSuggestion(source)}>
                <span>{source.canonical_domain}</span>
                <small>{source.essay_count} essays</small>
              </button>
            ))}
          </div>
        )}
      </CorpusSearchForm>

      {error && <div className="error">{error}</div>}
      {loading && <div className="empty-state">Loading...</div>}

      {!loading && (
        <div className="profile-panel">
            {selected ? (
              <>
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
              </>
            ) : (
              null
            )}
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
  const [profileTarget, setProfileTarget] = useState<ProfileTarget>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    window.localStorage.setItem(VIEW_STORAGE_KEY, view);
  }, [view]);

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

  const navItems: Array<{ view: View; label: string; icon: ReactNode; adminOnly?: boolean }> = [
    { view: 'search', label: 'Search', icon: <Search size={15} /> },
    { view: 'digest', label: 'Digest', icon: <BookOpen size={15} /> },
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
              onClick={() => setView(item.view)}
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
                  <span>{currentUser.email || currentUser.display_name || currentUser.slug}</span>
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
              {currentUser.display_name || currentUser.email || currentUser.slug}
            </div>
          </div>
        )}
      </Box>
      <Box className={view === 'explore' || view === 'graph' ? 'workspace workspace-fullscreen' : view === 'search' ? 'workspace workspace-search' : 'workspace'}>
        {view === 'search' && <SearchView onOpenProfile={openProfile} />}
        {view === 'digest' && <DigestView onOpenProfile={openProfile} />}
        {view === 'directory' && <DirectoryView target={profileTarget} onOpenProfile={openProfile} />}
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
  if (!currentUser && !authError) return <div className="auth-shell auth-shell-center">Loading account...</div>;
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
