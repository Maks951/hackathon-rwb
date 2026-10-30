import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: '/login', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login.component').then(m => m.LoginComponent),
  },
  {
    path: 'app',
    canActivate: [authGuard], // защита: без токена не пустит
    loadComponent: () => import('./features/layout/layout.component').then(m => m.LayoutComponent),
    children: [
      {
        path: 'home',
        loadComponent: () => import('./features/home/home.component').then(m => m.HomeComponent),
      },
      {
        path: 'projects/:id',
        loadComponent: () => import('./features/project/project.component').then(m => m.ProjectComponent),
      },
      {
        path: 'runs/:id',
        loadComponent: () => import('./features/run/run.component').then(m => m.RunComponent),
      },
    ],
  },
  { path: '**', redirectTo: '/login' },
];