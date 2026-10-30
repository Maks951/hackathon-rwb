import { ValidatorFn } from '@angular/forms';

export function trimmedMinLength(min: number): ValidatorFn {
  return control => typeof control.value === 'string' && control.value.trim().length >= min
    ? null : { trimmedMinLength: { min } };
}
