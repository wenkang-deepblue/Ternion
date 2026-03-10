import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import type { Config, ModelsData } from '../api/client';
import { getTranslations } from '../i18n';
import { RoleModelConfig } from './RoleModelConfig';
import { ToastContext } from './toastContext';

const mockApi = vi.hoisted(() => ({
  getModels: vi.fn(),
  logRoleSelection: vi.fn(),
  updateConfig: vi.fn(),
  refreshModels: vi.fn(),
}));

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    api: mockApi,
    default: mockApi,
  };
});

function buildConfig(overrides?: Partial<Config>): Config {
  return {
    providers: {
      openai: {
        enabled: true,
        has_keys: true,
        selected_key_id: 'openai-1',
        keys: [],
      },
      google: {
        enabled: false,
        has_keys: false,
        selected_key_id: null,
        keys: [],
      },
      anthropic: {
        enabled: false,
        has_keys: false,
        selected_key_id: null,
        keys: [],
      },
    },
    roles: {
      ternion_a: { provider: 'openai', model: 'gpt-5.2-2025-12-11' },
      ternion_b: { provider: 'openai', model: 'gpt-5.2-2025-12-11' },
      ternion_c: { provider: 'openai', model: 'gpt-5.2-2025-12-11' },
      arbiter: { provider: 'openai', model: 'gpt-5.2-2025-12-11' },
    },
    budget: {
      monthly_limit_usd: 50,
      alert_threshold: 0.8,
    },
    execution_mode: 'cursor_handoff',
    ...overrides,
  };
}

function buildModelsData(): ModelsData {
  return {
    models: {
      openai: [
        {
          id: 'gpt-5.2-2025-12-11',
          name: 'GPT 5.2',
          stale: false,
          pricing_available: true,
        },
        {
          id: 'gpt-5.3-codex',
          name: 'GPT 5.3 Codex',
          stale: false,
          pricing_available: true,
        },
      ],
      google: [],
      anthropic: [],
    },
    enabled_providers: ['openai'],
    last_updated_at: '2026-03-08T12:00:00Z',
    model_count: 2,
    catalog_initialized: true,
    requires_initialization: false,
    catalog_anomaly_detected: false,
    catalog_anomaly_summary: '',
    catalog_anomaly_updated_at: '',
    catalog_anomaly_providers: [],
    anomaly_report_available: false,
  };
}

function renderRoleModelConfig(
  overrides: {
    config?: Config;
    modelsReloadSignal?: number;
    onConfigUpdate?: (config: Config) => void;
    onModelsReload?: () => void;
    executionMode?: string;
  } = {}
) {
  const t = getTranslations('zh');
  const showToast = vi.fn();
  const onConfigUpdate = overrides.onConfigUpdate || vi.fn();
  const onModelsReload = overrides.onModelsReload || vi.fn();

  render(
    <ToastContext.Provider value={{ showToast }}>
      <RoleModelConfig
        config={overrides.config || buildConfig()}
        onConfigUpdate={onConfigUpdate}
        onModelsReload={onModelsReload}
        t={t}
        isDarkMode={false}
        executionMode={overrides.executionMode ?? 'cursor_handoff'}
        language="zh"
        modelsReloadSignal={overrides.modelsReloadSignal ?? 0}
      />
    </ToastContext.Provider>
  );

  return { t, showToast, onConfigUpdate, onModelsReload };
}

/**
 * Finds the model <select> within the card for a given role name.
 */
async function findModelSelectForRole(roleName: string): Promise<HTMLSelectElement> {
  const heading = await screen.findByText(roleName);
  const card = heading.closest('[class*="rounded-lg"]')!;
  const selects = within(card as HTMLElement).getAllByRole('combobox');
  return selects[1] as HTMLSelectElement;
}

function getSaveButtons(label: string): HTMLButtonElement[] {
  return screen.getAllByRole('button', { name: label }) as HTMLButtonElement[];
}

