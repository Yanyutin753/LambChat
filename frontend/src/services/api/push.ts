/**
 * Push notification API service
 * 推送通知 API 服务
 */

import { authFetch } from "./fetch";
import { API_BASE } from "./config";

export interface PushSubscriptionResponse {
  id: string;
  user_id: string;
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent: string;
  created_at: string;
  last_used_at: string | null;
}

export const pushApi = {
  async getSubscriptionStatus(
    endpoint: string,
  ): Promise<{ registered: boolean }> {
    try {
      return await authFetch(`${API_BASE}/api/push/subscription-status`, {
        method: "POST",
        body: JSON.stringify({ endpoint }),
      });
    } catch (error) {
      if ((error as { status?: number })?.status === 404)
        return { registered: true };
      throw error;
    }
  },

  /** Get VAPID public key (no auth required) */
  async getVapidPublicKey(): Promise<string> {
    const resp = await authFetch<{ public_key: string }>(
      `${API_BASE}/api/push/vapid-public-key`,
      { skipAuth: true },
    );
    return resp?.public_key ?? "";
  },

  /** Register a push subscription */
  async subscribe(
    subscription: PushSubscriptionJSON,
    userAgent: string = "",
  ): Promise<PushSubscriptionResponse> {
    return authFetch<PushSubscriptionResponse>(
      `${API_BASE}/api/push/subscribe`,
      {
        method: "POST",
        body: JSON.stringify({
          endpoint: subscription.endpoint,
          keys: subscription.keys,
          user_agent: userAgent,
        }),
      },
    );
  },

  /** Remove a push subscription */
  async unsubscribe(endpoint: string): Promise<void> {
    await authFetch(`${API_BASE}/api/push/unsubscribe`, {
      method: "POST",
      body: JSON.stringify({ endpoint }),
    });
  },

  /** Remove all push subscriptions for current user */
  async deleteAllSubscriptions(): Promise<void> {
    await authFetch(`${API_BASE}/api/push/subscriptions`, {
      method: "DELETE",
    });
  },
};

/** Type matching PushSubscription.toJSON() */
export interface PushSubscriptionJSON {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  expirationTime: number | null;
}
