import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import type { PortsConfig, PublicAccessStatus } from '../api/client';
import { getTranslations } from '../i18n';
import { PortsSettings } from './PortsSettings';
import { ToastContext } from './toastContext';

const mockApi = vi.hoisted(() => ({
  getPorts: vi.fn(),
  updatePorts: vi.fn(),
  updatePublicAccess: vi.fn(),
}));

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    api: mockApi,
    default: mockApi,
  };
});

function buildPorts(overrides?: Partial<PortsConfig>): PortsConfig {
  return {
    backend: 9110,
    web: 9120,
    ...overrides,
  };
}

function buildPublicAccess(overrides?: Partial<PublicAccessStatus>): PublicAccessStatus {
  return {
    mode: 'local_tunnel',
    deployment_environment: 'local',
    detection_method: 'manual_config',
    detected_public_base_url: '',
    configured_public_base_url: 'https://demo.ngrok.app',
    effective_public_base_url: 'https://demo.ngrok.app',
    effective_source: 'config',
    cursor_override_base_url: 'https://demo.ngrok.app',
    configured: true,
    requires_public_url: true,
    ...overrides,
  };
}

function renderPortsSettings(overrides?: {
  publicAccess?: PublicAccessStatus | null;
  publicAccessReady?: boolean;
}) {
  const t = getTranslations('zh');
  const showToast = vi.fn();
  const onPublicAccessUpdate = vi.fn();

  const utils = render(
    <ToastContext.Provider value={{ showToast }}>
      <PortsSettings
        t={t}
        isDarkMode={false}
        language="zh"
        publicAccess={overrides?.publicAccess ?? buildPublicAccess()}
        publicAccessReady={overrides?.publicAccessReady ?? true}
        onPublicAccessUpdate={onPublicAccessUpdate}
      />
    </ToastContext.Provider>
  );

  return { t, showToast, onPublicAccessUpdate, ...utils };
}

