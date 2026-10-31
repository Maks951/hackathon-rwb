export interface ProjectDto {
  id: string;
  name: string;
  requirements: string;
  createdAt: string;
}

export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed';
export type StepStatus = 'pending' | 'running' | 'succeeded' | 'failed';
export type ValidationStatus = 'pending' | 'passed' | 'failed';
export type DeploymentStatus = 'pending' | 'skipped' | 'deployed' | 'failed';

export interface RunDto {
  id: string;
  projectId: string;
  status: RunStatus;
  currentStep: string | null;
  error: ApiError | string | null;
  repositoryUrl: string | null;
  previewUrl: string | null;
  createdAt: string;
  finishedAt: string | null;
}

export interface StepDto {
  id: string;
  key: string;
  attempt: number;
  status: StepStatus;
  error: ApiError | string | null;
}

export interface RunDetailsDto extends RunDto {
  steps: StepDto[];
  validationStatus: ValidationStatus;
  deploymentStatus: DeploymentStatus;
}

export interface EventDto {
  id: string;
  sequence: number;
  type: string;
  message: string;
  createdAt: string;
}

export interface ArtifactDto {
  id: string;
  path: string;
  mimeType: string;
  sizeBytes: number;
  sha256: string;
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

export interface ListResponse<T> { items: T[]; }
export interface EventsResponse { items: EventDto[]; nextSequence: number; }
