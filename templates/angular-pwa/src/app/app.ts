import { Component, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { SwUpdate, VersionReadyEvent } from '@angular/service-worker';
import { filter } from 'rxjs/operators';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, CommonModule],
  template: `
    @if (updateAvailable()) {
      <div class="update-banner">
        Доступна новая версия.
        <button class="btn btn-sm btn-light ms-2" (click)="reload()">Обновить</button>
      </div>
    }
    @if (!online()) {
      <div class="offline-banner">
        Нет сети. Действия недоступны.
      </div>
    }
    <router-outlet />
  `,
  styles: [`
    .update-banner, .offline-banner {
      position: sticky; top: 0; z-index: 1000;
      padding: 8px 12px; text-align: center; font-weight: 600;
    }
    .update-banner { background: #1976d2; color: #fff; }
    .offline-banner { background: #ffc107; color: #000; }
  `],
})
export class AppComponent {
  private swUpdate = inject(SwUpdate);

  updateAvailable = signal(false);
  online = signal(navigator.onLine);

  constructor() {
    if (this.swUpdate.isEnabled) {
      this.swUpdate.versionUpdates
        .pipe(filter((e): e is VersionReadyEvent => e.type === 'VERSION_READY'))
        .subscribe(() => this.updateAvailable.set(true));
    }
    window.addEventListener('online', () => this.online.set(true));
    window.addEventListener('offline', () => this.online.set(false));
  }

  reload(): void {
    this.swUpdate.activateUpdate().then(() => document.location.reload());
  }
}