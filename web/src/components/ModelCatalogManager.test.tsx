import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Config, ModelsData } from '../api/client';
import ZH from '../locales/zh';
import { ModelCatalogManager } from './ModelCatalogManager';
import { ToastContext } from './toastContext';

const mockApi = vi.hoisted(() => ({
  getModels: vi.fn(),
  getConfig: vi.fn(),
  updateConfig: vi.fn(),
  refreshModels: vi.fn(),
  getModelsAnomalyReport: vi.fn(),
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
      openai: { enabled: true, has_keys: true, selected_key_id: 'openai-1', keys: [] },
      google: { enabled: false, has_keys: false, selected_key_id: null, keys: [] },
      anthropic: { enabled: false, has_keys: false, selected_key_id: null, keys: [] },
    },
    roles: {},
    budget: {
      monthly_limit_usd: 50,
      alert_threshold: 0.8,
    },
    model_catalog_refresh: {
      enabled: false,
      mode: 'daily',
      time_of_day: '03:00',
      interval_value: 1,
      last_refresh_at: '',
      next_refresh_at: '',
    },
    execution_mode: 'ternion_full',
    ...overrides,
  };
}

function buildModelsData(): ModelsData {
  return {
    models: {
      openai: [],
      google: [],
      anthropic: [],
    },
    enabled_providers: ['openai'],
    last_updated_at: '2026-03-09T12:00:00Z',
    model_count: 0,
    catalog_initialized: false,
    requires_initialization: true,
    catalog_anomaly_detected: false,
    catalog_anomaly_summary: '',
    catalog_anomaly_updated_at: '',
    catalog_anomaly_providers: [],
    anomaly_report_available: false,
  };
}

function renderModelCatalogManager(config: Config = buildConfig()) {
  const t = ZH;
  const showToast = vi.fn();

  render(
    <ToastContext.Provider value={{ showToast }}>
      <ModelCatalogManager
        config={config}
        onConfigUpdate={vi.fn()}
        onModelsReload={vi.fn()}
        t={t}
        language="zh"
      />
    </ToastContext.Provider>
  );

  return { t, showToast };
}

describe('ModelCatalogManager', () => {
  beforeEach(() => {
    mockApi.getModels.mockReset();
    mockApi.getConfig.mockReset();
    mockApi.updateConfig.mockReset();
    mockApi.refreshModels.mockReset();
    mockApi.getModelsAnomalyReport.mockReset();

    mockApi.getModels.mockResolvedValue(buildModelsData());
  });

  it('shows the checkbox beside the title without the old enabled label', async () => {
    const { t } = renderModelCatalogManager();

    await waitFor(() => {
      expect(mockApi.getModels).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(t.modelCatalogScheduleTitle)).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.queryByText(t.modelCatalogScheduleEnabled)).not.toBeInTheDocument();
  });

  it('disables schedule controls when automatic refresh is unchecked', async () => {
    renderModelCatalogManager();

    await waitFor(() => {
      expect(mockApi.getModels).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByRole('combobox')).toBeDisabled();
    expect(document.querySelector('input[type="time"]')).toBeDisabled();
  });

  it('uses the short primary save button label for automatic refresh', async () => {
    const user = userEvent.setup();
    const updatedConfig = buildConfig({
      model_catalog_refresh: {
        enabled: true,
        mode: 'daily',
        time_of_day: '04:00',
        interval_value: 1,
        last_refresh_at: '',
        next_refresh_at: '',
      },
    });
    mockApi.updateConfig.mockResolvedValue(updatedConfig);

    const { t } = renderModelCatalogManager(
      buildConfig({
        model_catalog_refresh: {
          enabled: false,
          mode: 'daily',
          time_of_day: '03:00',
          interval_value: 1,
          last_refresh_at: '',
          next_refresh_at: '',
        },
      })
    );

    await waitFor(() => {
      expect(mockApi.getModels).toHaveBeenCalledTimes(1);
    });

    const checkbox = screen.getByRole('checkbox');
    await user.click(checkbox);

    const saveButton = screen.getByRole('button', { name: t.execModeSave });
    expect(saveButton.className).toContain('btn-primary');
  });

  it('switches from time input to interval input for interval schedules', async () => {
    const user = userEvent.setup();
    const { t } = renderModelCatalogManager(
      buildConfig({
        model_catalog_refresh: {
          enabled: true,
          mode: 'daily',
          time_of_day: '03:00',
          interval_value: 1,
          last_refresh_at: '',
          next_refresh_at: '',
        },
      })
    );

    await waitFor(() => {
      expect(mockApi.getModels).toHaveBeenCalledTimes(1);
    });

    await user.selectOptions(screen.getByRole('combobox'), 'interval_days');

    await waitFor(() => {
      expect(screen.getByText(t.modelCatalogScheduleInterval)).toBeInTheDocument();
    });

    expect(document.querySelector('input[type="time"]')).toBeNull();
    expect(document.querySelector('input[type="number"]')).not.toBeNull();
  });
});
