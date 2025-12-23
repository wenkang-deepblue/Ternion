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

export interface Config {
  providers: Record<string, ProviderStatus>;
  roles: Record<string, RoleConfig>;
  budget: BudgetConfig;
  updated_at?: string;
}

export interface UsageData {
  month: string;
  total_cost_usd: number;
  request_count: number;
  monthly_limit_usd: number;
  remaining_usd: number;
  usage_pct: number;
  provider_costs: Record<string, number>;
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
  }>): Promise<{ success: boolean; config: Config }> {
    return this.request('/config', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async getUsage(): Promise<UsageData> {
    return this.request<UsageData>('/usage');
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
}

export const api = new ApiClient();
export default api;
