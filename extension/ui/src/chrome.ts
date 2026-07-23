export const IRIS_HOME = 'http://localhost:5180/';

export type Entry = {
  document: { id: number; title: string | null; url: string };
  favorited: boolean; status: string; note: string | null; intent_note: string | null; tags: string[];
};

export async function getAuthToken() {
  return (await chrome.storage.local.get({ authToken: '' })).authToken as string;
}

export function openIris(login = false) {
  const query = login ? `?iris_extension_auth=${encodeURIComponent(chrome.runtime.id)}` : '';
  return chrome.tabs.create({ url: `${IRIS_HOME}${query}` });
}

export async function irisRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await chrome.runtime.sendMessage({ type: 'iris-request', path, options });
  if (!response?.ok) throw new Error(response?.status === 401 ? 'Sign in to Iris again' : response?.payload?.detail || response?.error || `Iris returned HTTP ${response?.status}`);
  return response.payload as T;
}
