/**
 * API boundary for the internal app.
 *
 * No AURUMTRACE backend or API contract exists in this repository, so nothing
 * here pretends to call one. When VITE_API_BASE_URL is set later, the real
 * endpoints should be wired in here, behind the same functions.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) || undefined;

export type ApiConnection = 'not-configured' | 'configured-no-contract';
export const apiConnection: ApiConnection = API_BASE ? 'configured-no-contract' : 'not-configured';

export const DATA_SOURCE_NOTE =
  apiConnection === 'not-configured'
    ? 'Synthetic demo data · no API connected'
    : 'API URL set, but no endpoint contract is implemented yet · showing synthetic demo data';

export interface AiExplanationResult {
  ok: boolean;
  text?: string;
  error?: string;
  data?: any;
}

export type AiExplanationError = AiExplanationResult;

/** Requests an AI explanation for an exception. Never fabricates a result. */
export async function requestAiExplanation(exceptionId: string): Promise<AiExplanationResult> {
  if (!API_BASE) {
    return {
      ok: false,
      error: `No AI investigation service is configured (VITE_API_BASE_URL is not set). No explanation was generated for ${exceptionId}.`,
    };
  }
  try {
    const token = typeof window !== 'undefined' ? localStorage.getItem('aurum_token') : null;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    const res = await fetch(`${API_BASE}/investigations/run`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ exceptionId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return {
        ok: false,
        error: err.detail || err.message || `AI Investigation API failed with status ${res.status}`,
      };
    }
    const data = await res.json();
    return {
      ok: true,
      text: data.response?.summary || 'AI investigation completed successfully.',
      data,
    };
  } catch (err: any) {
    return {
      ok: false,
      error: `Network error contacting AI Investigation API at ${API_BASE}: ${err.message}`,
    };
  }
}
