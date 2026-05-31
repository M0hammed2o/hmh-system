/**
 * Offline draft queue backed by localStorage.
 * Stores failed submissions when the device loses connectivity.
 * Sync logic lives in the calling page (to avoid circular imports).
 */

export type DraftType = "material_request" | "stage_update" | "usage";

export interface OfflineDraft {
  id: string;
  type: DraftType;
  created_at: string;
  projectId: string;
  siteId: string;
  lotId: string;
  payload: Record<string, unknown>;
}

const STORAGE_KEY = "hmh_offline_drafts";

export function getDrafts(): OfflineDraft[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export function saveDraft(draft: Omit<OfflineDraft, "id" | "created_at">): OfflineDraft {
  const full: OfflineDraft = {
    ...draft,
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    created_at: new Date().toISOString(),
  };
  const existing = getDrafts();
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...existing, full]));
  return full;
}

export function removeDraft(id: string): void {
  const remaining = getDrafts().filter(d => d.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(remaining));
}

export function clearDrafts(): void {
  localStorage.removeItem(STORAGE_KEY);
}
