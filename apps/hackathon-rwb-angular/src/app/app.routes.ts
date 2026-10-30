import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: '/app/home', pathMatch: 'full' },
  {
    path: 'app',
    loadComponent: () => import('./features/layout/layout.component').then(m => m.LayoutComponent),
    children: [
      { path: '', redirectTo: 'home', pathMatch: 'full' },
      { path: 'home', loadComponent: () => import('./features/home/home.component').then(m => m.HomeComponent) },
      { path: 'projects/:id', loadComponent: () => import('./features/project/project.component').then(m => m.ProjectComponent) },
      { path: 'runs/:id', loadComponent: () => import('./features/run/run.component').then(m => m.RunComponent) },
    ],
  },
  { path: '**', redirectTo: '/app/home' },
];
