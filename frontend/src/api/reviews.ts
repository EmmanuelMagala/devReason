import { API_URL } from "@/config/constants";
import { apiClient } from "@/api/client";
import { adaptReview } from "@/lib/adapters";
import type { Review, ReviewCreate } from "@/types";
const pendingRequests = new Map<string, string>();

export const reviewsApi = {
  async create(data: ReviewCreate): Promise<{ id: string; status: string }> {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(data)));
    const storageKey = 'devreason:request:' + Array.from(new Uint8Array(digest)).map(n => n.toString(16).padStart(2, '0')).join('');
    let key = pendingRequests.get(storageKey);
    try { key = key || sessionStorage.getItem(storageKey) || undefined; } catch { /* Storage may be unavailable. */ }
    key = key || crypto.randomUUID(); pendingRequests.set(storageKey, key);
    try { sessionStorage.setItem(storageKey, key); } catch { /* In-memory retry still works. */ }
    const response = await apiClient.post("/api/reviews", {
      pr_url: data.prUrl,
      repo_id: data.repoId,
      post_to_github: data.postToGithub,
      mode: data.mode ?? "pr", pr_number: data.prNumber, branch: data.branch, commit_sha: data.commitSha, scope: data.scope ?? {},
    }, {headers: {'Idempotency-Key': key}});
    pendingRequests.delete(storageKey);
    try { sessionStorage.removeItem(storageKey); } catch { /* No stored state to clear. */ }

    return response.data;
  },

  async getOne(reviewId: string): Promise<Review> {
    const response = await apiClient.get(`/api/reviews/${reviewId}`);
    return adaptReview(response.data);
  },

  streamUrl(reviewId: string) {
    return `${API_URL}/api/reviews/${reviewId}/stream`;
  },
};
