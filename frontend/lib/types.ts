// 与后端 schema 对应的前端类型。

export interface UserPublic {
  id: string;
  email: string;
  role: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: string;
}

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  role_in_ws: string;
}

export interface Category {
  id: string;
  workspace_id: string;
  name: string;
  parent_id: string | null;
}

export interface DocumentPublic {
  id: string;
  workspace_id: string;
  title: string;
  mime_type: string;
  category_id: string | null;
  summary: string | null;
  tags: string[];
  status: string;
  created_at: string;
}

export interface ProcessingTask {
  id: string;
  document_id: string;
  kind: string;
  status: string;
  attempts: number;
  max_attempts: number;
  error: string | null;
  logs: unknown[];
  created_at: string;
  updated_at: string;
}

export interface SourceRef {
  doc_id: string;
  title: string;
  download_url: string;
}

export interface ChatResponse {
  answer: string;
  sources: SourceRef[];
  conversation_id: string;
}
