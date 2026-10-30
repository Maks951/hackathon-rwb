import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, Router } from '@angular/router';
import { BehaviorSubject, of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { ApiService } from '../../core/api.service';
import { ProjectComponent } from './project.component';

describe('Starting generation', () => {
  it('reuses the key after a failed request and changes it for another project', () => {
    const params = new BehaviorSubject(convertToParamMap({ id: 'p1' }));
    const route = { paramMap: params, get snapshot() { return { paramMap: params.value }; } };
    const api = {
      getProject: vi.fn((id: string) => of({ id, name: id, requirements: 'requirements', createdAt: '' })),
      startRun: vi.fn(() => throwError(() => new Error('offline'))),
    };
    TestBed.configureTestingModule({ providers: [
      { provide: ActivatedRoute, useValue: route },
      { provide: Router, useValue: { navigate: vi.fn() } },
      { provide: ApiService, useValue: api },
    ] });
    const component = TestBed.runInInjectionContext(() => new ProjectComponent());
    component.ngOnInit();
    component.startRun();
    component.startRun();
    expect(api.startRun.mock.calls[0]).toEqual(api.startRun.mock.calls[1]);
    params.next(convertToParamMap({ id: 'p2' }));
    component.startRun();
    expect(component.project()?.id).toBe('p2');
    expect(api.startRun.mock.calls[2]).not.toEqual(api.startRun.mock.calls[0]);
  });
});
