import { describe, expect, it } from 'vitest';

import type { ModelsData } from './api/client';
import {
  getModelName,
  getModelSeriesName,
  getProviderDisplayName,
  isModelAvailableInCatalog,
} from './modelDisplay';

function buildModelsData(): ModelsData {
  return {
    models: {
      openai: [
        { id: 'gpt-5.2', name: 'GPT 5.2', stale: false, pricing_available: true },
      ],
      google: [
        { id: 'gemini-3-pro', name: 'Gemini 3.0 Pro', stale: false, pricing_available: true },
      ],
      anthropic: [],
    },
    enabled_providers: ['openai', 'google'],
    model_count: 2,
  };
}

describe('getProviderDisplayName', () => {
  it('returns brand names for known providers', () => {
    expect(getProviderDisplayName('openai')).toBe('OpenAI');
    expect(getProviderDisplayName('anthropic')).toBe('Anthropic');
    expect(getProviderDisplayName('google')).toBe('Google');
  });

  it('falls back to the raw provider key for unknown providers', () => {
    expect(getProviderDisplayName('mistral')).toBe('mistral');
  });
});

describe('getModelSeriesName', () => {
  it('returns model series names for known providers', () => {
    expect(getModelSeriesName('openai')).toBe('GPT');
    expect(getModelSeriesName('anthropic')).toBe('Claude');
    expect(getModelSeriesName('google')).toBe('Gemini');
  });

  it('falls back to the raw provider key for unknown providers', () => {
    expect(getModelSeriesName('mistral')).toBe('mistral');
  });
});

describe('getModelName', () => {
  it('returns the catalog display name when the model exists', () => {
    expect(getModelName(buildModelsData(), 'openai', 'gpt-5.2')).toBe('GPT 5.2');
  });

  it('returns the raw model id when not found in catalog', () => {
    expect(getModelName(buildModelsData(), 'openai', 'unknown-model')).toBe('unknown-model');
  });

  it('returns the raw model id when provider has no entries', () => {
    expect(getModelName(buildModelsData(), 'anthropic', 'claude-4')).toBe('claude-4');
  });

  it('returns the raw model id when modelsData is null', () => {
    expect(getModelName(null, 'openai', 'gpt-5.2')).toBe('gpt-5.2');
  });

  it('returns the raw model id when modelsData is undefined', () => {
    expect(getModelName(undefined, 'openai', 'gpt-5.2')).toBe('gpt-5.2');
  });

  it('returns the raw model id when provider key is missing from models', () => {
    expect(getModelName(buildModelsData(), 'mistral', 'mistral-large')).toBe('mistral-large');
  });
});

describe('isModelAvailableInCatalog', () => {
  it('returns true when the model exists in the catalog', () => {
    expect(isModelAvailableInCatalog(buildModelsData(), 'openai', 'gpt-5.2')).toBe(true);
  });

  it('returns false when the model does not exist', () => {
    expect(isModelAvailableInCatalog(buildModelsData(), 'openai', 'nonexistent')).toBe(false);
  });

  it('returns false when provider is empty string', () => {
    expect(isModelAvailableInCatalog(buildModelsData(), '', 'gpt-5.2')).toBe(false);
  });

  it('returns false when modelId is empty string', () => {
    expect(isModelAvailableInCatalog(buildModelsData(), 'openai', '')).toBe(false);
  });

  it('returns false when modelsData is null', () => {
    expect(isModelAvailableInCatalog(null, 'openai', 'gpt-5.2')).toBe(false);
  });

  it('returns false when modelsData is undefined', () => {
    expect(isModelAvailableInCatalog(undefined, 'openai', 'gpt-5.2')).toBe(false);
  });

  it('returns false when provider key is missing from models', () => {
    expect(isModelAvailableInCatalog(buildModelsData(), 'mistral', 'mistral-large')).toBe(false);
  });
});
