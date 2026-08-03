import { StrictMode, useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Check, Clock3, ExternalLink, Heart, MessageSquarePlus, Plus, RotateCw, Settings, X } from 'lucide-react';
import { Button } from './components/Button';
import { Entry, hasSession, irisRequest, openIris } from './chrome';
import { IrisBrand } from './IrisBrand';
import './index.css';

type Capture = { entry: Entry };
type Phase = 'checking' | 'signed-out' | 'saving' | 'saved' | 'error';

function App() {
  const [phase, setPhase] = useState<Phase>('checking');
  const [entry, setEntry] = useState<Entry | null>(null);
  const [domain, setDomain] = useState('');
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState('');
  const [topic, setTopic] = useState('');
  const [message, setMessage] = useState('');
  const [messageError, setMessageError] = useState(false);
  const [updating, setUpdating] = useState(false);

  const capture = useCallback(async () => {
    setMessage('');
    setMessageError(false);
    setEntry(null);
    if (!await hasSession()) {
      setPhase('signed-out');
      return;
    }
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url || !/^https?:\/\//i.test(tab.url)) {
      setPhase('error');
      setMessage('Iris can only save regular web pages.');
      return;
    }
    setDomain(new URL(tab.url).hostname.replace(/^www\./, ''));
    setPhase('saving');
    try {
      const page = await irisRequest<Capture>('/api/browser/pages/capture', {
        method: 'POST',
        body: JSON.stringify({ url: tab.url, title: tab.title || null, crawl_now: false }),
      });
      setEntry(page.entry);
      setNote(page.entry.note || page.entry.intent_note || '');
      setPhase('saved');
      const stored = await chrome.storage.local.get({ savedUrls: [] });
      const savedUrls = [...new Set([...(stored.savedUrls as string[]), tab.url, page.entry.document.url])].slice(-2000);
      await chrome.storage.local.set({ savedUrls });
      chrome.tabs.sendMessage(tab.id, { type: 'iris-page-saved', page }).catch(() => undefined);
    } catch (error) {
      if (!await hasSession()) {
        setPhase('signed-out');
        return;
      }
      setPhase('error');
      setMessage(error instanceof Error ? error.message : 'Iris could not save this page.');
    }
  }, []);

  useEffect(() => { void capture(); }, [capture]);

  async function update(payload: Record<string, unknown>, success = 'Saved') {
    if (!entry || updating) return false;
    setUpdating(true);
    setMessage('');
    setMessageError(false);
    try {
      const updated = await irisRequest<Entry>(`/api/documents/${entry.document.uuid}/bookshelf`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      setEntry(updated);
      setNote(updated.note || updated.intent_note || '');
      setMessage(success);
      window.setTimeout(() => setMessage((current) => current === success ? '' : current), 1400);
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not update this page.');
      setMessageError(true);
      return false;
    } finally {
      setUpdating(false);
    }
  }

  return (
    <main className="min-h-[280px] bg-background px-5 pb-4 pt-5 text-foreground">
      <header className="flex items-center justify-between">
        <IrisBrand />
        <div className="flex items-center gap-1">
          <Button className="h-8 px-2 text-[11px]" variant="ghost" onClick={() => void openIris()}>
            Open Iris <ExternalLink size={13} />
          </Button>
          <Button aria-label="Extension settings" title="Extension settings" size="icon" variant="ghost" onClick={() => chrome.runtime.openOptionsPage()}>
            <Settings size={15} />
          </Button>
        </div>
      </header>

      {(phase === 'checking' || phase === 'saving') && (
        <section className="grid min-h-48 place-items-center">
          <div className="flex flex-col items-center gap-3 text-xs text-muted-foreground">
            <span className="size-4 animate-spin rounded-full border-2 border-muted border-t-primary" />
            {phase === 'saving' ? 'Saving this page…' : 'Checking your session…'}
          </div>
        </section>
      )}

      {phase === 'signed-out' && (
        <section className="pb-5 pt-10">
          <h1 className="text-2xl font-semibold tracking-[-0.035em]">Save the good web.</h1>
          <p className="mb-6 mt-2 max-w-sm text-[13px] leading-5 text-muted-foreground">
            Sign in once to sync saved pages, highlights, and notes with Iris.
          </p>
          <Button variant="solid" onClick={() => void openIris(true)}>Sign in to Iris <span aria-hidden="true">→</span></Button>
        </section>
      )}

      {phase === 'error' && (
        <section className="pb-4 pt-10">
          <h1 className="text-xl font-semibold tracking-tight">Couldn’t save this page</h1>
          <p className="mt-2 text-xs leading-5 text-destructive">{message}</p>
          <div className="mt-5 flex gap-2">
            <Button variant="solid" onClick={() => void capture()}><RotateCw size={14} /> Try again</Button>
            <Button onClick={() => void openIris()}>Open Iris</Button>
          </div>
        </section>
      )}

      {phase === 'saved' && entry && (
        <section>
          <div className="mt-6 flex items-center gap-2 text-[11px]">
            <span className="size-2 rounded-full bg-emerald-700" />
            <span className="font-semibold text-emerald-700">Saved</span>
            <span className="text-border">·</span>
            <span className="text-muted-foreground">{domain}</span>
          </div>
          <h1 className="mb-5 mt-2 line-clamp-2 text-xl font-semibold leading-6 tracking-[-0.025em]">
            {entry.document.title || entry.document.url}
          </h1>

          <div className="flex gap-2 border-b pb-5">
            <Button className={entry.favorited ? 'bg-accent text-accent-foreground' : ''} disabled={updating} size="sm" onClick={() => void update({ favorited: !entry.favorited }, entry.favorited ? 'Removed from favorites' : 'Added to favorites')}>
              <Heart size={14} fill={entry.favorited ? 'currentColor' : 'none'} /> {entry.favorited ? 'Favorited' : 'Favorite'}
            </Button>
            <Button className={entry.status === 'read' ? 'bg-accent text-accent-foreground' : ''} disabled={updating} size="sm" onClick={() => void update({ status: entry.status === 'saved' ? 'read' : 'saved' }, entry.status === 'saved' ? 'Marked read' : 'Moved to Read next')}>
              {entry.status === 'saved' ? <Clock3 size={14} /> : <Check size={14} />} {entry.status === 'saved' ? 'Read next' : 'Read'}
            </Button>
            <Button disabled={updating} size="sm" onClick={() => setNoteOpen((value) => !value)}>
              <MessageSquarePlus size={14} /> {note ? 'Edit note' : 'Add note'}
            </Button>
          </div>

          {noteOpen && (
            <div className="border-b py-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[11px] font-semibold">Note</span>
                <Button aria-label="Close note" size="icon" variant="ghost" onClick={() => setNoteOpen(false)}><X size={13} /></Button>
              </div>
              <textarea className="min-h-24 w-full resize-y rounded-md border bg-background p-2 text-[13px] outline-none focus:ring-2 focus:ring-ring/50" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Why is this worth keeping?" />
              <Button className="mt-2" disabled={updating} size="sm" variant="solid" onClick={async () => { if (await update({ note: note.trim() || null }, 'Note saved')) setNoteOpen(false); }}>Save note</Button>
            </div>
          )}

          <div className="pt-4">
            <p className="mb-2 text-[11px] font-semibold">Topics</p>
            <div className="flex flex-wrap gap-2">
              {entry.tags.map((tag) => (
                <Button className="bg-accent text-accent-foreground" key={tag} disabled={updating} size="sm" onClick={() => void update({ tags: entry.tags.filter((item) => item !== tag) }, `Removed ${tag}`)}>
                  {tag} <X size={11} />
                </Button>
              ))}
            </div>
            <form onSubmit={(event) => { event.preventDefault(); const value = topic.trim(); if (value && !entry.tags.includes(value)) { setTopic(''); void update({ tags: [...entry.tags, value] }, `Added ${value}`); } }}>
              <div className="mt-2 flex items-center border-b focus-within:border-ring">
                <Plus size={14} className="text-muted-foreground" />
                <input className="h-9 min-w-0 flex-1 border-0 bg-transparent px-2 text-[13px] outline-none" value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Add a topic and press Enter" />
              </div>
            </form>
          </div>

          <footer className="mt-4 flex items-center justify-between border-t pt-3 text-[11px]">
            <span className="text-muted-foreground">Select text on the page to highlight it.</span>
            <span className={messageError ? 'text-destructive' : 'text-emerald-700'}>{message}</span>
          </footer>
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
