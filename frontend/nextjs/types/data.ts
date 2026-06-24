export interface BaseData {
  type: string;
}

export interface BasicData extends BaseData {
  type: 'basic';
  content: string;
}

export interface LanggraphButtonData extends BaseData {
  type: 'langgraphButton';
  link: string;
}

export interface DifferencesData extends BaseData {
  type: 'differences';
  content: string;
  output: string;
}

export interface QuestionData extends BaseData {
  type: 'question';
  content: string;
}

export interface ChatData extends BaseData {
  type: 'chat';
  content: string;
  metadata?: any; // For storing search results and other contextual information
}

export type Data = BasicData | LanggraphButtonData | DifferencesData | QuestionData | ChatData;

export interface MCPConfig {
  name: string;
  description?: string;
  enabled?: boolean; // 列表里是否勾选（控制发不发给后端）
  // HTTP/远程（智谱 MCP 走这套）
  connection_url?: string;
  connection_type?: string; // "streamable_http" | "websocket" | "stdio"
  connection_headers?: Record<string, string>;
  // stdio/本地（GitHub/文件系统走这套）
  command?: string;
  args?: string[];
  env?: Record<string, string>;
}


export interface ChatBoxSettings {
  report_type: string;
  report_source: string;
  tone: string;
  domains: string[];
  defaultReportType: string;
  layoutType: string;
  mcp_enabled: boolean;
  mcp_configs: MCPConfig[];
  mcp_strategy?: string;
}

export interface Domain {
  value: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: number;
  metadata?: any; // For storing search results and other contextual information
}

export interface ResearchHistoryItem {
  id: string;
  question: string;
  answer: string;
  timestamp: number;
  orderedData: Data[];
  chatMessages?: ChatMessage[];
  workspaceId?: string; // 归属工作区
}

// 工作区（项目式空间）
export interface Workspace {
  id: string;
  name: string;
  description?: string;
  created_at?: number;
  updated_at?: number;
}

// 工作区内的文档/资料
export interface WorkspaceDocument {
  id: string;
  workspaceId: string;
  filename: string;
  filePath: string;
  fileSize: number;
  uploadedAt: number;
} 