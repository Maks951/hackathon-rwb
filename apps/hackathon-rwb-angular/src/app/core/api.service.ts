import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import * as D from './api.dto';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = environment.apiBaseUrl;

  constructor() {
    if (environment.production && environment.useMock) {
      throw new Error('FATAL: useMock=true in production build. Refusing to start.');
    }
    if (environment.useMock && !environment.production) {
      console.warn('[MOCK MODE] API calls are mocked. Do not demo this build.');
    }
  }

  createProject(body: { name: string; requirements: string }): Observable<D.ProjectDto> {
    return this.http.post<D.ProjectDto>(`${this.base}/projects`, body);
  }
  listProjects(): Observable<D.ListResponse<D.ProjectDto>> {
    return this.http.get<D.ListResponse<D.ProjectDto>>(`${this.base}/projects`);
  }
  getProject(id: string): Observable<D.ProjectDto> {
    return this.http.get<D.ProjectDto>(`${this.base}/projects/${id}`);
  }
  startRun(projectId: string, idempotencyKey: string): Observable<D.RunDto> {
    const headers = new HttpHeaders({ 'Idempotency-Key': idempotencyKey });
    return this.http.post<D.RunDto>(`${this.base}/projects/${projectId}/runs`, {}, { headers });
  }
  getRun(id: string): Observable<D.RunDetailsDto> {
    return this.http.get<D.RunDetailsDto>(`${this.base}/runs/${id}`);
  }
  getEvents(runId: string, afterSequence = 0): Observable<D.EventsResponse> {
    return this.http.get<D.EventsResponse>(`${this.base}/runs/${runId}/events`, {
      params: { afterSequence: String(afterSequence) },
    });
  }
  getArtifacts(runId: string): Observable<D.ListResponse<D.ArtifactDto>> {
    return this.http.get<D.ListResponse<D.ArtifactDto>>(`${this.base}/runs/${runId}/artifacts`);
  }
  getArtifactContent(id: string): Observable<string> {
    return this.http.get(`${this.base}/artifacts/${id}/content`, { responseType: 'text' });
  }
  getDownloadUrl(runId: string): string {
    return `${this.base}/runs/${runId}/download`;
  }
}