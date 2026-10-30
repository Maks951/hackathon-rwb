import { apiErrorMessage } from '../../core/api-error';
import { Component, inject, signal, OnInit, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { ProjectDto } from '../../core/api.dto';

@Component({
  selector: 'app-project',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <section class="container py-4">
      <a routerLink="/app/home" class="btn btn-sm btn-outline-secondary mb-3">&larr; Back to projects</a>

      @if (loading()) {
        <div class="text-muted">Loading project...</div>
      } @else if (loadError()) {
        <div class="alert alert-danger">
          {{ loadError() }}
          <button class="btn btn-sm btn-outline-secondary ms-2" (click)="load()">Retry</button>
        </div>
      } @else if (project(); as p) {
        <h1 class="h3 mb-1">{{ p.name }}</h1>
        <div class="text-muted small mb-3">Created {{ p.createdAt | date:'medium' }}</div>

        <div class="card card-body mb-4">
          <div class="fw-semibold mb-2">Requirements snapshot</div>
          <pre class="mb-0" style="white-space: pre-wrap;">{{ p.requirements }}</pre>
        </div>

        <button class="btn btn-primary" (click)="startRun()" [disabled]="starting()">
          {{ starting() ? 'Starting run...' : 'Start run' }}
        </button>

        @if (startError()) {
          <div class="alert alert-danger mt-3 mb-0">{{ startError() }}</div>
        }
      }
    </section>
  `,
})
export class ProjectComponent implements OnInit {
  private destroyRef = inject(DestroyRef);
  private loadSub?: Subscription;
  private startSub?: Subscription;
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  project = signal<ProjectDto | null>(null);
  loading = signal(false);
  loadError = signal<string | null>(null);

  starting = signal(false);
  startError = signal<string | null>(null);

  // Idempotency: один ключ на пару (projectId, "попытка старта"), сбрасывается после успеха
  private idempotencyKey: string | null = null;
  private idempotencyProjectId: string | null = null;

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }

  load(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.loadError.set('Missing project id in URL.');
      return;
    }
    this.startSub?.unsubscribe();
    this.starting.set(false);
    this.startError.set(null);
    this.loadSub?.unsubscribe();
    this.project.set(null);
    this.loading.set(true);
    this.loadError.set(null);
    this.loadSub = this.api.getProject(id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: p => {
        this.project.set(p);
        this.loading.set(false);
      },
      error: err => {
        this.loadError.set(this.errMsg(err));
        this.loading.set(false);
      },
    });
  }

  startRun(): void {
    const p = this.project();
    if (!p || this.starting()) return;

    // Генерим/переиспользуем ключ ТОЛЬКО для этого проекта
    if (this.idempotencyProjectId !== p.id || !this.idempotencyKey) {
      this.idempotencyKey = crypto.randomUUID();
      this.idempotencyProjectId = p.id;
    }

    this.starting.set(true);
    this.startError.set(null);

    this.startSub = this.api.startRun(p.id, this.idempotencyKey).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: run => {
        // Успех: сбрасываем ключ, идём на страницу run
        this.idempotencyKey = null;
        this.idempotencyProjectId = null;
        this.starting.set(false);
        this.router.navigate(['/app/runs', run.id]);
      },
      error: err => {
        // Ключ НЕ сбрасываем — повтор пойдёт с тем же ключом
        this.starting.set(false);
        this.startError.set(this.errMsg(err));
      },
    });
  }

  private errMsg = apiErrorMessage;
}
