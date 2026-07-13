import { FormEvent, ReactNode, useEffect, useRef, useState } from 'react';
import { Box } from '@chakra-ui/react';
import { ArrowUpRight, Search, X } from 'lucide-react';
import { getAgentConversation, getAgentConversations, getDocument, streamChatSearch } from '../api';
import { CorpusSearchForm } from '../CorpusSearchForm';
import { documentPath, navigateTo } from '../app/navigation';
import type { AgentConversation, AgentConversationSummary, AgentStep, DocumentDetail, SearchResult } from '../types';

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
  const [drawerResult, setDrawerResult] = useState<SearchResult | null>(null);
  const [drawerDetail, setDrawerDetail] = useState<DocumentDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const [drawerClosing, setDrawerClosing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const historyRef = useRef<HTMLDivElement | null>(null);
  const drawerCloseTimeoutRef = useRef<number | null>(null);
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

  useEffect(() => {
    if (!drawerResult) {
      setDrawerDetail(null);
      setDrawerError(null);
      setDrawerLoading(false);
      return;
    }

    let cancelled = false;
    setDrawerLoading(true);
    setDrawerError(null);
    getDocument(drawerResult.document.uuid)
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
  }, [drawerResult?.document.uuid]);

  useEffect(() => {
    return () => {
      if (drawerCloseTimeoutRef.current !== null) window.clearTimeout(drawerCloseTimeoutRef.current);
    };
  }, []);

  function openResultDrawer(result: SearchResult) {
    if (drawerCloseTimeoutRef.current !== null) {
      window.clearTimeout(drawerCloseTimeoutRef.current);
      drawerCloseTimeoutRef.current = null;
    }
    setDrawerClosing(false);
    setDrawerResult(result);
    setDrawerDetail(null);
    setDrawerError(null);
  }

  function closeResultDrawer() {
    if (!drawerResult || drawerClosing) return;
    setDrawerClosing(true);
    drawerCloseTimeoutRef.current = window.setTimeout(() => {
      setDrawerResult(null);
      setDrawerDetail(null);
      setDrawerError(null);
      setDrawerClosing(false);
      drawerCloseTimeoutRef.current = null;
    }, 180);
  }

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
    closeResultDrawer();
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

      <Box className="chat-shell">
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
                {message.role === 'assistant' && message.results && message.results.length > 0 && (
                  <SearchResultsTable
                    results={message.results}
                    selectedDocumentId={drawerResult?.document.uuid ?? null}
                    onOpenResult={openResultDrawer}
                  />
                )}
              </div>
            ))}
          </div>
        </Box>
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
      {drawerResult && (
        <>
          <button className={drawerClosing ? 'drawer-backdrop drawer-closing' : 'drawer-backdrop'} type="button" aria-label="Close details" onClick={closeResultDrawer} />
          <SearchResultDrawer
            result={drawerResult}
            detail={drawerDetail}
            loading={drawerLoading}
            error={drawerError}
            closing={drawerClosing}
            onClose={closeResultDrawer}
            onOpenProfile={onOpenProfile}
          />
        </>
      )}
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

