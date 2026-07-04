import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import type { PortsConfig, PublicAccessStatus } from '../api/client';
import { getTranslations } from '../i18n';
import { PortsSettings } from './PortsSettings';

const REPOSITORY_BLOB_URL = 'https://github.com/wenkang-deepblue/Ternion/blob/main';
const LOCAL_TUNNEL_DOC_URL = `${REPOSITORY_BLOB_URL}/public_tunnel_configuration.md`;
const GITHUB_DOCS_URL = `${REPOSITORY_BLOB_URL}/README.md`;
import { ToastContext } from './toastContext';

const mockApi = vi.hoisted(() => ({
  getPorts: vi.fn(),
  updatePorts: vi.fn(),
  updatePublicAccess: vi.fn(),
  getAuthToken: vi.fn(),
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
  const publicAccess: PublicAccessStatus | null =
    overrides && 'publicAccess' in overrides
      ? (overrides.publicAccess ?? null)
      : buildPublicAccess();

  const utils = render(
    <ToastContext.Provider value={{ showToast }}>
      <PortsSettings
        t={t}
        isDarkMode={false}
        language="zh"
        publicAccess={publicAccess}
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
    mockApi.getAuthToken.mockReset();
    mockApi.getPorts.mockResolvedValue(buildPorts());
    mockApi.getAuthToken.mockResolvedValue({ auth_token: 'test-access-token' });
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

  it('renders the access token row masked with its own copy button', async () => {
    const { t } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getAuthToken).toHaveBeenCalledTimes(1);
    });

    // Only the first six characters are shown; the full token never
    // appears in the DOM.
    expect(await screen.findByText(`test-a${'•'.repeat(12)}`)).toBeInTheDocument();
    expect(screen.queryByText('test-access-token')).not.toBeInTheDocument();
    const tokenCopyLabel = `${t.publicAccessTokenLabel}: ${t.publicAccessCopy}`;
    expect(screen.getByRole('button', { name: tokenCopyLabel })).toBeInTheDocument();
  });

  it('always shows deployment, detected URL, cursor URL, and source rows', async () => {
    const { t } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(t.publicAccessDeploymentEnvironment)).toBeInTheDocument();
    expect(screen.getByText(t.publicAccessDetectedPublicUrl)).toBeInTheDocument();
    expect(screen.getByText(t.publicAccessCursorUrl)).toBeInTheDocument();
    expect(screen.getByText(t.publicAccessSource)).toBeInTheDocument();
    expect(screen.getByText(t.publicAccessDeploymentEnvironmentLocal)).toBeInTheDocument();
    expect(screen.getAllByText('https://demo.ngrok.app')).not.toHaveLength(0);
    expect(screen.getByText(t.publicAccessSourceConfig)).toBeInTheDocument();
  });

  it('shows the auto-detected note for ngrok-discovered public URLs', async () => {
    const { t } = renderPortsSettings({
      publicAccess: buildPublicAccess({
        detection_method: 'ngrok_api',
        detected_public_base_url: 'https://live.ngrok.app',
        effective_public_base_url: 'https://live.ngrok.app',
        effective_source: 'ngrok_api',
        cursor_override_base_url: 'https://live.ngrok.app',
      }),
    });

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(t.publicAccessAutoDetectedNote)).toBeInTheDocument();
  });

  it('shows the Cloud Run deployment label when the backend reports cloud_run', async () => {
    const { t } = renderPortsSettings({
      publicAccess: buildPublicAccess({
        deployment_environment: 'cloud_run',
        detection_method: 'request_origin',
        detected_public_base_url: 'https://ternion.run.app',
        effective_public_base_url: 'https://ternion.run.app',
        effective_source: 'request_origin',
        cursor_override_base_url: 'https://ternion.run.app',
      }),
    });

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(t.publicAccessDeploymentEnvironmentCloudRun)).toBeInTheDocument();
    expect(screen.getAllByText('https://ternion.run.app')).not.toHaveLength(0);
  });

  it('hides the manual fallback form when an auto-detected URL is available', async () => {
    const { t } = renderPortsSettings({
      publicAccess: buildPublicAccess({
        detection_method: 'request_origin',
        detected_public_base_url: 'https://ternion.run.app',
        effective_public_base_url: 'https://ternion.run.app',
        effective_source: 'request_origin',
        cursor_override_base_url: 'https://ternion.run.app',
      }),
    });

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.queryByText(t.publicAccessManualFallbackTitle)).not.toBeInTheDocument();
    expect(screen.queryByText(t.publicAccessDocsTitle)).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(t.publicAccessUrlPlaceholder)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.saveChanges })).not.toBeInTheDocument();
  });

  it('shows the manual fallback guidance when no auto-detected URL is available', async () => {
    const { t } = renderPortsSettings({
      publicAccess: buildPublicAccess({
        detected_public_base_url: '',
        effective_public_base_url: '',
        effective_source: 'none',
        cursor_override_base_url: '',
        configured: false,
      }),
    });

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(t.publicAccessManualFallbackTitle)).toBeInTheDocument();
    expect(screen.getByText(t.publicAccessManualFallbackDescription)).toBeInTheDocument();
    expect(screen.getByText(t.publicAccessManualFallbackHint)).toBeInTheDocument();
    expect(screen.getByText(t.publicAccessDetectedPublicUrlUnavailable)).toBeInTheDocument();
    expect(screen.getByText(t.publicAccessDocsTitle)).toBeInTheDocument();
    expect(screen.getByText(t.publicAccessDocsDescription)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: t.publicAccessDocsLocalTunnel })
    ).toHaveAttribute('href', LOCAL_TUNNEL_DOC_URL);
    expect(
      screen.getByRole('link', { name: t.publicAccessDocsLocalTunnel })
    ).toHaveAttribute('target', '_blank');
    expect(
      screen.getByRole('link', { name: t.publicAccessDocsLocalTunnel })
    ).toHaveAttribute('rel', 'noreferrer');
    expect(
      screen.queryByRole('link', { name: t.publicAccessDocsCloudRun })
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: t.publicAccessDocsGitHub })).toHaveAttribute(
      'href',
      GITHUB_DOCS_URL
    );
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(t.publicAccessUrlPlaceholder)).toBeInTheDocument();
  });

  it('shows the documentation entry points when Cloud Run has no detected public URL yet', async () => {
    const { t } = renderPortsSettings({
      publicAccess: buildPublicAccess({
        mode: 'cloud_run',
        deployment_environment: 'cloud_run',
        detected_public_base_url: '',
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

    expect(screen.getAllByText(t.publicAccessDeploymentEnvironmentCloudRun)).not.toHaveLength(0);
    expect(screen.getByText(t.publicAccessDetectedPublicUrlUnavailable)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: t.publicAccessDocsLocalTunnel })
    ).toHaveAttribute('href', LOCAL_TUNNEL_DOC_URL);
    expect(
      screen.queryByRole('link', { name: t.publicAccessDocsCloudRun })
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: t.publicAccessDocsGitHub })).toHaveAttribute(
      'href',
      GITHUB_DOCS_URL
    );
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

  it('keeps backend and web port editing inside collapsed advanced settings by default', async () => {
    const { t } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(t.portsCurrentBackend)).toBeInTheDocument();
    expect(screen.getByText(t.portsCurrentWeb)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.portsShowAdvancedSettings })).toBeInTheDocument();
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.getByText('http://localhost:9120')).toBeInTheDocument();
  });

  it('toggles the advanced settings button label and both port inputs', async () => {
    const user = userEvent.setup();
    const { t } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    const toggleButton = screen.getByRole('button', { name: t.portsShowAdvancedSettings });
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();

    await user.click(toggleButton);
    expect(
      screen.getByRole('button', { name: t.portsHideAdvancedSettings })
    ).toBeInTheDocument();
    expect(screen.getAllByRole('spinbutton')).toHaveLength(2);
    expect(screen.getByText(t.portsBackend)).toBeInTheDocument();
    expect(screen.getByText(t.portsWeb)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: t.portsHideAdvancedSettings }));
    expect(
      screen.getByRole('button', { name: t.portsShowAdvancedSettings })
    ).toBeInTheDocument();
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  });

  it('preserves edited backend and web ports across advanced settings collapse and expand', async () => {
    const user = userEvent.setup();
    const { t } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    const [backendInput, webInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(backendInput, { target: { value: '9111' } });
    fireEvent.change(webInput, { target: { value: '9210' } });

    await user.click(screen.getByRole('button', { name: t.portsHideAdvancedSettings }));
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    expect(screen.getByDisplayValue('9111')).toBeInTheDocument();
    expect(screen.getByDisplayValue('9210')).toBeInTheDocument();
  });

  it('shows the port save button only after backend or web ports change', async () => {
    const user = userEvent.setup();
    const { t } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    expect(screen.queryByRole('button', { name: t.saveChanges })).not.toBeInTheDocument();

    const [, webInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(webInput, { target: { value: '9210' } });
    expect(screen.getByRole('button', { name: t.saveChanges })).toBeInTheDocument();

    fireEvent.change(webInput, { target: { value: '9120' } });
    expect(screen.queryByRole('button', { name: t.saveChanges })).not.toBeInTheDocument();
  });

  it('disables port editing in Cloud Run environments', async () => {
    const { t } = renderPortsSettings({
      publicAccess: buildPublicAccess({
        deployment_environment: 'cloud_run',
      }),
    });

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(t.portsCloudRunManaged)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.portsShowAdvancedSettings })).not.toBeInTheDocument();
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.saveChanges })).not.toBeInTheDocument();
  });

  it('keeps local advanced port settings available when public access is unavailable', async () => {
    const { t } = renderPortsSettings({
      publicAccess: null,
      publicAccessReady: true,
    });

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(t.publicAccessUnavailable)).toBeInTheDocument();
    expect(screen.getByText(t.portsCurrentBackend)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.portsShowAdvancedSettings })).toBeInTheDocument();
    expect(screen.queryByText(t.publicAccessDocsTitle)).not.toBeInTheDocument();
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

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));

    const [backendInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(backendInput, { target: { value: '9111' } });
    await user.click(screen.getByRole('button', { name: t.saveChanges }));
    await user.click(screen.getByRole('button', { name: t.portsConfirmBtn }));

    await waitFor(() => {
      expect(showToast).toHaveBeenCalledWith(t.code_CONNECTION_ERROR, 'error');
    });
  });

  it('blocks saving invalid backend ports before calling the API', async () => {
    const user = userEvent.setup();
    const { t, showToast } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    const [backendInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(backendInput, { target: { value: '80' } });
    await user.click(screen.getByRole('button', { name: t.saveChanges }));

    expect(mockApi.updatePorts).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(t.portsInvalid, 'error');
  });

  it('blocks saving invalid web ports before calling the API', async () => {
    const user = userEvent.setup();
    const { t, showToast } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    const [, webInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(webInput, { target: { value: '65536' } });
    await user.click(screen.getByRole('button', { name: t.saveChanges }));

    expect(mockApi.updatePorts).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(t.portsInvalid, 'error');
  });

  it('blocks saving duplicate backend and web ports before calling the API', async () => {
    const user = userEvent.setup();
    const { t, showToast } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    const [backendInput, webInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(backendInput, { target: { value: '9111' } });
    fireEvent.change(webInput, { target: { value: '9111' } });
    await user.click(screen.getByRole('button', { name: t.saveChanges }));

    expect(mockApi.updatePorts).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(t.portsDuplicate, 'error');
  });

  it('restores the current ports when the confirmation dialog is cancelled', async () => {
    const user = userEvent.setup();
    const { t } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    const [backendInput, webInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(backendInput, { target: { value: '9111' } });
    fireEvent.change(webInput, { target: { value: '9210' } });
    expect(screen.getByText(t.portsWarning)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: t.saveChanges }));
    await user.click(screen.getByRole('button', { name: t.portsCancelBtn }));

    expect(mockApi.updatePorts).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue('9110')).toBeInTheDocument();
    expect(screen.getByDisplayValue('9120')).toBeInTheDocument();
    expect(screen.queryByText(t.portsWarning)).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes the confirmation dialog when Escape is pressed', async () => {
    const user = userEvent.setup();
    const { t } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    const [backendInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(backendInput, { target: { value: '9111' } });
    await user.click(screen.getByRole('button', { name: t.saveChanges }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByDisplayValue('9110')).toBeInTheDocument();
    expect(screen.queryByText(t.portsWarning)).not.toBeInTheDocument();
  });

  it('saves backend and web ports from advanced settings after confirmation', async () => {
    const user = userEvent.setup();
    mockApi.updatePorts.mockResolvedValue({
      success: true,
      ports: buildPorts({ backend: 9111, web: 9210 }),
      restart_required: true,
      message: 'saved',
    });

    const { t, showToast } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    const [backendInput, webInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(backendInput, { target: { value: '9111' } });
    fireEvent.change(webInput, { target: { value: '9210' } });
    await user.click(screen.getByRole('button', { name: t.saveChanges }));
    await user.click(screen.getByRole('button', { name: t.portsConfirmBtn }));

    await waitFor(() => {
      expect(mockApi.updatePorts).toHaveBeenCalledWith({ backend: 9111, web: 9210 });
      expect(showToast).toHaveBeenCalledWith(
        `${t.portsSaved}\n${t.portsChangedToast
          .replace('{backend}', '9111')
          .replace('{web}', '9210')}`,
        'success'
      );
    });
  });

  it('omits the detailed restart toast when the backend port change does not require restart messaging', async () => {
    const user = userEvent.setup();
    mockApi.updatePorts.mockResolvedValue({
      success: true,
      ports: buildPorts({ backend: 9111 }),
      restart_required: false,
      message: 'saved',
    });

    const { t, showToast } = renderPortsSettings();

    await waitFor(() => {
      expect(mockApi.getPorts).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: t.portsShowAdvancedSettings }));
    const [backendInput] = screen.getAllByRole('spinbutton');
    fireEvent.change(backendInput, { target: { value: '9111' } });
    await user.click(screen.getByRole('button', { name: t.saveChanges }));
    await user.click(screen.getByRole('button', { name: t.portsConfirmBtn }));

    await waitFor(() => {
      expect(showToast).toHaveBeenCalledWith(t.portsSaved, 'success');
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

  it('hides the copy button and shows not configured when no cursor URL is available', async () => {
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
    expect(screen.getAllByText(t.notConfigured)).not.toHaveLength(0);
  });
});
