import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { BehaviorSubject, NEVER, of, throwError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiService } from '../../core/api.service';
import { RunDetailsDto } from '../../core/api.dto';
import { RunComponent } from './run.component';

const run = (status: RunDetailsDto['status']): RunDetailsDto => ({
  id: 'run-1', projectId: 'project-1', status, currentStep: null, error: null,
  repositoryUrl: null, previewUrl: null, createdAt: '', finishedAt: null,
  steps: [], validationStatus: 'pending', deploymentStatus: 'pending',
});

describe('Run monitoring', () => {
  let component: RunComponent;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let api: { getRun: ReturnType<typeof vi.fn>; getEvents: ReturnType<typeof vi.fn>;
    getArtifacts: ReturnType<typeof vi.fn>; getDownloadUrl: ReturnType<typeof vi.fn>; };
  beforeEach(() => {
    vi.useFakeTimers();
    params = new BehaviorSubject(convertToParamMap({ id: 'run-1' }));
    api = {
      getRun: vi.fn(() => of(run('running'))),
      getEvents: vi.fn(() => of({ items: [], nextSequence: 0 })),
      getArtifacts: vi.fn(() => of({ items: [] })),
      getDownloadUrl: vi.fn(() => '/download'),
    };
    TestBed.configureTestingModule({ providers: [
      { provide: ApiService, useValue: api },
      { provide: ActivatedRoute, useValue: { paramMap: params } },
    ] });
    component = TestBed.runInInjectionContext(() => new RunComponent());
    component.ngOnInit();
  });
  afterEach(() => {
    component.ngOnDestroy();
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });
  it('stops polling on completion and loads artifacts even for a failed run', async () => {
    api.getRun.mockReturnValue(of(run('failed')));
    await vi.advanceTimersByTimeAsync(0);
    expect(component.run()?.status).toBe('failed');
    expect(api.getArtifacts).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(6000);
    expect(api.getRun).toHaveBeenCalledOnce();
  });
  it('times out a hanging request and recovers on a later tick', async () => {
    api.getRun.mockReturnValue(NEVER);
    await vi.advanceTimersByTimeAsync(10000);
    expect(component.initialError()).toContain('10 seconds');
    api.getRun.mockReturnValue(of(run('running')));
    await vi.advanceTimersByTimeAsync(12000);
    expect(component.run()?.status).toBe('running');
    expect(component.initialError()).toBeNull();
  });
  it('does not overlap slow requests', async () => {
    api.getRun.mockReturnValue(NEVER);
    await vi.advanceTimersByTimeAsync(8000);
    expect(api.getRun).toHaveBeenCalledOnce();
  });
  it('reports event errors while preserving the run result', async () => {
    api.getRun.mockReturnValue(of(run('succeeded')));
    api.getEvents.mockReturnValue(throwError(() => new Error('unavailable')));
    await vi.advanceTimersByTimeAsync(0);
    expect(component.run()?.status).toBe('succeeded');
    expect(component.eventsError()).toBeTruthy();
  });
  it('retries artifact loading after failure', async () => {
    api.getRun.mockReturnValue(of(run('succeeded')));
    api.getArtifacts.mockReturnValueOnce(throwError(() => new Error('unavailable')));
    await vi.advanceTimersByTimeAsync(0);
    expect(component.artifactsError()).toBeTruthy();
    component.retryArtifacts();
    expect(component.artifactsError()).toBeNull();
    expect(api.getArtifacts).toHaveBeenCalledTimes(2);
  });
  it('reloads when the route changes and cancels polling on destroy', async () => {
    await vi.advanceTimersByTimeAsync(0);
    params.next(convertToParamMap({ id: 'run-2' }));
    await vi.advanceTimersByTimeAsync(0);
    expect(api.getRun).toHaveBeenLastCalledWith('run-2');
    component.ngOnDestroy();
    await vi.advanceTimersByTimeAsync(6000);
    expect(api.getRun).toHaveBeenCalledTimes(2);
  });
});