function SearchResultsTable({
  results,
  selectedDocumentId,
  onOpenResult,
}: {
  results: SearchResult[];
  selectedDocumentId: string | null;
  onOpenResult: (result: SearchResult) => void;
}) {
  return (
    <div className="search-results-turn">
      <div className="search-results-turn-header">
        <span>Results</span>
        <small>{results.length}</small>
      </div>
      <div className="search-results-table" role="table" aria-label="Search results">
        <div className="search-results-row search-results-head" role="row">
          <span>Title</span>
          <span>One-liner</span>
        </div>
        {results.map((result) => {
          const { document } = result;
          const selected = selectedDocumentId === document.uuid;
          return (
            <div
              key={document.uuid}
              className={selected ? 'search-results-row search-results-row-selected' : 'search-results-row'}
              role="row"
              tabIndex={0}
              aria-selected={selected}
              onClick={(event) => {
                const target = event.target as HTMLElement;
                if (target.closest('a, button')) return;
                onOpenResult(result);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onOpenResult(result);
                }
              }}
            >
              <span className="search-results-title tooltip-overflow-cell" data-label="Title" data-tooltip={document.title ?? document.url}>
                <strong>
                  <span className="tooltip-overflow-text">{document.title ?? document.url}</span>
                  <a href={document.url} target="_blank" rel="noreferrer" aria-label="Open document" onClick={(event) => event.stopPropagation()}>
                    <ArrowUpRight size={14} />
                  </a>
                </strong>
              </span>
              <span className="search-results-one-liner tooltip-overflow-cell" data-label="One-liner" data-tooltip={resultOneLiner(result)}>
                <span className="tooltip-overflow-text">{resultOneLiner(result)}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SearchResultDrawer({
  result,
  detail,
  loading,
  error,
  closing,
  onClose,
  onOpenProfile,
}: {
  result: SearchResult;
  detail: DocumentDetail | null;
  loading: boolean;
  error: string | null;
  closing: boolean;
  onClose: () => void;
  onOpenProfile: (sourceId: number, domain: string) => void;
}) {
  const document = detail ?? result.document;
  return (
    <aside className={closing ? 'bookshelf-detail-drawer search-result-drawer drawer-closing' : 'bookshelf-detail-drawer search-result-drawer'} aria-label="Search result details">
      <div className="bookshelf-detail-header">
        <div>
          <button className="profile-link" type="button" onClick={() => onOpenProfile(document.source_id, document.source_domain)}>
            {document.source_domain}
          </button>
          <h3>
            {document.title ?? document.url}
            <a href={document.url} target="_blank" rel="noreferrer" aria-label="Open document">
              <ArrowUpRight size={15} />
            </a>
          </h3>
        </div>
        <button type="button" onClick={onClose} aria-label="Close details">
          <X size={16} />
        </button>
      </div>

      {loading && <div className="skeleton-stack" aria-label="Loading document details"><span className="skeleton-line" /><span className="skeleton-line" /><span className="skeleton-line" /></div>}
      {error && <div className="error">{error}</div>}

      <section className="bookshelf-detail-section">
        <h4>Summary</h4>
        <p>{document.summary || document.one_liner || 'No summary yet.'}</p>
      </section>

      <section className="bookshelf-detail-section search-result-match">
        <h4>Why This Result</h4>
        <p>{naturalRelevance(result)}</p>
      </section>

      {document.topics.length > 0 && (
        <section className="bookshelf-detail-section">
          <h4>Tags</h4>
          <div className="bookshelf-detail-tags directory-document-drawer-tags">
            {document.topics.map((topic) => <span key={topic}>{topic}</span>)}
          </div>
        </section>
      )}

      {detail && (
        <div className="bookshelf-detail-reference-grid">
          <section className="bookshelf-detail-section">
            <div className="bookshelf-detail-section-heading bookshelf-detail-reference-heading">
              <h4>References</h4>
              <span>{detail.outgoing_links.length}</span>
            </div>
            {detail.outgoing_links.length ? (
              <div className="bookshelf-detail-link-list">
                {detail.outgoing_links.slice(0, 8).map((link, index) => (
                  link.target_document_uuid ? (
                    <button key={`${link.target_url}-${index}`} type="button" onClick={() => navigateTo(documentPath(link.target_document_uuid!))}>
                      <strong>{link.anchor_text || link.target_domain || link.target_url}</strong>
                      <small>{link.target_domain || link.target_url}</small>
                      {link.context && <span>{link.context}</span>}
                    </button>
                  ) : (
                    <a key={`${link.target_url}-${index}`} href={link.target_url} target="_blank" rel="noreferrer">
                      <strong>{link.anchor_text || link.target_domain || link.target_url}</strong>
                      <small>{link.target_domain || link.target_url}</small>
                      {link.context && <span>{link.context}</span>}
                    </a>
                  )
                ))}
              </div>
            ) : (
              <p>No outgoing references indexed.</p>
            )}
          </section>
          <section className="bookshelf-detail-section">
            <div className="bookshelf-detail-section-heading bookshelf-detail-reference-heading">
              <h4>Referenced By</h4>
              <span>{detail.incoming_links.length}</span>
            </div>
            {detail.incoming_links.length ? (
              <div className="bookshelf-detail-link-list">
                {detail.incoming_links.slice(0, 8).map((link, index) => (
                  <button key={`${link.source_document_uuid}-${index}`} type="button" onClick={() => navigateTo(documentPath(link.source_document_uuid))}>
                    <strong>{link.anchor_text || link.target_url || 'Referenced document'}</strong>
                    <small>{link.target_url}</small>
                  </button>
                ))}
              </div>
            ) : (
              <p>No incoming references indexed.</p>
            )}
          </section>
        </div>
      )}
    </aside>
  );
}

function naturalRelevance(result: SearchResult): string {
  const text =
    result.document.one_liner?.trim() ||
    result.document.summary?.trim() ||
    cleanTechnicalReason(result.reason);
  return truncate(text || 'This result matched the search terms and corpus context.', 180);
}

function resultOneLiner(result: SearchResult): string {
  return truncate(result.document.one_liner?.trim() || 'No one-liner yet.', 180);
}

function cleanTechnicalReason(reason: string): string {
  return reason
    .replace(/^agent selected:\s*/i, '')
    .replace(/\b(keyword|semantic|tags|categories):\s*/gi, '')
    .replace(/\bpgvector cosine\s+\d+(?:\.\d+)?/gi, 'semantic match')
    .replace(/\bembedding cosine\s+\d+(?:\.\d+)?/gi, 'semantic match')
    .replace(/\bkeyword overlap\s+\d+%/gi, 'keyword match')
    .replace(/\s*;\s*/g, ', ')
    .trim();
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 3).trimEnd()}...`;
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
