import { FormControl } from '@angular/forms';
import { trimmedMinLength } from './trimmed-length.validator';

describe('Project input validation', () => {
  it('rejects whitespace and short trimmed input', () => {
    const validate = trimmedMinLength(2);
    expect(validate(new FormControl('   '))).toBeTruthy();
    expect(validate(new FormControl(' a '))).toBeTruthy();
    expect(validate(new FormControl(' ab '))).toBeNull();
  });
});
