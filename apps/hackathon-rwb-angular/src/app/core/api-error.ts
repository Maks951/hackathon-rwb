import { HttpErrorResponse } from '@angular/common/http';

export function apiErrorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    if (error.status === 0) return 'Network error. Is the API running?';
    const body = error.error;
    const detail = body?.error ?? body;
    const message = detail?.message ?? (typeof detail?.detail === 'string' ? detail.detail : null);
    if (message) return detail.code ? `${message} (${detail.code})` : message;
    return `HTTP ${error.status}: request failed.`;
  }
  if (error instanceof Error && error.name === 'TimeoutError') return 'The API did not respond within 10 seconds. Retry the request.';
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object' && 'message' in error && typeof error.message === 'string') {
    const code = 'code' in error && typeof error.code === 'string' ? error.code : null;
    return code ? `${error.message} (${code})` : error.message;
  }
  return 'Request failed. Please retry.';
}
