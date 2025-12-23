/**
 * API Key Manager component for Ternion Control Panel.
 *
 * Provides UI for:
 * - Adding/removing API keys for each provider
 * - Testing API key validity
 * - Selecting active API key per provider
 */

import { useState } from 'react';
import api from '../api/client';
import type { Config } from '../api/client';
import { useToast } from './Toast';
import type { Translations } from '../i18n';
import { getErrorMessage } from '../i18n';

interface ApiKeyManagerProps {
  config: Config | null;
  onConfigUpdate: (config: Config) => void;
  t: Translations;
}

const PROVIDER_INFO = {
  google: {
    name: 'Google Gemini',
    description: 'Google AI Studio API Key',
    placeholder: 'AIza...',
    link: 'https://aistudio.google.com/',
    icon: '🔵',
  },
  anthropic: {
    name: 'Anthropic Claude',
    description: 'Anthropic API Key',
    placeholder: 'sk-ant-...',
    link: 'https://console.anthropic.com/',
    icon: '🟠',
  },
  openai: {
    name: 'OpenAI GPT',
    description: 'OpenAI API Key',
    placeholder: 'sk-...',
    link: 'https://platform.openai.com/',
    icon: '🟢',
  },
};

export function ApiKeyManager({ config, onConfigUpdate, t }: ApiKeyManagerProps) {
  const { showToast } = useToast();
  const [newKeys, setNewKeys] = useState<Record<string, { name: string; key: string }>>({
    google: { name: '', key: '' },
    anthropic: { name: '', key: '' },
    openai: { name: '', key: '' },
  });
  const [testing, setTesting] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  const handleNameChange = (provider: string, value: string) => {
    setNewKeys(prev => ({
      ...prev,
      [provider]: { ...prev[provider], name: value },
    }));
  };

  const handleKeyChange = (provider: string, value: string) => {
    setNewKeys(prev => ({
      ...prev,
      [provider]: { ...prev[provider], key: value },
    }));
  };

  const handleTestAndSave = async (provider: string) => {
    const { name, key } = newKeys[provider];
    if (!key) return;

    setTesting(provider);
    try {
      const testResult = await api.testProvider(provider, key);
      console.log('Test Result:', testResult);

      if (!testResult.success) {
        // Use global getErrorMessage helper
        let errorMessage = getErrorMessage(t, testResult.code);
        
        // If translation is missing (returns code) or it is a connection error, append detail
        if (errorMessage === testResult.code || testResult.code === 'CONNECTION_ERROR') {
           // Clean up common error prefixes from backend message
           const rawMessage = testResult.message || '';
           const cleanMessage = rawMessage.replace(/^(400|500)\s+/, '');
           
           // Fallback: Check message content for auth errors if code check failed
           if (cleanMessage.toLowerCase().includes('not valid') || 
               cleanMessage.toLowerCase().includes('invalid') ||
               cleanMessage.toLowerCase().includes('incorrect')) {
              errorMessage = t.code_AUTH_ERROR;
           } else if (testResult.code === 'CONNECTION_ERROR') {
             errorMessage = `${t.code_CONNECTION_ERROR}: ${cleanMessage}`;
           } else {
             // Fallback to cleaned message if no translation found
             errorMessage = cleanMessage || t.code_UNKNOWN_ERROR;
           }
        }
        
        showToast(errorMessage, 'error');
        setTesting(null);
        return;
      }

      setSaving(true);
      const result = await api.addApiKey(provider, name || 'Unnamed', key);
      onConfigUpdate(result.config);

      setNewKeys(prev => ({
        ...prev,
        [provider]: { name: '', key: '' },
      }));

      // Success message
      const providerName = PROVIDER_INFO[provider as keyof typeof PROVIDER_INFO].name;
      const successMsg = getErrorMessage(t, testResult.code);
      showToast(`${providerName} ${successMsg}`, 'success');

    } catch (error) {
      console.error('Test API Error:', error);
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode), 'error');
    } finally {
      setTesting(null);
      setSaving(false);
    }
  };

  const handleSelectKey = async (provider: string, keyId: string) => {
    try {
      const result = await api.selectApiKey(provider, keyId);
      onConfigUpdate(result.config);
      showToast(`${t.apiKeySelected}: ${result.key_name || 'Unnamed'}`, 'info');
    } catch (error) {
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode), 'error');
    }
  };

  const handleDeleteKey = async (provider: string, keyId: string) => {
    if (!confirm(t.confirmDeleteApiKey)) return;

    try {
      const result = await api.deleteApiKey(provider, keyId);
      onConfigUpdate(result.config);
      showToast(t.apiKeyDeleted, 'info');
    } catch (error) {
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode), 'error');
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          {t.apiKeyTitle}
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          {t.apiKeyDescription}
          <span className="text-slate-400 dark:text-slate-500">{t.apiKeyStorageNote}</span>
        </p>
      </div>
      <div className="card-body space-y-6">
        {Object.entries(PROVIDER_INFO).map(([provider, info]) => {
          const status = config?.providers[provider];
          const keys = status?.keys || [];
          const selectedKeyId = status?.selected_key_id;

          return (
            <div
              key={provider}
              className="p-4 rounded-lg border border-slate-200 dark:border-slate-700"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{info.icon}</span>
                    <h3 className="font-medium">{info.name}</h3>
                    {status?.enabled && (
                      <span className="badge badge-success">{t.enabled}</span>
                    )}
                  </div>
                  <p className="text-sm text-slate-500 mt-1">
                    {info.description} •{' '}
                    <a
                      href={info.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-500 hover:underline"
                    >
                      {t.apiKeyGetKey}
                    </a>
                  </p>
                </div>
              </div>

              {/* Existing Keys */}
              {keys.length > 0 && (
                <div className="mb-4 space-y-2">
                  {keys.map((keyInfo) => (
                    <div
                      key={keyInfo.id}
                      className="flex items-center gap-3 p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50"
                    >
                      <input
                        type="radio"
                        name={`${provider}-key`}
                        checked={selectedKeyId === keyInfo.id}
                        onChange={() => handleSelectKey(provider, keyInfo.id)}
                        className="w-4 h-4 text-blue-600 cursor-pointer"
                      />
                      <div className="flex-1 min-w-0">
                        <span className="font-medium text-sm">
                          {keyInfo.name || t.unnamed}
                        </span>
                        <code className="ml-2 px-2 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-xs">
                          {keyInfo.key_preview}
                        </code>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDeleteKey(provider, keyInfo.id)}
                        className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all duration-200 active:scale-95 cursor-pointer"
                        title={t.delete}
                      >
                        🗑️
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Add New Key */}
              <div className="flex flex-col gap-1">
                <div className="flex gap-2" style={{ marginLeft: '2px' }}>
                  <span className="text-xs text-slate-500 dark:text-slate-400" style={{ width: '260px' }}>{t.apiKeyNameLabel}</span>
                  <span className="text-xs text-slate-500 dark:text-slate-400 flex-1">{t.apiKeyLabel}</span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    style={{ width: '260px', flexShrink: 0 }}
                    className="input"
                    placeholder={t.apiKeyPlaceholder}
                    value={newKeys[provider]?.name || ''}
                    onChange={(e) => handleNameChange(provider, e.target.value)}
                  />
                  <div className="relative flex-1">
                    <input
                      type={showKeys[provider] ? 'text' : 'password'}
                      style={{ width: '100%', paddingRight: '2.5rem' }}
                      className="input"
                      placeholder={info.placeholder}
                      value={newKeys[provider]?.key || ''}
                      onChange={(e) => handleKeyChange(provider, e.target.value)}
                    />
                    <button
                      type="button"
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors cursor-pointer"
                      onClick={() => setShowKeys(prev => ({ ...prev, [provider]: !prev[provider] }))}
                    >
                      {showKeys[provider] ? '🙈' : '👁️'}
                    </button>
                  </div>
                  <button
                    style={{ width: '120px', flexShrink: 0 }}
                    className="btn btn-primary"
                    onClick={() => handleTestAndSave(provider)}
                    disabled={!newKeys[provider]?.key || testing === provider || saving}
                  >
                    {testing === provider ? t.apiKeyTesting : t.apiKeyTestAndSave}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default ApiKeyManager;