describe('PortsSettings', () => {
  beforeEach(() => {
    mockApi.getPorts.mockReset();
    mockApi.updatePorts.mockReset();
    mockApi.updatePublicAccess.mockReset();
    mockApi.getPorts.mockResolvedValue(buildPorts());
  });

  it('shows the cursor base URL without appending /v1 and renders the copy button', async () => {
    const { t } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByRole('button', { name: t.publicAccessCopy })).toBeInTheDocument();
    expect(screen.getAllByText('https://demo.ngrok.app')).not.toHaveLength(0);
    expect(screen.queryByText('https://demo.ngrok.app/v1')).not.toBeInTheDocument();
  });

  it('shows loading first and then renders an unavailable warning when port loading fails', async () => {
    mockApi.getPorts.mockRejectedValueOnce(
      new ApiError(503, { code: 'CONNECTION_ERROR', detail: 'CONNECTION_ERROR' })
    );

    const { t } = renderPortsSettings();

    expect(screen.getByText(t.loading)).toBeInTheDocument();

    expect(await screen.findByText(t.code_CONNECTION_ERROR)).toBeInTheDocument();
    expect(screen.queryByText(t.portsCurrentBackend)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.saveChanges })).not.toBeInTheDocument();
  });

  it('saves the public access form and propagates the updated state', async () => {
    const user = userEvent.setup();
    const updatedState = buildPublicAccess({
      mode: 'cloud_run',
      configured_public_base_url: 'https://ternion.run.app',
      effective_public_base_url: 'https://ternion.run.app',
      cursor_override_base_url: 'https://ternion.run.app',
    });
    mockApi.updatePublicAccess.mockResolvedValue({
      success: true,
      ...updatedState,
    });

    const { t, showToast, onPublicAccessUpdate } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.selectOptions(screen.getByRole('combobox'), 'cloud_run');

    const urlInput = screen.getByPlaceholderText(t.publicAccessUrlPlaceholder);
    await user.clear(urlInput);
    await user.type(urlInput, 'https://ternion.run.app');

    await user.click(screen.getByRole('button', { name: t.saveChanges }));

    expect(mockApi.updatePublicAccess).toHaveBeenCalledWith({
      mode: 'cloud_run',
      public_base_url: 'https://ternion.run.app',
    });
    expect(onPublicAccessUpdate).toHaveBeenCalledWith(expect.objectContaining(updatedState));
    expect(showToast).toHaveBeenCalledWith(t.publicAccessSaved, 'success');
  });

  it.each(['https://ternion.run.app/v1/', 'https://ternion.run.app/v1'])(
    'renders the canonical root URL after saving legacy value %s',
    async (legacyValue) => {
      const user = userEvent.setup();
      const updatedState = buildPublicAccess({
        mode: 'custom',
        configured_public_base_url: 'https://ternion.run.app',
        effective_public_base_url: 'https://ternion.run.app',
        cursor_override_base_url: 'https://ternion.run.app',
      });
      mockApi.updatePublicAccess.mockResolvedValue({
        success: true,
        ...updatedState,
      });

      const { t, showToast, onPublicAccessUpdate } = renderPortsSettings();

      await waitFor(() => {
        expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
      });

      await user.selectOptions(screen.getByRole('combobox'), 'custom');

      const urlInput = screen.getByPlaceholderText(t.publicAccessUrlPlaceholder);
      await user.clear(urlInput);
      await user.type(urlInput, legacyValue);

      await user.click(screen.getByRole('button', { name: t.saveChanges }));

      await waitFor(() => {
        expect(mockApi.updatePublicAccess).toHaveBeenCalledWith({
          mode: 'custom',
          public_base_url: legacyValue,
        });
        expect(onPublicAccessUpdate).toHaveBeenCalledWith(
          expect.objectContaining(updatedState)
        );
        expect(showToast).toHaveBeenCalledWith(t.publicAccessSaved, 'success');
        expect(screen.getByDisplayValue('https://ternion.run.app')).toBeInTheDocument();
        expect(
          screen.queryByDisplayValue('https://ternion.run.app/v1')
        ).not.toBeInTheDocument();
        expect(
          screen.queryByDisplayValue('https://ternion.run.app/v1/')
        ).not.toBeInTheDocument();
      });
    }
  );

  it('shows a localized error toast when public access saving fails', async () => {
    const user = userEvent.setup();
    mockApi.updatePublicAccess.mockRejectedValue(
      new ApiError(400, {
        code: 'INVALID_PUBLIC_BASE_URL',
        detail: 'INVALID_PUBLIC_BASE_URL',
        message: 'public https url is invalid',
      })
    );

    const { t, showToast } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.selectOptions(screen.getByRole('combobox'), 'custom');
    await user.click(screen.getByRole('button', { name: t.saveChanges }));

    await waitFor(() => {
      expect(showToast).toHaveBeenCalledWith(t.code_INVALID_PUBLIC_BASE_URL, 'error');
    });
  });

  it('shows a localized error toast when port saving fails', async () => {
    const user = userEvent.setup();
    mockApi.updatePorts.mockRejectedValue(
      new ApiError(400, {
        code: 'CONNECTION_ERROR',
        detail: 'CONNECTION_ERROR',
        message: 'network request failed',
      })
    );

    const { t, showToast } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    const backendInput = screen.getAllByRole('spinbutton')[0];
    fireEvent.change(backendInput, { target: { value: '9111' } });
    await user.click(screen.getByRole('button', { name: t.saveChanges }));

    await waitFor(() => {
      expect(showToast).toHaveBeenCalledWith(t.code_CONNECTION_ERROR, 'error');
    });
  });

  it('shows loading and unavailable states for public access', async () => {
    const { t, rerender } = renderPortsSettings({
      publicAccess: null,
      publicAccessReady: false,
    });

    expect(screen.getAllByText(t.loading)).not.toHaveLength(0);

    rerender(
      <ToastContext.Provider value={{ showToast: vi.fn() }}>
        <PortsSettings
          t={t}
          isDarkMode={false}
          language="zh"
          publicAccess={null}
          publicAccessReady
          onPublicAccessUpdate={vi.fn()}
        />
      </ToastContext.Provider>
    );

    expect(await screen.findByText(t.publicAccessUnavailable)).toBeInTheDocument();
  });

  it('hides the copy button and shows a missing badge when no cursor URL is available', async () => {
    const { t } = renderPortsSettings({
      publicAccess: buildPublicAccess({
        configured_public_base_url: '',
        effective_public_base_url: '',
        effective_source: 'none',
        cursor_override_base_url: '',
        configured: false,
      }),
    });

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.queryByRole('button', { name: t.publicAccessCopy })).not.toBeInTheDocument();
    expect(screen.getAllByText(t.publicAccessStatusMissing)).not.toHaveLength(0);
  });
});
