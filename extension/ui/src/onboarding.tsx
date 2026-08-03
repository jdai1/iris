import { StrictMode, useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ExternalLink } from 'lucide-react';
import { Button } from './components/Button';
import { hasSession, irisRequest, openIris } from './chrome';
import { IrisBrand } from './IrisBrand';
import './index.css';

function App() {
  const [state, setState] = useState<'checking' | 'signed-out' | 'ready'>('checking');
  const [status, setStatus] = useState('');
  const check = useCallback(async () => {
    if (!await hasSession()) { setState('signed-out'); return; }
    try { await irisRequest('/api/me'); setState('ready'); setStatus(''); }
    catch { setState('signed-out'); setStatus('Your session expired. Sign in again.'); }
  }, []);

  useEffect(() => {
    void check();
    const listener = (changes: Record<string, chrome.storage.StorageChange>, area: string) => { if (area === 'local' && (changes.authToken || changes.authRefreshToken)) void check(); };
    chrome.storage.onChanged.addListener(listener);
    return () => chrome.storage.onChanged.removeListener(listener);
  }, [check]);

  return (
    <main className="grid min-h-svh items-center p-[clamp(32px,7vw,112px)]">
      <section className="w-[min(900px,100%)]">
        <IrisBrand className="mb-8" />
        {state === 'checking' && <p className="text-sm text-muted-foreground">Checking your Iris account…</p>}
        {state === 'signed-out' && <>
          <h1 className="max-w-3xl text-[clamp(38px,5.8vw,76px)] font-semibold leading-[0.98] tracking-[-0.055em]">Save anything worth returning to.</h1>
          <p className="mt-5 max-w-xl text-[15px] leading-6 text-muted-foreground">One click saves the current page. Iris stores the URL, title, and any passages or notes you explicitly add. It does not collect your general browsing history.</p>
          <Button className="mt-8" variant="solid" onClick={() => void openIris(true)}>Sign in to Iris <span aria-hidden="true">→</span></Button>
          {status && <p className="mt-3 text-xs text-destructive">{status}</p>}
        </>}
        {state === 'ready' && <>
          <h1 className="text-[clamp(38px,5.4vw,70px)] font-semibold leading-none tracking-[-0.05em]">Save first.<br />Organize later.</h1>
          <div className="mt-10 grid border-y md:grid-cols-3">
            {[
              ['01', 'Save', 'Click the Iris extension once. The current page is saved immediately.'],
              ['02', 'Highlight', 'Select text on the saved page, then choose Highlight.'],
              ['03', 'Return', 'Find the page, note, and highlights together in your bookshelf.'],
            ].map(([number, title, copy], index) => <div className={`min-h-48 p-5 ${index < 2 ? 'border-b md:border-b-0 md:border-r' : ''}`} key={number}><p className="text-[10px] text-muted-foreground">{number}</p><h2 className="mt-8 text-lg font-semibold">{title}</h2><p className="mt-2 text-xs leading-5 text-muted-foreground">{copy}</p></div>)}
          </div>
          <div className="mt-8 flex gap-3"><Button variant="solid" onClick={() => void openIris()}>Open Iris <ExternalLink size={15} /></Button><Button onClick={async () => { const [tab] = await chrome.tabs.query({ active: true, currentWindow: true }); if (tab?.id) await chrome.tabs.remove(tab.id); }}>Got it</Button></div>
        </>}
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
