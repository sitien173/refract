export type JobState =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'interrupted';

export interface DaemonStatus {
  status: 'running' | 'stopping';
  workers: number;
  active_jobs: number;
  queued_jobs: number;
}

export interface Project {
  id: string;
  alias: string;
  root: string;
  head_commit: string;
  clean: boolean;
  created_at: string;
}

export interface JobResult {
  text: string;
  commit: string;
  error: string;
}

export interface Job {
  id: string;
  project_id: string;
  workflow: string;
  profile: string;
  state: JobState;
  context_key: string;
  base_commit: string;
  target_id: string;
  attempts: number;
  created_at: string;
  updated_at: string;
  result: JobResult;
}

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonArray;
export interface JsonObject {
  [key: string]: JsonValue;
}
export type JsonArray = JsonValue[];

export interface JobEvent {
  id: number;
  created_at: string;
  kind: string;
  data: JsonObject;
}

export interface Target {
  id: string;
  model: string;
  capabilities: string[];
  max_concurrency: number;
  active: number;
  healthy: boolean;
  circuit_open_until: string;
}

export interface ProfilesResponse {
  default: string;
  available: string[];
}
