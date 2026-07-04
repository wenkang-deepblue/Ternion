import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import api, {
  ApiError,
  buildAuthHeaders,
  getStoredAuthToken,
  isApiError,
  setStoredAuthToken,
} from './client';

describe('ApiError', () => {
  it('sets status, code, message, and payload from a full payload', () => {
    const error = new ApiError(400, {
      detail: 'MODEL_UNAVAILABLE',
      code: 'MODEL_UNAVAILABLE',
      message: 'model not found',
      provider: 'openai',
      model: 'gpt-5.3',
      refresh_suggested: true,
    });

    expect(error.status).toBe(400);
    expect(error.code).toBe('MODEL_UNAVAILABLE');
    expect(error.message).toBe('model not found');
    expect(error.name).toBe('ApiError');
    expect(error.payload.provider).toBe('openai');
    expect(error.payload.model).toBe('gpt-5.3');
    expect(error.payload.refresh_suggested).toBe(true);
  });

  it('prefers code over detail for the code property', () => {
    const error = new ApiError(400, {
      detail: 'Model gpt-5.3 is unavailable',
      code: 'MODEL_UNAVAILABLE',
    });

    expect(error.code).toBe('MODEL_UNAVAILABLE');
    expect(error.message).toBe('Model gpt-5.3 is unavailable');
  });

  it('falls back to detail when code is absent', () => {
    const error = new ApiError(400, { detail: 'MODEL_UNAVAILABLE' });

    expect(error.code).toBe('MODEL_UNAVAILABLE');
    expect(error.message).toBe('MODEL_UNAVAILABLE');
  });

  it('falls back to HTTP status when both code and detail are absent', () => {
    const error = new ApiError(500, {});

    expect(error.code).toBe('HTTP 500');
    expect(error.message).toBe('HTTP 500');
  });

  it('prefers message over detail for the Error.message property', () => {
    const error = new ApiError(400, {
      detail: 'ERROR_CODE',
      message: 'Human readable description',
    });

    expect(error.message).toBe('Human readable description');
    expect(error.code).toBe('ERROR_CODE');
  });

  it('is an instance of Error', () => {
    const error = new ApiError(500, { detail: 'test' });
    expect(error).toBeInstanceOf(Error);
  });
});

describe('isApiError', () => {
  it('returns true for ApiError instances', () => {
    expect(isApiError(new ApiError(400, { detail: 'test' }))).toBe(true);
  });

  it('returns false for plain Error instances', () => {
    expect(isApiError(new Error('test'))).toBe(false);
  });

  it('returns false for null', () => {
    expect(isApiError(null)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isApiError(undefined)).toBe(false);
  });

  it('returns false for strings', () => {
    expect(isApiError('error')).toBe(false);
  });

  it('returns false for plain objects', () => {
    expect(isApiError({ status: 400, code: 'test' })).toBe(false);
  });
});

describe('access token storage and header injection', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('round-trips the stored access token', () => {
    expect(getStoredAuthToken()).toBe('');
    setStoredAuthToken('my-token');
    expect(getStoredAuthToken()).toBe('my-token');
    setStoredAuthToken('');
    expect(getStoredAuthToken()).toBe('');
  });

  it('builds the Authorization header only when a token is stored', () => {
    expect(buildAuthHeaders()).toEqual({});
    setStoredAuthToken('my-token');
    expect(buildAuthHeaders()).toEqual({ Authorization: 'Bearer my-token' });
  });

  it('attaches the bearer token to API requests', async () => {
    setStoredAuthToken('my-token');
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ server_status: 'running' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await api.getStatus();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer my-token');
  });

  it('sends no Authorization header without a stored token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ server_status: 'running' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await api.getStatus();

    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>).Authorization).toBeUndefined();
  });
});
