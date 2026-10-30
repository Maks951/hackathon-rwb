import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <nav class="navbar navbar-expand navbar-dark bg-dark px-3">
      <a class="navbar-brand" routerLink="/app/home">Platform</a>
      <ul class="navbar-nav me-auto">
        <li class="nav-item">
          <a
            class="nav-link"
            routerLink="/app/home"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
          >Projects</a>
        </li>
      </ul>
    </nav>

    <main class="app-main">
      <router-outlet />
    </main>
  `,
  styles: [`
    .app-main {
      min-height: calc(100vh - 56px);
      background: #f8f9fa;
    }
  `],
})
export class LayoutComponent {}