describe('RoleModelConfig', () => {
  beforeEach(() => {
    mockApi.getModels.mockReset();
    mockApi.logRoleSelection.mockReset();
    mockApi.updateConfig.mockReset();
    mockApi.refreshModels.mockReset();

    mockApi.getModels.mockResolvedValue(buildModelsData());
    mockApi.logRoleSelection.mockResolvedValue({ success: true, pending: true });
  });

  it('shows retry and refresh actions when save fails with MODEL_UNAVAILABLE', async () => {
    const user = userEvent.setup();
    const unavailableError = new ApiError(400, {
      detail: 'MODEL_UNAVAILABLE',
      provider: 'openai',
      model: 'gpt-5.3-codex',
      message: 'model not found',
      refresh_suggested: true,
    });
    mockApi.updateConfig.mockRejectedValue(unavailableError);

    const { t, showToast } = renderRoleModelConfig();

    const modelSelect = await findModelSelectForRole(t.ternionAName);
    await user.selectOptions(modelSelect, 'gpt-5.3-codex');
    await waitFor(() => {
      expect(getSaveButtons(t.saveChanges)).toHaveLength(2);
    });
    await user.click(getSaveButtons(t.saveChanges)[1]);

    await waitFor(() => {
      expect(screen.getAllByText(t.code_MODEL_UNAVAILABLE).length).toBeGreaterThan(0);
    });
    expect(
      screen.getByRole('button', { name: t.modelCatalogRetry })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: t.modelCatalogRefreshNow })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.modelCatalogRetry }).className).toContain(
      'whitespace-nowrap'
    );
    expect(screen.getByRole('button', { name: t.modelCatalogRefreshNow }).className).toContain(
      'whitespace-nowrap'
    );
    expect(showToast).toHaveBeenCalledWith(t.code_MODEL_UNAVAILABLE, 'error');
  });

  it('shows raw model ids in the model select', async () => {
    const { t } = renderRoleModelConfig();

    const modelSelect = await findModelSelectForRole(t.ternionAName);
    const options = within(modelSelect).getAllByRole('option');

    expect(options.some((option) => option.textContent === 'gpt-5.2-2025-12-11')).toBe(true);
    expect(options.some((option) => option.textContent === 'gpt-5.3-codex')).toBe(true);
  });

  it('shows a floating save button after a role model change', async () => {
    const user = userEvent.setup();
    const { t } = renderRoleModelConfig();

    const modelSelect = await findModelSelectForRole(t.ternionAName);
    await user.selectOptions(modelSelect, 'gpt-5.3-codex');

    await waitFor(() => {
      expect(getSaveButtons(t.saveChanges)).toHaveLength(2);
    });

    const floatingSaveButton = getSaveButtons(t.saveChanges)[1];
    expect(floatingSaveButton.style.position).toBe('fixed');
    expect(floatingSaveButton.style.top).toBe('50%');
  });

  it('clears removed selections after refreshing the model catalog from the save error banner', async () => {
    const user = userEvent.setup();
    const unavailableError = new ApiError(400, {
      detail: 'MODEL_UNAVAILABLE',
      provider: 'openai',
      model: 'gpt-5.3-codex',
      message: 'model not found',
      refresh_suggested: true,
    });
    const refreshedModels: ModelsData = {
      ...buildModelsData(),
      models: {
        openai: [
          {
            id: 'gpt-5.2-2025-12-11',
            name: 'GPT 5.2',
            stale: false,
            pricing_available: true,
          },
        ],
        google: [],
        anthropic: [],
      },
      model_count: 1,
    };

    mockApi.updateConfig.mockRejectedValue(unavailableError);
    mockApi.refreshModels.mockResolvedValue(refreshedModels);

    const { t, showToast, onModelsReload } = renderRoleModelConfig();

    const modelSelect = await findModelSelectForRole(t.ternionAName);
    await user.selectOptions(modelSelect, 'gpt-5.3-codex');
    await waitFor(() => {
      expect(getSaveButtons(t.saveChanges)).toHaveLength(2);
    });
    await user.click(getSaveButtons(t.saveChanges)[1]);

    await screen.findByRole('button', { name: t.modelCatalogRefreshNow });
    await user.click(screen.getByRole('button', { name: t.modelCatalogRefreshNow }));

    await waitFor(() => {
      expect(modelSelect).toHaveValue('');
    });
    await waitFor(() => {
      expect(screen.getByText(t.roleConfigRemovedSelectionHint)).toBeInTheDocument();
    });
    expect(onModelsReload).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith(t.roleConfigRemovedSelectionHint, 'info');
  });

  it('calls onConfigUpdate and shows success toast on successful save', async () => {
    const user = userEvent.setup();
    const updatedConfig = buildConfig();
    mockApi.updateConfig.mockResolvedValue(updatedConfig);

    const { t, showToast, onConfigUpdate } = renderRoleModelConfig();

    const modelSelect = await findModelSelectForRole(t.ternionAName);
    await user.selectOptions(modelSelect, 'gpt-5.3-codex');
    await waitFor(() => {
      expect(getSaveButtons(t.saveChanges)).toHaveLength(2);
    });
    await user.click(getSaveButtons(t.saveChanges)[1]);

    await waitFor(() => {
      expect(onConfigUpdate).toHaveBeenCalledWith(updatedConfig);
    });
    expect(showToast).toHaveBeenCalledWith(expect.any(String), 'success');
  });

  it('resets model selection when provider is changed', async () => {
    const user = userEvent.setup();
    const config = buildConfig({
      providers: {
        openai: { enabled: true, has_keys: true, selected_key_id: 'k1', keys: [] },
        google: { enabled: true, has_keys: true, selected_key_id: 'k2', keys: [] },
        anthropic: { enabled: false, has_keys: false, selected_key_id: null, keys: [] },
      },
    });

    mockApi.getModels.mockResolvedValue({
      ...buildModelsData(),
      enabled_providers: ['openai', 'google'],
      models: {
        openai: [{ id: 'gpt-5.2-2025-12-11', name: 'GPT 5.2', stale: false, pricing_available: true }],
        google: [{ id: 'gemini-3-pro', name: 'Gemini 3 Pro', stale: false, pricing_available: true }],
        anthropic: [],
      },
    });

    renderRoleModelConfig({ config });

    const heading = await screen.findByText(getTranslations('zh').ternionAName);
    const card = heading.closest('[class*="rounded-lg"]')!;
    const selects = within(card as HTMLElement).getAllByRole('combobox');
    const providerSelect = selects[0] as HTMLSelectElement;
    const modelSelect = selects[1] as HTMLSelectElement;

    expect(providerSelect).toHaveValue('openai');
    expect(modelSelect).toHaveValue('gpt-5.2-2025-12-11');

    await user.selectOptions(providerSelect, 'google');

    await waitFor(() => {
      expect(modelSelect).toHaveValue('');
    });
  });

  it('disables writer and reviewer selects under cursor_handoff mode', async () => {
    renderRoleModelConfig({ executionMode: 'cursor_handoff' });

    const t = getTranslations('zh');
    const writerHeading = await screen.findByText(t.writerName);
    const writerCard = writerHeading.closest('[class*="rounded-lg"]')!;
    const writerSelects = within(writerCard as HTMLElement).getAllByRole('combobox');

    expect(writerSelects[0]).toBeDisabled();
    expect(writerSelects[1]).toBeDisabled();

    const reviewerHeading = screen.getByText(t.reviewerName);
    const reviewerCard = reviewerHeading.closest('[class*="rounded-lg"]')!;
    const reviewerSelects = within(reviewerCard as HTMLElement).getAllByRole('combobox');

    expect(reviewerSelects[0]).toBeDisabled();
    expect(reviewerSelects[1]).toBeDisabled();
  });
});
