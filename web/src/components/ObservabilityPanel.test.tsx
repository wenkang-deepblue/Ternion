import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { setStoredAuthToken } from '../api/client';
import ZH from '../locales/zh';
import { ObservabilityPanel } from './ObservabilityPanel';

const mockApi = vi.hoisted(() => ({
  revealFile: vi.fn(),
  exportLogs: vi.fn(),
}));

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    api: mockApi,
    default: mockApi,
  };
});

const t = ZH;

function sseResponse(frames: string[], status = 200): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
      // Keep the stream open so the connection stays "connected".
    },
  });
  return { status, ok: status >= 200 && status < 300, body: stream } as unknown as Response;
}

describe('ObservabilityPanel log streaming', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('parses SSE data frames from the fetch-based stream into log rows', async () => {
    const entry = {
      timestamp: '2026-07-04T10:00:00.000Z',
      level: 'INFO',
      category: 'LIFECYCLE',
      message: 'Server started on port 9110',
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(sseResponse([`data: ${JSON.stringify(entry)}\n\n`]));
    vi.stubGlobal('fetch', fetchMock);

    render(<ObservabilityPanel t={t} isDarkMode={false} />);

    await waitFor(() => {
      expect(screen.getByText(/Server started on port 9110/)).toBeInTheDocument();
    });
    expect(screen.getByText(t.logsConnected)).toBeInTheDocument();
  });

  it('sends the stored access token as an Authorization header', async () => {
    setStoredAuthToken('stream-token');
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([]));
    vi.stubGlobal('fetch', fetchMock);

    render(<ObservabilityPanel t={t} isDarkMode={false} />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/logs/stream');
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer stream-token');
  });

  it('stops reconnecting after a 401 instead of looping', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([], 401));
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout');
    vi.stubGlobal('fetch', fetchMock);

    render(<ObservabilityPanel t={t} isDarkMode={false} />);

    await waitFor(() => {
      expect(screen.getByText(t.logsDisconnected)).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // No 3-second reconnect was scheduled for the auth failure.
    const reconnectCalls = setTimeoutSpy.mock.calls.filter(([, delay]) => delay === 3000);
    expect(reconnectCalls).toHaveLength(0);
    setTimeoutSpy.mockRestore();
  });

  it('schedules a reconnect for non-auth stream failures', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('network down'));
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout');
    vi.stubGlobal('fetch', fetchMock);

    render(<ObservabilityPanel t={t} isDarkMode={false} />);

    await waitFor(() => {
      const reconnectCalls = setTimeoutSpy.mock.calls.filter(([, delay]) => delay === 3000);
      expect(reconnectCalls.length).toBeGreaterThanOrEqual(1);
    });
    setTimeoutSpy.mockRestore();
  });
});
