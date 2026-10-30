import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./layout/layout.component').then(m => m.LayoutComponent),
    children: [
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
      },
      // === QWEN: доменные маршруты добавляются здесь ===
      // {
      //   path: 'zones',
      //   loadComponent: () => import('./features/zones/zones.component').then(m => m.ZonesComponent),
      // },
    ],
  },
  { path: '**', redirectTo: '' },
];