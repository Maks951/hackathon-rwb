import { apiErrorMessage } from '../../core/api-error';
import { Component, inject, signal, OnInit, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { trimmedMinLength } from '../../core/trimmed-length.validator';
import { ApiService } from '../../core/api.service';
import { ProjectDto } from '../../core/api.dto';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  template: `
    <section class="container py-4">
      <h1 class="h3 mb-3">Projects</h1>

      <form [formGroup]="form" (ngSubmit)="onCreate()" class="card card-body mb-4">
        <div class="mb-3">
          <label class="form-label" for="name">Project name</label>
          <input id="name" class="form-control" formControlName="name" />
          @if (form.controls.name.touched && form.controls.name.invalid) {
            <div class="text-danger small">Name is required (min 2 chars).</div>
          }
        </div>
        <div class="mb-3">
          <label class="form-label" for="requirements">Business requirements</label>
          <textarea
            id="requirements"
            class="form-control"
            rows="6"
            formControlName="requirements"
            placeholder="Describe the product in natural language..."
          ></textarea>
          @if (form.controls.requirements.touched && form.controls.requirements.invalid) {
            <div class="text-danger small">Requirements are required (min 10 chars).</div>
          }
        </div>
        <button class="btn btn-primary" type="submit" [disabled]="form.invalid || creating()">
          {{ creating() ? 'Creating...' : 'Create project' }}
        </button>
        @if (createError()) {
          <div class="alert alert-danger mt-3 mb-0">{{ createError() }}</div>
        }
      </form>

      <h2 class="h5 mb-2">Existing projects</h2>

      @if (loading()) {
        <div class="text-muted">Loading projects...</div>
      } @else if (listError()) {
        <div class="alert alert-danger">
          {{ listError() }}
          <button class="btn btn-sm btn-outline-secondary ms-2" (click)="loadProjects()">Retry</button>
        </div>
      } @else if (projects().length === 0) {
        <div class="text-muted">No projects yet. Create the first one above.</div>
      } @else {
        <ul class="list-group">
          @for (p of projects(); track p.id) {
            <li class="list-group-item d-flex justify-content-between align-items-center">
              <div>
                <div class="fw-semibold">{{ p.name }}</div>
                <div class="small text-muted">{{ p.createdAt | date:'short' }}</div>
              </div>
              <a class="btn btn-sm btn-outline-primary" [routerLink]="['/app/projects', p.id]">Open</a>
            </li>
          }
        </ul>
      }
    </section>
  `,
})
export class HomeComponent implements OnInit {
  private destroyRef = inject(DestroyRef);
  private api = inject(ApiService);
  private router = inject(Router);
  private fb = inject(FormBuilder);

  form = this.fb.nonNullable.group({
    name: ['', [trimmedMinLength(2)]],
    requirements: ['', [trimmedMinLength(10)]],
  });

  projects = signal<ProjectDto[]>([]);
  loading = signal(false);
  listError = signal<string | null>(null);

  creating = signal(false);
  createError = signal<string | null>(null);

  ngOnInit(): void {
    this.loadProjects();
  }

  loadProjects(): void {
    this.loading.set(true);
    this.listError.set(null);
    this.api.listProjects().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: res => {
        this.projects.set(res.items);
        this.loading.set(false);
      },
      error: err => {
        this.listError.set(this.errMsg(err));
        this.loading.set(false);
      },
    });
  }

  onCreate(): void {
    if (this.form.invalid || this.creating()) return;
    this.creating.set(true);
    this.createError.set(null);
    const { name, requirements } = this.form.getRawValue();
    this.api.createProject({ name: name.trim(), requirements: requirements.trim() }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: project => {
        this.creating.set(false);
        this.form.reset({ name: '', requirements: '' });
        this.router.navigate(['/app/projects', project.id]);
      },
      error: err => {
        this.creating.set(false);
        this.createError.set(this.errMsg(err));
      },
    });
  }

  private errMsg = apiErrorMessage;
}
