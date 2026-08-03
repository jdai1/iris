export type Entry = {
  document: { uuid: string; title: string | null; url: string };
  favorited: boolean; status: string; note: string | null; intent_note: string | null; tags: string[];
};

type IrisConfig = { profile: string; appBase: string; apiBase: string };

export async function getConfig(): Promise<IrisConfig> {
  return chrome.runtime.sendMessage({ type: 'iris-config' });
}

export async function hasSession(): Promise<boolean> {
  const response = await chrome.runtime.sendMessage({ type: 'iris-session-status' });
  return Boolean(response?.connected);
}

export async function disconnect() {
  const response = await chrome.runtime.sendMessage({ type: 'iris-disconnect' });
  if (!response?.ok) throw new Error(response?.error || 'Could not disconnect Iris');
}

export async function openIris(login = false) {
  const { appBase } = await getConfig();
  const query = login ? `?iris_extension_auth=${encodeURIComponent(chrome.runtime.id)}` : '';
  return chrome.tabs.create({ url: `${appBase.replace(/\/+$/, '')}/${query}` });
}

export async function irisRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await chrome.runtime.sendMessage({ type: 'iris-request', path, options });
  if (!response?.ok) throw new Error(response?.status === 401 ? 'Sign in to Iris again' : response?.payload?.detail || response?.error || `Iris returned HTTP ${response?.status}`);
  return response.payload as T;
}
