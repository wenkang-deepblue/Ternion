/**
 * API client for Ternion Control Panel
 */

const API_BASE = '/api';

/**
 * Structured error payload returned by the backend.
 */
export interface ApiErrorPayload {
  detail?: string;
  code?: string;
  message?: string;
  provider?: string;
  model?: string;
  refresh_suggested?: boolean;
}

/**
 * Error wrapper that preserves backend response metadata.
 */
export class ApiError extends Error {
  status: number;
  code: string;
  payload: ApiErrorPayload;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message || payload.detail || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = payload.code || payload.detail || `HTTP ${status}`;
    this.payload = payload;
  }
}

/**
 * Type guard for API errors returned by the client.
 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/**
 * Basic information for a configured API key.
 */
export interface ApiKeyInfo {
  id: string;
  name: string;
  key_preview: string;
}

/**
 * Status of a specific LLM provider, including its enabled state and available keys.
 */
export interface ProviderStatus {
  enabled: boolean;
  has_keys: boolean;
  selected_key_id: string | null;
  keys: ApiKeyInfo[];
}

/**
 * Configuration for a specific AI role (e.g., Ternion members, Arbiter, Writer),
 * specifying which provider and model to use for that role.
 */
export interface RoleConfig {
  provider: string;
  model: string;
}

/**
 * Cost control settings, defining monthly spending limits and alert thresholds.
 */
export interface BudgetConfig {
  monthly_limit_usd: number;
  alert_threshold: number;
}

/**
 * Network port configuration for the backend and web services.
 */
export interface PortsConfig {
  backend: number;
  web: number;
}

/**
 * Automatic model catalog refresh schedule persisted in the backend.
 */
export interface ModelCatalogRefreshConfig {
  enabled: boolean;
  mode: 'daily' | 'interval_days' | 'interval_weeks';
  /** "HH:MM" in 24-hour format. */
  time_of_day: string;
  interval_value: number;
  /** ISO-8601 UTC timestamp of the last successful refresh. */
  last_refresh_at?: string;
  /** ISO-8601 UTC timestamp of the next scheduled refresh. */
  next_refresh_at?: string;
}

/**
 * Writable subset of model catalog refresh settings accepted by the backend.
 */
export interface ModelCatalogRefreshUpdateRequest {
  enabled?: boolean;
  mode?: ModelCatalogRefreshConfig['mode'];
  time_of_day?: string;
  interval_value?: number;
}

/**
 * Complete application configuration persisted in the backend.
 * Captures all user settings including active models, budget limits, and UI preferences.
 */
export interface Config {
  providers: Record<string, ProviderStatus>;
  roles: Record<string, RoleConfig>;
  budget: BudgetConfig;
  ports?: PortsConfig;
  model_catalog_refresh?: ModelCatalogRefreshConfig;
  execution_mode?: string;
  preferences?: {
    theme: string;
    language: string;
    browser_language?: string;
    hide_usage_disclaimer?: boolean;
    show_phase_indicators?: boolean;
  };
  updated_at?: string;
}

/**
 * Detailed token usage and cost metrics for a single provider.
 * thoughts_tokens/thoughts_cost track reasoning/chain-of-thought tokens (e.g., extended thinking).
 */
export interface ProviderDetail {
  input_tokens: number;
  output_tokens: number;
  thoughts_tokens?: number;
  input_cost?: number;
  output_cost?: number;
  thoughts_cost?: number;
}

/**
 * Aggregated usage and cost statistics for a specific date.
 */
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

/**
 * Aggregated usage and cost statistics for an entire month.
 */
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

/**
 * Comprehensive usage report for the dashboard, containing current usage,
 * budget limits, and historical breakdowns by day/month and provider.
 */
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

/**
 * Metadata for an LLM model entry in the catalog, including staleness and pricing availability.
 */
export interface ModelInfo {
  id: string;
  name: string;
  stale: boolean;
  pricing_available: boolean;
}

/**
 * Available models grouped by their respective providers.
 */
export interface ModelsData {
  models: Record<string, ModelInfo[]>;
  enabled_providers: string[];
  last_updated_at?: string;
  model_count?: number;
  catalog_initialized?: boolean;
  requires_initialization?: boolean;
  catalog_anomaly_detected?: boolean;
  catalog_anomaly_summary?: string;
  catalog_anomaly_updated_at?: string;
  catalog_anomaly_providers?: string[];
  anomaly_report_available?: boolean;
}

/**
 * Result of testing a newly added API key.
 */
export interface TestResult {
  success: boolean;
  message: string;
  code: string;
}

/**
 * Current health and operational status of the backend server.
 */
export interface ServerStatus {
  server_status: string;
  active_providers: string[];
  provider_count: number;
}

/**
 * API client responsible for all communication with the backend Server.
 * Encapsulates fetch logic, error handling, and type-safe data contracts.
 */
