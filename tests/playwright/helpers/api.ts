import { APIRequestContext, request } from '@playwright/test';

type AuthHeaders = Record<'access-token' | 'token-type' | 'client' | 'expiry' | 'uid', string>;

// Thin client over the dashboard API, authenticated as a real user via devise_token_auth.
export class ApiClient {
  private constructor(
    readonly ctx: APIRequestContext,
    readonly auth: AuthHeaders,
    readonly accountId: number
  ) {}

  static async login(baseURL: string, email: string, password: string, accountId: number) {
    const ctx = await request.newContext({ baseURL });
    const res = await ctx.post('/auth/sign_in', { data: { email, password } });
    if (!res.ok()) throw new Error(`login failed for ${email}: ${res.status()} ${await res.text()}`);
    const h = res.headers();
    const auth = { 'access-token': h['access-token'], 'token-type': h['token-type'], client: h.client, expiry: h.expiry, uid: h.uid };
    return new ApiClient(ctx, auth, accountId);
  }

  // Header bag the dashboard keeps in the cw_d_session_info cookie.
  sessionCookieValue() {
    return JSON.stringify(this.auth);
  }

  async call<T = unknown>(method: 'get' | 'post' | 'patch' | 'put' | 'delete', path: string, data?: unknown): Promise<T> {
    const res = await this.ctx.fetch(`/api/v1/accounts/${this.accountId}${path}`, {
      method: method.toUpperCase(),
      headers: this.auth,
      data,
    });
    const body = await res.text();
    if (!res.ok()) throw new Error(`${method.toUpperCase()} ${path} -> ${res.status()}: ${body}`);
    return (body ? JSON.parse(body) : undefined) as T;
  }

  async createContact(name: string, email: string) {
    const res = await this.call<{ payload: { contact: { id: number } } }>('post', '/contacts', { name, email });
    return res.payload.contact;
  }

  async createConversation(inboxId: number, contactId: number, message: string, extra: Record<string, unknown> = {}) {
    return this.call<{ id: number; status: string }>('post', '/conversations', {
      inbox_id: inboxId,
      contact_id: contactId,
      message: { content: message },
      ...extra,
    });
  }

  async getConversation(id: number) {
    return this.call<Record<string, unknown>>('get', `/conversations/${id}`);
  }
}
