/**
 * Tests for the App-level access token gate (Phase C5).
 *
 * Covers the tunneled Panel flow: a 401 on initial load shows the gate,
 * a wrong token gets explicit feedback, and a valid token dismisses the
 * gate and loads the normal Panel.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { ApiError } from './api/client';
import { getTranslations } from './i18n';

const mockApi = vi.hoisted(() => ({}) as Record<string, ReturnType<typeof vi.fn>>);

vi.mock('./api/client', async () => {
  const actual = await vi.importActual<typeof import('./api/client')>('./api/client');
  const proto = Object.getPrototypeOf(actual.default);
  for (const key of Object.getOwnPropertyNames(proto)) {
    if (key !== 'constructor' && typeof proto[key] === 'function') {
      mockApi[key] = vi.fn();
    }
  }
  return { ...actual, api: mockApi, default: mockApi };
});

// The gate renders before any config loads, so App falls back to the browser
// language; jsdom reports English, so assertions use the English strings.
const t = getTranslations('en');

// jsdom does not implement matchMedia, which App uses for the system theme.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

function unauthorized(): ApiError {
  return new ApiError(401, { detail: 'invalid_api_key' });
}

function buildConfig() {
  return {
    providers: {},
    roles: {},
    budget: { monthly_limit_usd: 50, alert_threshold: 0.9 },
    preferences: { theme: 'light', language: 'zh' },
    execution_mode: 'ternion_full',
    updated_at: '2026-07-04T00:00:00Z',
    public_access: { mode: 'local_tunnel', public_base_url: 'https://demo.ngrok.app' },
  };
}

function buildPublicAccess() {
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
  };
}

function primeResolvedBackend() {
  mockApi.getConfig.mockResolvedValue(buildConfig());
  mockApi.getStatus.mockResolvedValue({
    server_status: 'running',
    active_providers: [],
    recent_requests: 0,
  });
  mockApi.getModels.mockResolvedValue({
    models: { openai: [], google: [], anthropic: [] },
    enabled_providers: [],
    model_count: 0,
    catalog_initialized: true,
    requires_initialization: false,
  });
  mockApi.getPublicAccess.mockResolvedValue(buildPublicAccess());
  mockApi.getPorts.mockResolvedValue({ backend: 9110, web: 9120 });
  mockApi.getAuthToken.mockResolvedValue({ auth_token: 'server-token' });
  mockApi.updatePreferences.mockResolvedValue({});
}

describe('App access token gate', () => {
  beforeEach(() => {
    for (const fn of Object.values(mockApi)) {
      fn.mockReset();
      fn.mockResolvedValue(undefined);
    }
    window.localStorage.clear();
    // Suppress the public-access first-run reminder so it cannot overlap
    // with the gate assertions.
    window.sessionStorage.setItem('ternion-public-access-reminder-dismissed', '1');
  });

  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('shows the token gate when the initial load is rejected with 401', async () => {
    mockApi.getConfig.mockRejectedValue(unauthorized());
    mockApi.getStatus.mockRejectedValue(unauthorized());

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(t.accessTokenGateTitle)).toBeInTheDocument();
    });
  });

  it('shows invalid-token feedback when the submitted token is rejected', async () => {
    mockApi.getConfig.mockRejectedValue(unauthorized());
    mockApi.getStatus.mockRejectedValue(unauthorized());

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(t.accessTokenGateTitle)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(t.accessTokenGatePlaceholder), 'wrong-token');
    await user.click(screen.getByRole('button', { name: t.accessTokenGateSubmit }));

    await waitFor(() => {
      expect(screen.getByText(t.accessTokenGateInvalid)).toBeInTheDocument();
    });
    // Still gated.
    expect(screen.getByText(t.accessTokenGateTitle)).toBeInTheDocument();
  });

  it('dismisses the gate and loads the panel once a valid token is accepted', async () => {
    mockApi.getConfig.mockRejectedValue(unauthorized());
    mockApi.getStatus.mockRejectedValue(unauthorized());

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(t.accessTokenGateTitle)).toBeInTheDocument();
    });

    primeResolvedBackend();

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(t.accessTokenGatePlaceholder), 'server-token');
    await user.click(screen.getByRole('button', { name: t.accessTokenGateSubmit }));

    await waitFor(() => {
      expect(screen.queryByText(t.accessTokenGateTitle)).not.toBeInTheDocument();
    });
    expect(window.localStorage.getItem('ternion-access-token')).toBe('server-token');
    expect(screen.getByRole('heading', { name: t.appTitle })).toBeInTheDocument();
  });
});
