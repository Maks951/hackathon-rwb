import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { environment } from '../../environments/environment';
import { ListResponse } from './api.dto';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = environment.apiBaseUrl;

  private ensureOnline(): void {
    if (!navigator.onLine) {
      throw new Error('Offline: действие недоступно');
    }
  }

  get<T>(path: string): Observable<T> {
    return this.http.get<T>(`${this.base}${path}`);
  }

  list<T>(path: string): Observable<ListResponse<T>> {
    return this.http.get<ListResponse<T>>(`${this.base}${path}`);
  }

  post<T>(path: string, body: unknown): Observable<T> {
    try { this.ensureOnline(); } catch (e) { return throwError(() => e); }
    return this.http.post<T>(`${this.base}${path}`, body);
  }

  put<T>(path: string, body: unknown): Observable<T> {
    try { this.ensureOnline(); } catch (e) { return throwError(() => e); }
    return this.http.put<T>(`${this.base}${path}`, body);
  }

  delete<T>(path: string): Observable<T> {
    try { this.ensureOnline(); } catch (e) { return throwError(() => e); }
    return this.http.delete<T>(`${this.base}${path}`);
  }
}