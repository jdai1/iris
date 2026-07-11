import { FormEvent, ReactNode, useEffect, useRef, useState } from 'react';
import { Box } from '@chakra-ui/react';
import { ChevronDown, Search, X } from 'lucide-react';
import { getAgentConversation, getAgentConversations, searchCorpus, streamChatSearch } from '../api';
import { defaultArtifactWidth } from '../app/navigation';
import { CorpusSearchForm } from '../CorpusSearchForm';
import { DocumentCard } from '../components/DocumentCard';
import type { AgentConversation, AgentConversationSummary, AgentStep, SearchResult } from '../types';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  results?: SearchResult[];
  steps?: AgentStep[];
  pending?: boolean;
};

const ACTIVE_CHAT_STORAGE_KEY = 'iris.activeChatUuid';
const SEARCH_RELOAD_STORAGE_KEY = 'iris.searchReloading';
const HISTORY_PAGE_SIZE = 15;

export function SearchView({ onOpenProfile }: { onOpenProfile: (sourceId: number, domain: string) => void }) {
  const [query, setQuery] = useState('');
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [history, setHistory] = useState<AgentConversationSummary[]>([]);
  const [historyQuery, setHistoryQuery] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [startedNewChat, setStartedNewChat] = useState(false);
  const [selectedResultMessageId, setSelectedResultMessageId] = useState<string | null>(null);
  const [searchesOpen, setSearchesOpen] = useState(false);
  const [linksDrawerOpen, setLinksDrawerOpen] = useState(false);
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
      const activeChatId = window.sessionStorage.getItem(ACTIVE_CHAT_STORAGE_KEY);
      if (shouldRestoreConversation.current && activeChatId) {
        await loadConversation(activeChatId);
      }
    } catch {
      // History is secondary; start on a clean chat if it fails.
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadConversation(id: string) {
    if (loading) return;
    setError(null);
    try {
      const conversation = await getAgentConversation(id);
      setConversationId(conversation.uuid);
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
          setConversationId(event.data.conversation_uuid);
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

  const showResultsSkeleton = loading && messages.length > 0 && !selectedResultTurn;
  const showArtifact = Boolean(selectedResultTurn) || showResultsSkeleton;

  useEffect(() => {
    if (!showArtifact) {
      setLinksDrawerOpen(false);
    }
  }, [showArtifact]);

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
            {historyLoading && <HistorySkeleton />}
            {!historyLoading && history.length === 0 && <div className="chat-history-empty">No saved chats yet.</div>}
            {!historyLoading &&
              history.map((item) => (
                <button
                  key={item.uuid}
                  className={item.uuid === conversationId ? 'chat-history-item chat-history-item-active' : 'chat-history-item'}
                  type="button"
                  onClick={() => loadConversation(item.uuid)}
                >
                  <span>{item.title || 'Untitled search'}</span>
                </button>
              ))}
            {!historyLoading && historyLoadingMore && <HistorySkeleton rows={2} />}
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
        className={showArtifact ? 'chat-shell chat-shell-with-artifact' : 'chat-shell'}
        style={showArtifact ? { '--artifact-width': `${artifactWidth}px` } as React.CSSProperties : undefined}
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

        {showArtifact && (
          <>
          <button
            className="chat-artifact-toggle"
            type="button"
            onClick={() => setLinksDrawerOpen(true)}
            aria-label="Open links"
          >
            Links
            <span>
              {selectedResultTurn
                ? selectedResultTurn.results.length
                : '...'}
            </span>
          </button>
          <button
            className={linksDrawerOpen ? 'chat-artifact-backdrop chat-artifact-backdrop-open' : 'chat-artifact-backdrop'}
            type="button"
            aria-label="Close links"
            onClick={() => setLinksDrawerOpen(false)}
          />
          <aside className={linksDrawerOpen ? 'chat-artifact chat-artifact-drawer-open' : 'chat-artifact'} aria-label="Search results">
            <button className="chat-artifact-resize" type="button" aria-label="Resize links panel" data-tooltip="Resize links panel" onPointerDown={startResizeArtifact} />
            <div className="chat-artifact-header">
              <span>Links</span>
              <small>
                {selectedResultTurn
                  ? `${selectedResultTurn.results.length} result${selectedResultTurn.results.length === 1 ? '' : 's'}`
                  : 'Searching'}
              </small>
              <button className="chat-artifact-close" type="button" onClick={() => setLinksDrawerOpen(false)} aria-label="Close links">
                <X size={15} />
              </button>
            </div>
            {selectedResultTurn && resultTurns.length > 1 && (
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
              {selectedResultTurn ? (
                selectedResultTurn.results.map((result) => (
                  <DocumentCard
                    key={result.document.id}
                    document={result.document}
                    reason={result.reason}
                    score={result.score}
                    onOpenProfile={onOpenProfile}
                    compact
                  />
                ))
              ) : (
                <ResultSkeleton />
              )}
            </div>
          </aside>
          </>
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
    <div className="chat-pending" aria-live="polite">
      <div>
        <span>Thinking</span>
        <span className="thinking-word" aria-hidden="true">
          <span>quietly</span>
          <span>through it</span>
          <span>with context</span>
          <span>ahead</span>
        </span>
      </div>
      <div className="skeleton-stack skeleton-stack-chat" aria-hidden="true">
        <span className="skeleton-line" />
        <span className="skeleton-line" />
        <span className="skeleton-line" />
      </div>
    </div>
  );
}

function HistorySkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="skeleton-stack chat-history-skeleton" aria-label="Loading chats">
      {Array.from({ length: rows }).map((_, index) => (
        <span className="skeleton-line" key={index} />
      ))}
    </div>
  );
}

function ResultSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton-stack chat-results-skeleton" aria-label="Loading search results">
      {Array.from({ length: rows }).map((_, index) => (
        <div className="chat-result-skeleton-card" key={index}>
          <span className="skeleton-line" />
          <span className="skeleton-line" />
          <span className="skeleton-line" />
        </div>
      ))}
    </div>
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
