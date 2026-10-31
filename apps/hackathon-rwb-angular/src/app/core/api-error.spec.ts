import { describe, expect, it } from 'vitest';
import { apiErrorMessage } from './api-error';

describe('Run and step error messages', () => {
  it('renders the structured API error with its code', () => {
    expect(apiErrorMessage({ code: 'invalid_model_output', message: 'notes: missing' }))
      .toBe('notes: missing (invalid_model_output)');
  });
  it('preserves legacy string errors', () => {
    expect(apiErrorMessage('Generation failed')).toBe('Generation failed');
  });
  it('does not stringify an unknown object', () => {
    expect(apiErrorMessage({ unexpected: true })).not.toContain('[object Object]');
  });
});
