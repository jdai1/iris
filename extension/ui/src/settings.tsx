import { StrictMode, useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ExternalLink, LogOut } from 'lucide-react';
import { Button } from './components/Button';
import { disconnect, hasSession, irisRequest, openIris } from './chrome';
import { IrisBrand } from './IrisBrand';
import './index.css';

type IrisUser = { email?: string | null; display_name?: string | null };

function App() {
  const [state, setState] = useState<'checking' | 'signed-out' | 'signed-in' | 'expired'>('checking');
  const [user, setUser] = useState<IrisUser | null>(null);

  const check = useCallback(async () => {
    if (!await hasSession()) { setState('signed-out'); setUser(null); return; }
    try { setUser(await irisRequest<IrisUser>('/api/me')); setState('signed-in'); }
    catch { setState('expired'); setUser(null); }
  }, []);

  useEffect(() => {
    void check();
    const listener = () => { void check(); };
    chrome.storage.onChanged.addListener(listener);
    return () => chrome.storage.onChanged.removeListener(listener);
  }, [check]);

  const signedIn = state === 'signed-in';
  return (
    <main className="mx-auto w-[min(720px,calc(100%-48px))] py-20">
      <IrisBrand className="mb-20" />
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Browser extension</p>
      <h1 className="mt-3 text-[clamp(34px,6vw,58px)] font-semibold leading-none tracking-[-0.055em]">{signedIn ? 'Connected.' : 'Connect Iris.'}</h1>
      <p className="mt-5 text-[15px] leading-6 text-muted-foreground">{signedIn ? 'Pages, notes, and highlights save to the same Iris account you use on the web.' : 'Sign in to save pages and highlights to your Iris bookshelf.'}</p>
      <div className="mt-10 border-t">
        <SettingRow title="Account" detail={signedIn ? user?.email || user?.display_name || 'Signed in to Iris' : state === 'checking' ? 'Checking…' : state === 'expired' ? 'Session expired' : 'Not signed in'} detailClassName={signedIn ? 'text-emerald-700' : ''}>
          {signedIn ? <Button variant="ghost" onClick={async () => { await disconnect(); setState('signed-out'); setUser(null); }}><LogOut size={14} /> Disconnect</Button> : <Button variant="solid" onClick={() => void openIris(true)}>Sign in <span aria-hidden="true">→</span></Button>}
        </SettingRow>
        <SettingRow title="Iris bookshelf" detail="Open your saved pages, notes, and highlights.">
          <Button onClick={() => void openIris()}>Open Iris <ExternalLink size={14} /></Button>
        </SettingRow>
        <SettingRow title="How it works" detail="Review the save and highlight workflow." last>
          <Button onClick={() => chrome.tabs.create({ url: chrome.runtime.getURL('onboarding.html') })}>View guide</Button>
        </SettingRow>
      </div>
    </main>
  );
}

function SettingRow({ title, detail, detailClassName = '', last = false, children }: { title: string; detail: string; detailClassName?: string; last?: boolean; children: React.ReactNode }) {
  return <section className={`flex items-center justify-between py-5 ${last ? '' : 'border-b'}`}><div><h2 className="text-[13px] font-semibold">{title}</h2><p className={`mt-1 text-xs text-muted-foreground ${detailClassName}`}>{detail}</p></div>{children}</section>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
