import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="d-flex" style="min-height: 100vh;">
      <aside class="bg-dark text-white p-3" style="width: 240px;">
        <h5 class="mb-3">Admin</h5>
        <ul class="nav flex-column">
          <li class="nav-item">
            <a class="nav-link text-white" routerLink="/dashboard" routerLinkActive="fw-bold">Dashboard</a>
          </li>
          <!-- QWEN: доменные ссылки добавляются здесь -->
        </ul>
      </aside>
      <main class="flex-grow-1 p-4 bg-light">
        <router-outlet />
      </main>
    </div>
  `,
})
export class LayoutComponent {}