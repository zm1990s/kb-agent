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

export interface AllowedDomain {
  id: string;
  domain: string;
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
  folder_id: string | null;
  category_id: string | null;
  brief: string | null;
  summary: string | null;
  tags: string[];
  status: string;
  created_at: string;
  deleted_at?: string | null;
  content_text: string | null;
}

export interface Folder {
  id: string;
  workspace_id: string;
  name: string;
  parent_id: string | null;
}

export interface TaskLog {
  stage: string;
  message: string;
  at: string;
}

export interface ProcessingTask {
  id: string;
  document_id: string;
  kind: string;
  status: string;
  attempts: number;
  max_attempts: number;
  error: string | null;
  logs: TaskLog[];
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

export interface ConversationSummary {
  id: string;
  workspace_id: string;
  title: string | null;
  pinned: boolean;
  created_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceRef[];
  created_at: string;
}

export interface ConversationHistory {
  conversation_id: string;
  messages: Message[];
}
