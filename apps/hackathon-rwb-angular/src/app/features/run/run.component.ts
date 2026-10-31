import { apiErrorMessage } from '../../core/api-error';
import { Component, inject, signal, computed, OnInit, OnDestroy, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, forkJoin, of, timer } from 'rxjs';
import { catchError, exhaustMap, timeout } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/api.service';
import {
  ArtifactDto,
  EventDto,
  RunDetailsDto,
} from '../../core/api.dto';

@Component({
  selector: 'app-run',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <section class="container py-4">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <a routerLink="/app/home" class="btn btn-sm btn-outline-secondary">&larr; Projects</a>
        @if (run(); as r) {
          <span class="text-muted small">Run {{ r.id }}</span>
        }
      </div>

      @if (loading() && !run()) {
        <div class="text-muted">Loading run...</div>
      }

      @if (initialError()) {
        <div class="alert alert-danger">
          {{ initialError() }}
          <button class="btn btn-sm btn-outline-secondary ms-2" (click)="restart()">Retry</button>
        </div>
      }

      @if (eventsError()) {
        <div class="alert alert-warning">{{ eventsError() }}
          <button class="btn btn-sm btn-outline-secondary" (click)="restart()">Retry events</button>
        </div>
      }
      @if (run(); as r) {
        <div class="card card-body mb-3">
          <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
            <div>
              <span class="badge" [ngClass]="statusBadgeClass(r.status)">{{ r.status }}</span>
              @if (r.currentStep) {
                <span class="ms-2 text-muted">step: <code>{{ r.currentStep }}</code></span>
              }
            </div>
            <div class="small text-muted">
              validation: <strong>{{ r.validationStatus }}</strong>
              · deployment: <strong>{{ r.deploymentStatus }}</strong>
            </div>
          </div>

          @if (r.error) {
            <div class="alert alert-danger mt-3 mb-0">
              <div class="fw-semibold">Run failed</div>
              <div>{{ errorMessage(r.error) }}</div>
            </div>
          }

          @if (r.finishedAt) {
            <div class="small text-muted mt-2">Finished {{ r.finishedAt | date:'medium' }}</div>
          }
        </div>

        @if (pollError()) {
          <div class="alert alert-warning">
            {{ pollError() }}
            <button class="btn btn-sm btn-outline-secondary ms-2" (click)="restart()">Retry polling</button>
          </div>
        }

        <div class="card card-body mb-3">
          <div class="fw-semibold mb-2">Steps</div>
          @if (r.steps.length === 0) {
            <div class="text-muted">
              @if (r.status === 'queued') {
                Run queued — waiting for worker.
              } @else {
                No steps reported yet.
              }
            </div>
          } @else {
            <ul class="list-unstyled mb-0">
              @for (s of r.steps; track s.id) {
                <li class="d-flex align-items-center gap-2 py-1 border-bottom">
                  <span class="badge" [ngClass]="stepBadgeClass(s.status)">{{ s.status }}</span>
                  <code>{{ s.key }}</code>
                  <span class="small text-muted">attempt {{ s.attempt }}</span>
                  @if (s.error) {
                    <span class="small text-danger ms-auto" style="max-width: 50%;">{{ errorMessage(s.error) }}</span>
                  }
                </li>
              }
            </ul>
          }
        </div>

        @if (analysisText() || designText()) {
          <div class="card card-body mb-3">
            <div class="fw-semibold mb-2">Analysis / Design</div>
            @if (analysisText()) {
              <div class="mb-2">
                <div class="small text-muted">analyze</div>
                <pre class="mb-0" style="white-space: pre-wrap; max-height: 240px; overflow: auto;">{{ analysisText() }}</pre>
              </div>
            }
            @if (designText()) {
              <div>
                <div class="small text-muted">design</div>
                <pre class="mb-0" style="white-space: pre-wrap; max-height: 240px; overflow: auto;">{{ designText() }}</pre>
              </div>
            }
          </div>
        }

        <div class="card card-body mb-3">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <div class="fw-semibold">Artifacts</div>
            @if (canDownload()) {
              <a class="btn btn-sm btn-primary" [href]="zipUrl()" download>Download ZIP</a>
            }
          </div>

          @if (artifactsLoading()) {
            <div class="text-muted">Loading artifacts...</div>
          } @else if (artifactsError()) {
            <div class="alert alert-danger mb-0">{{ artifactsError() }}
              <button class="btn btn-sm btn-outline-secondary" (click)="retryArtifacts()">Retry artifacts</button>
            </div>
          } @else if (artifacts().length === 0) {
            <div class="text-muted">No artifacts yet.</div>
          } @else {
            <div class="table-responsive">
              <table class="table table-sm align-middle mb-0">
                <thead>
                  <tr>
                    <th>Path</th>
                    <th>MIME</th>
                    <th class="text-end">Size</th>
                    <th>sha256</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  @for (a of artifacts(); track a.id) {
                    <tr>
                      <td><code>{{ a.path }}</code></td>
                      <td class="small">{{ a.mimeType }}</td>
                      <td class="text-end small">{{ a.sizeBytes }} B</td>
                      <td class="small text-muted" [title]="a.sha256">{{ shortSha(a.sha256) }}</td>
                      <td class="text-end">
                        @if (isTextArtifact(a)) {
                          <button class="btn btn-sm btn-outline-secondary" (click)="openArtifact(a)">
                            View
                          </button>
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </div>

        @if (isTerminal()) {
          <div class="d-flex gap-2">
            @if (r.status === 'failed') {
              <a class="btn btn-primary" [routerLink]="['/app/projects', r.projectId]">
                Create new run
              </a>
            }
            @if (r.repositoryUrl) {
              <a class="btn btn-outline-secondary" [href]="r.repositoryUrl" target="_blank" rel="noopener">
                Repository
              </a>
            }
            @if (r.previewUrl) {
              <a class="btn btn-outline-secondary" [href]="r.previewUrl" target="_blank" rel="noopener">
                Preview
              </a>
            }
          </div>
        }

        @if (events().length > 0) {
          <div class="card card-body mt-3">
            <div class="fw-semibold mb-2">Events</div>
            <ul class="list-unstyled mb-0 small">
              @for (e of events(); track e.id) {
                <li class="py-1 border-bottom">
                  <span class="text-muted">#{{ e.sequence }}</span>
                  <span class="badge bg-secondary ms-1">{{ e.type }}</span>
                  <span class="ms-2">{{ e.message }}</span>
                  <span class="text-muted ms-2">{{ e.createdAt | date:'mediumTime' }}</span>
                </li>
              }
            </ul>
          </div>
        }

        @if (openedArtifact(); as oa) {
          <div class="modal d-block" tabindex="-1" style="background: rgba(0,0,0,.5);" (click)="closeArtifact()">
            <div class="modal-dialog modal-lg modal-dialog-scrollable" (click)="$event.stopPropagation()">
              <div class="modal-content">
                <div class="modal-header">
                  <h5 class="modal-title"><code>{{ oa.artifact.path }}</code></h5>
                  <button type="button" class="btn-close" (click)="closeArtifact()"></button>
                </div>
                <div class="modal-body">
                  @if (oa.loading) {
                    <div class="text-muted">Loading...</div>
                  } @else if (oa.error) {
                    <div class="alert alert-danger mb-0">{{ oa.error }}</div>
                  } @else {
                    <pre class="mb-0" style="white-space: pre-wrap;">{{ oa.content }}</pre>
                  }
                </div>
              </div>
            </div>
          </div>
        }
      }
    </section>
  `,
})
export class RunComponent implements OnInit, OnDestroy {
  readonly errorMessage = apiErrorMessage;
  private destroyRef = inject(DestroyRef);
  private viewSub?: Subscription;
  private artifactSub = new Subscription();
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);

  private runId: string | null = null;
  private pollSub: Subscription | null = null;
  private lastSequence = 0;
  private artifactsLoaded = false;

  readonly run = signal<RunDetailsDto | null>(null);
  readonly loading = signal(true);
  readonly initialError = signal<string | null>(null);
  readonly pollError = signal<string | null>(null);

  readonly eventsError = signal<string | null>(null);
  readonly events = signal<EventDto[]>([]);
  readonly artifacts = signal<ArtifactDto[]>([]);
  readonly artifactsLoading = signal(false);
  readonly artifactsError = signal<string | null>(null);

  readonly analysisText = signal<string | null>(null);
  readonly designText = signal<string | null>(null);

  readonly openedArtifact = signal<{
    artifact: ArtifactDto;
    loading: boolean;
    error: string | null;
    content: string | null;
  } | null>(null);

  readonly isTerminal = computed(() => {
    const s = this.run()?.status;
    return s === 'succeeded' || s === 'failed';
  });

  readonly canDownload = computed(() => this.run()?.status === 'succeeded');

  readonly zipUrl = computed(() => {
    const r = this.run();
    // Требует proxy.conf.json в dev: /api/v1 -> http://localhost:8000
    return r ? this.api.getDownloadUrl(r.id) : '';
  });

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.runId = params.get('id');
      this.run.set(null);
      this.restart();
    });
  }

  ngOnDestroy(): void {
    this.stopPolling();
    this.closeArtifact();
    this.artifactSub.unsubscribe();
  }

  restart(): void {
    this.stopPolling();
    this.closeArtifact();
    this.artifactSub.unsubscribe();
    this.artifactSub = new Subscription();
    this.lastSequence = 0;
    this.artifactsLoaded = false;
    this.artifacts.set([]);
    this.artifactsLoading.set(false);
    this.artifactsError.set(null);
    this.events.set([]);
    this.eventsError.set(null);
    this.analysisText.set(null);
    this.designText.set(null);
    this.pollError.set(null);
    this.initialError.set(null);
    this.loading.set(true);
    if (!this.runId) {
      this.loading.set(false);
      this.initialError.set('Missing run id in URL.');
      return;
    }
    this.startPolling();
  }

  private stopPolling(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = null;
  }

  private startPolling(): void {
    const runId = this.runId!;
    this.pollSub = timer(0, 2000).pipe(
      // Skip ticks while a request is active; a hung request times out.
      exhaustMap(() => forkJoin({
        run: this.api.getRun(runId).pipe(timeout(10000)),
        events: this.api.getEvents(runId, this.lastSequence).pipe(
          timeout(10000),
          catchError(error => {
            this.eventsError.set(this.errMsg(error));
            return of(null);
          }),
        ),
      }).pipe(catchError(error => {
        this.loading.set(false);
        if (this.run()) this.pollError.set(this.errMsg(error));
        else this.initialError.set(this.errMsg(error));
        return of(null);
      }))),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(result => {
      if (!result) return;
      const { run, events } = result;
      this.loading.set(false);
      this.initialError.set(null);
      this.pollError.set(null);
      this.run.set(run);
      if (events) {
        this.eventsError.set(null);
        const seen = new Set(this.events().map(event => event.id));
        this.events.update(previous => [...previous, ...events.items.filter(event => !seen.has(event.id))]
          .sort((a, b) => a.sequence - b.sequence));
        this.lastSequence = Math.max(this.lastSequence, events.nextSequence);
      }
      if (run.status === 'succeeded' || run.status === 'failed') {
        this.stopPolling();
        if (!this.artifactsLoaded) this.loadArtifacts(runId);
      }
    });
  }

  retryArtifacts(): void {
    if (this.runId) this.loadArtifacts(this.runId);
  }

  private loadArtifacts(runId: string): void {
    this.artifactsLoading.set(true);
    this.artifactsError.set(null);
    this.artifactSub.add(this.api.getArtifacts(runId).pipe(timeout(10000), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: res => {
        this.artifacts.set(res.items);
        this.artifactsLoading.set(false);
        this.artifactsLoaded = true;
        this.loadStageTexts(res.items);
      },
      error: (err: unknown) => {
        this.artifactsError.set(this.errMsg(err));
        this.artifactsLoading.set(false);
      },
    }));
  }

  /**
   * analyze/design показываем как текст.
   * Ищем известные имена файлов по path, независимо от MIME-типа.
   */
  private loadStageTexts(items: ArtifactDto[]): void {
    const analysis = this.findArtifact(items, ['analysis.md', 'requirements.md', 'requirements.json']);
    const design = this.findArtifact(items, ['design.md', 'system.md', 'system.json']);

    if (analysis) {
      this.artifactSub.add(this.api.getArtifactContent(analysis.id).pipe(timeout(10000), takeUntilDestroyed(this.destroyRef)).subscribe({
        next: t => this.analysisText.set(t),
        error: () => { /* не критично для demo */ },
      }));
    }
    if (design) {
      this.artifactSub.add(this.api.getArtifactContent(design.id).pipe(timeout(10000), takeUntilDestroyed(this.destroyRef)).subscribe({
        next: t => this.designText.set(t),
        error: () => { /* не критично */ },
      }));
    }
  }

  private findArtifact(items: ArtifactDto[], suffixes: string[]): ArtifactDto | undefined {
    const lower = (s: string) => s.toLowerCase();
    // сначала по path
    for (const suffix of suffixes) {
      const hit = items.find(a => lower(a.path).endsWith(lower(suffix)));
      if (hit) return hit;
    }
    return undefined;
  }

  isTextArtifact(a: ArtifactDto): boolean {
    const mime = (a.mimeType || '').toLowerCase();
    const path = (a.path || '').toLowerCase();
    if (mime.startsWith('text/')) return true;
    if (mime === 'application/json') return true;
    if (mime === 'application/octet-stream') {
      // бэк может отдать .md как octet-stream — допускаем по расширению
      return /\.(md|txt|json)$/.test(path);
    }
    return /\.(md|txt|json)$/.test(path);
  }

  openArtifact(a: ArtifactDto): void {
    this.viewSub?.unsubscribe();
    this.openedArtifact.set({ artifact: a, loading: true, error: null, content: null });
    this.viewSub = this.api.getArtifactContent(a.id).pipe(timeout(10000), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: content => {
        const cur = this.openedArtifact();
        if (cur && cur.artifact.id === a.id) {
          this.openedArtifact.set({ ...cur, loading: false, content });
        }
      },
      error: (err: unknown) => {
        const cur = this.openedArtifact();
        if (cur && cur.artifact.id === a.id) {
          this.openedArtifact.set({ ...cur, loading: false, error: this.errMsg(err) });
        }
      },
    });
  }

  closeArtifact(): void {
    this.viewSub?.unsubscribe();
    this.openedArtifact.set(null);
  }

  shortSha(sha: string): string {
    return sha.length > 12 ? sha.slice(0, 12) + '…' : sha;
  }

  statusBadgeClass(status: string): string {
    switch (status) {
      case 'succeeded': return 'bg-success';
      case 'failed': return 'bg-danger';
      case 'running': return 'bg-primary';
      case 'queued': return 'bg-secondary';
      default: return 'bg-secondary';
    }
  }

  stepBadgeClass(status: string): string {
    switch (status) {
      case 'succeeded': return 'bg-success';
      case 'failed': return 'bg-danger';
      case 'running': return 'bg-primary';
      case 'pending': return 'bg-secondary';
      default: return 'bg-secondary';
    }
  }

  private errMsg = apiErrorMessage;
}
