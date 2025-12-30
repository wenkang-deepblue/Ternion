/**
 * API client for Ternion Control Panel
 */

const API_BASE = '/api';

export interface ApiKeyInfo {
  id: string;
  name: string;
  key_preview: string;
}

export interface ProviderStatus {
  enabled: boolean;
  has_keys: boolean;
  selected_key_id: string | null;
  keys: ApiKeyInfo[];
}

export interface RoleConfig {
  provider: string;
  model: string;
}

export interface BudgetConfig {
  monthly_limit_usd: number;
  alert_threshold: number;
}

export interface PortsConfig {
  backend: number;
  web: number;
}

export interface Config {
  providers: Record<string, ProviderStatus>;
  roles: Record<string, RoleConfig>;
  budget: BudgetConfig;
  ports?: PortsConfig;
  preferences?: {
    theme: string;
    language: string;
    hide_usage_disclaimer?: boolean;
  };
  updated_at?: string;
}

export interface ProviderDetail {
  input_tokens: number;
  output_tokens: number;
  thoughts_tokens?: number;
  input_cost?: number;
  output_cost?: number;
  thoughts_cost?: number;
}

export interface DailyUsageRecord {
  date: string;
  cost: number;
  input_cost?: number;
  output_cost?: number;
  thoughts_cost?: number;
  input_tokens: number;
  output_tokens: number;
  thoughts_tokens: number;
  providers?: Record<string, ProviderDetail>;
}

export interface MonthlyUsageRecord {
  month: string;
  cost: number;
  input_cost?: number;
  output_cost?: number;
  thoughts_cost?: number;
  input_tokens: number;
  output_tokens: number;
  thoughts_tokens: number;
  providers?: Record<string, ProviderDetail>;
}

export interface UsageData {
  month: string;
  total_cost_usd: number;
  request_count: number;
  monthly_limit_usd: number;
  remaining_usd: number;
  usage_pct: number;
  input_tokens: number;
  output_tokens: number;
  thoughts_tokens: number;
  provider_costs: Record<string, number>;
  provider_details: Record<string, ProviderDetail>;
  daily_data: DailyUsageRecord[];
  monthly_data: MonthlyUsageRecord[];
  available_months: string[];
  available_years: string[];
}

export interface ModelInfo {
  id: string;
  name: string;
}

export interface ModelsData {
  models: Record<string, ModelInfo[]>;
  enabled_providers: string[];
}

export interface TestResult {
  success: boolean;
  message: string;
  code: string;
}

export interface ServerStatus {
  server_status: string;
  active_providers: string[];
  provider_count: number;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async getConfig(): Promise<Config> {
    return this.request<Config>('/config');
  }

  async addApiKey(
    provider: string,
    name: string,
    apiKey: string
  ): Promise<{ success: boolean; key_id: string; config: Config }> {
    return this.request('/api-keys/add', {
      method: 'POST',
      body: JSON.stringify({ provider, name, api_key: apiKey }),
    });
  }

  async deleteApiKey(provider: string, keyId: string): Promise<{ success: boolean; config: Config }> {
    return this.request('/api-keys/delete', {
      method: 'POST',
      body: JSON.stringify({ provider, key_id: keyId }),
    });
  }

  async selectApiKey(
    provider: string,
    keyId: string
  ): Promise<{ success: boolean; key_name: string; config: Config }> {
    return this.request('/api-keys/select', {
      method: 'POST',
      body: JSON.stringify({ provider, key_id: keyId }),
    });
  }

  async updateConfig(config: Partial<{
    roles?: Record<string, RoleConfig>;
    budget?: Partial<BudgetConfig>;
    preferences?: {
      theme?: string;
      language?: string;
      hide_usage_disclaimer?: boolean;
    };
  }>): Promise<{ success: boolean; config: Config }> {
    return this.request('/config', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async getUsage(month?: string): Promise<UsageData> {
    const params = month ? `?month=${month}` : '';
    return this.request<UsageData>(`/usage${params}`);
  }

  async testProvider(provider: string, apiKey: string): Promise<TestResult> {
    return this.request<TestResult>('/test-provider', {
      method: 'POST',
      body: JSON.stringify({ provider, api_key: apiKey }),
    });
  }

  async getStatus(): Promise<ServerStatus> {
    return this.request<ServerStatus>('/status');
  }

  async getModels(): Promise<ModelsData> {
    return this.request<ModelsData>('/models');
  }

  async updatePreferences(prefs: {
    theme?: string;
    language?: string;
    hide_usage_disclaimer?: boolean;
  }): Promise<{ success: boolean; preferences: { theme: string; language: string; hide_usage_disclaimer: boolean } }> {
    return this.request('/preferences', {
      method: 'PUT',
      body: JSON.stringify(prefs),
    });
  }

  async revealFile(path: string): Promise<{ success: boolean }> {
    return this.request('/reveal-file', {
      method: 'POST',
      body: JSON.stringify({ path }),
    });
  }

  async getPorts(): Promise<PortsConfig> {
    return this.request<PortsConfig>('/ports');
  }

  async updatePorts(ports: Partial<PortsConfig>): Promise<{
    success: boolean;
    ports: PortsConfig;
    restart_required: boolean;
    message: string;
  }> {
    return this.request('/ports', {
      method: 'POST',
      body: JSON.stringify(ports),
    });
  }

  async downloadLogs(): Promise<{
    success: boolean;
    file_path: string;
    log_count: number;
  }> {
    return this.request('/logs/download', {
      method: 'POST',
    });
  }
}

export const api = new ApiClient();
export default api;
