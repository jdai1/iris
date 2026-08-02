import { auth } from './firebase';
import type { AdminConversation, AdminOverview, AdminQuery, AdminUser, AdminUserLibrary, IrisUser, Page } from './types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

async function request<T>(path: string): Promise<T> {
  const token = auth?.currentUser ? await auth.currentUser.getIdToken() : null;
  let response = await fetch(`${API_BASE}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (response.status === 401 && auth?.currentUser) {
    response = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${await auth.currentUser.getIdToken(true)}` } });
  }
  if (!response.ok) {
    const payload = await response.text();
    let detail = payload;
    try {
      const parsed = JSON.parse(payload) as { detail?: string };
      detail = parsed.detail || payload;
    } catch {
      // Keep non-JSON error responses as-is.
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function pagePath(path: string, params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== '') search.set(key, String(value)); });
  return `${path}?${search}`;
}

export const getMe = () => request<IrisUser>('/api/me');
export const getQueries = (params: { q?: string; userId?: number; limit: number; offset: number }) => request<Page<AdminQuery>>(pagePath('/api/admin/queries', { q: params.q, user_id: params.userId, limit: params.limit, offset: params.offset }));
export const getConversation = (uuid: string) => request<AdminConversation>(`/api/admin/conversations/${encodeURIComponent(uuid)}`);
export const getUsers = (params: { q?: string; limit: number; offset: number }) => request<Page<AdminUser>>(pagePath('/api/admin/users', params));
export const getUserLibrary = (userId: number, params: { limit: number; offset: number }) => request<AdminUserLibrary>(pagePath(`/api/admin/users/${userId}/library`, params));
export const getOverview = () => request<AdminOverview>('/api/admin/overview');
