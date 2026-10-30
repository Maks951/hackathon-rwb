import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { AppComponent } from './app';
import { routes } from './app.routes';

describe('Application navigation', () => {
  for (const path of ['/', '/app', '/unknown', '/login']) {
    it(`opens projects from ${path}`, async () => {
      TestBed.configureTestingModule({
        imports: [AppComponent],
        providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
      });
      const fixture = TestBed.createComponent(AppComponent);
      await TestBed.inject(Router).navigateByUrl(path);
      await fixture.whenStable();
      const http = TestBed.inject(HttpTestingController);
      http.expectOne('/api/v1/projects').flush({ items: [] });
      fixture.detectChanges();
      expect(TestBed.inject(Router).url).toBe('/app/home');
      expect(fixture.nativeElement.querySelector('h1')?.textContent).toContain('Projects');
      http.verify();
    });
  }
});
