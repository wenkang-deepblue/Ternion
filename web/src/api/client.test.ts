import { describe, expect, it } from 'vitest';

import { ApiError, isApiError } from './client';

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
