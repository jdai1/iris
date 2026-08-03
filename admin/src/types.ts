export interface Page<T> { items: T[]; total: number; limit: number; offset: number; has_next: boolean; has_previous: boolean }
export interface IrisUser { id: number; email: string; username: string | null; is_admin: boolean }
export interface AdminQuery { id: number; conversation_uuid: string; conversation_title: string | null; user_id: number; email: string; username: string | null; content: string; created_at: string; answer_preview: string | null; step_count: number; result_count: number }
export interface AdminUser { id: number; email: string; username: string | null; created_at: string; onboarding_completed_at: string | null; conversation_count: number; query_count: number; saved_document_count: number }
export interface QueryResult { rank: number; score: number; reason: string; document_uuid: string; title: string | null; url: string; source_domain: string }
export interface ConversationMessage { id: number; role: 'user' | 'assistant'; content: string; created_at: string; steps: Array<Record<string, unknown>>; results: QueryResult[] }
export interface AdminConversation { id: number; uuid: string; title: string | null; created_at: string; updated_at: string; user_id: number; email: string; username: string | null; messages: ConversationMessage[] }
export interface AdminOverview { totals: Record<string, number>; source_statuses: Record<string, number>; document_types: Record<string, number> }
export interface AdminLibraryEntry { document: { uuid: string; title: string | null; url: string; source_domain: string }; status: 'saved' | 'read' | 'archived'; favorited: boolean; note: string | null; intent_note: string | null; tags: string[]; first_seen_at: string | null; read_at: string | null; archived_at: string | null; favorited_at: string | null }
export interface AdminLibraryCollection { id: number; name: string; description: string | null; visibility: 'private' | 'share_link'; created_at: string; updated_at: string; items: AdminLibraryEntry[] }
export interface AdminUserLibrary { collections: AdminLibraryCollection[]; entries: Page<AdminLibraryEntry> }
