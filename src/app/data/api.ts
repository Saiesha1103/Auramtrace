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

export interface AiExplanationError {
  ok: false;
  error: string;
}

/** Requests an AI explanation for an exception. Never fabricates a result. */
export async function requestAiExplanation(exceptionId: string): Promise<AiExplanationError> {
  if (!API_BASE) {
    return {
      ok: false,
      error: `No AI investigation service is configured (VITE_API_BASE_URL is not set). No explanation was generated for ${exceptionId}.`,
    };
  }
  return {
    ok: false,
    error: `An API base URL is configured, but this repository has no AI explanation endpoint contract yet. No explanation was generated for ${exceptionId}.`,
  };
}