class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  /**
   * Internal generic method to perform fetch requests and handle JSON responses.
   * Throws an error with a unified message format upon non-2xx responses.
   */
  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw await this.buildApiError(response);
    }

    return response.json();
  }

  /**
   * Internal helper for endpoints that return plain text instead of JSON.
   */
  private async requestText(endpoint: string, options?: RequestInit): Promise<string> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        Accept: 'text/markdown',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw await this.buildApiError(response);
    }

    return response.text();
  }

  /**
   * Builds a normalized error instance from a failed HTTP response.
   * Handles JSON objects, non-object JSON (arrays/numbers), plain text, and unreadable bodies.
   */
  private async buildApiError(response: Response): Promise<ApiError> {
    let payload: ApiErrorPayload;

    try {
      const parsed: unknown = await response.clone().json();
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        payload = parsed as ApiErrorPayload;
      } else {
        payload = { detail: String(parsed) || `HTTP ${response.status}` };
      }
    } catch {
      try {
        const text = await response.text();
        payload = { detail: text || `HTTP ${response.status}` };
      } catch {
        payload = { detail: `HTTP ${response.status}` };
      }
    }

    return new ApiError(response.status, payload);
  }

  /**
   * Fetches the current application configuration.
   */
  async getConfig(): Promise<Config> {
    return this.request<Config>('/config');
  }

  /**
   * Adds and validates a new API key for the specified provider.
   */
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

  /**
   * Removes an existing API key from the given provider's configuration.
   */
  async deleteApiKey(provider: string, keyId: string): Promise<{ success: boolean; config: Config }> {
    return this.request('/api-keys/delete', {
      method: 'POST',
      body: JSON.stringify({ provider, key_id: keyId }),
    });
  }

  /**
   * Sets the active working API key for a specified provider.
   */
  async selectApiKey(
    provider: string,
    keyId: string
  ): Promise<{ success: boolean; key_name: string; config: Config }> {
    return this.request('/api-keys/select', {
      method: 'POST',
      body: JSON.stringify({ provider, key_id: keyId }),
    });
  }

  /**
   * Partially updates backend configuration settings (roles, budget, mode, preferences).
   */
  async updateConfig(config: Partial<{
    roles?: Record<string, RoleConfig>;
    budget?: Partial<BudgetConfig>;
    model_catalog_refresh?: ModelCatalogRefreshUpdateRequest;
    execution_mode?: string;
    preferences?: {
      theme?: string;
      language?: string;
      hide_usage_disclaimer?: boolean;
    };
  }>): Promise<Config> {
    const result = await this.request<{ success: boolean; config: Config }>('/config', {
      method: 'POST',
      body: JSON.stringify(config),
    });
    return result.config;
  }

  /**
   * Logs or updates the selected provider and model for a specific AI agent role.
   */
  async logRoleSelection(
    role: string,
    provider: string,
    model: string
  ): Promise<{ success: boolean; pending: boolean }> {
    return this.request('/roles/selection', {
      method: 'POST',
      body: JSON.stringify({ role, provider, model }),
    });
  }

  /**
   * Updates the global execution mode (e.g., cursor_handoff, ternion_full).
   */
  async logExecutionModeSelection(
    execution_mode: string
  ): Promise<{ success: boolean; pending: boolean }> {
    return this.request('/execution-mode/selection', {
      method: 'POST',
      body: JSON.stringify({ execution_mode }),
    });
  }

  /**
   * Retrieves aggregated usage statistics, optionally filtered by a specific month (YYYY-MM).
   */
  async getUsage(month?: string): Promise<UsageData> {
    const params = month ? `?month=${month}` : '';
    return this.request<UsageData>(`/usage${params}`);
  }

  /**
   * Conducts an immediate test API call to verify the validity of an API key.
   */
  async testProvider(provider: string, apiKey: string): Promise<TestResult> {
    return this.request<TestResult>('/test-provider', {
      method: 'POST',
      body: JSON.stringify({ provider, api_key: apiKey }),
    });
  }

  /**
   * Checks the backend server's health and the number of active/ready providers.
   */
  async getStatus(): Promise<ServerStatus> {
    return this.request<ServerStatus>('/status');
  }

  /**
   * Fetches the catalog of available models grouped by their enabled providers.
   */
  async getModels(): Promise<ModelsData> {
    return this.request<ModelsData>('/models');
  }

  /**
   * Forces the backend to initialize or refresh the LiteLLM model catalog.
   */
  async refreshModels(): Promise<ModelsData & { success: boolean }> {
    return this.request<ModelsData & { success: boolean }>('/models/refresh', {
      method: 'POST',
    });
  }

  /**
   * Retrieves the latest catalog anomaly report as Markdown.
   */
  async getModelsAnomalyReport(): Promise<string> {
    return this.requestText('/models/anomaly-report');
  }

  /**
   * Updates UI-specific settings like theme, language, and disclaimers.
   */
  async updatePreferences(prefs: {
    theme?: string;
    language?: string;
    browser_language?: string;
    hide_usage_disclaimer?: boolean;
  }): Promise<{ success: boolean; preferences: { theme: string; language: string; browser_language: string; hide_usage_disclaimer: boolean } }> {
    return this.request('/preferences', {
      method: 'PUT',
      body: JSON.stringify(prefs),
    });
  }

  /**
   * Requests the native OS to reveal a file or directory in its file manager.
   */
  async revealFile(path: string): Promise<{ success: boolean }> {
    return this.request('/reveal-file', {
      method: 'POST',
      body: JSON.stringify({ path }),
    });
  }

  /**
   * Retrieves the configured application network ports.
   */
  async getPorts(): Promise<PortsConfig> {
    return this.request<PortsConfig>('/ports');
  }

  /**
   * Updates network port allocations for backend/web services. Requires restart to apply.
   */
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

  /**
   * Exports current session logs to ~/.ternion/log.json on the server.
   */
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
