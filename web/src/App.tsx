/**
 * Main application component for Ternion Control Panel.
 *
 * Integrates all sub-components and provides:
 * - i18n language support
 * - Dark mode toggle
 * - Configuration status bar
 * - Tab navigation
 */

import { useState, useEffect } from 'react';
import api from './api/client';
import type { Config, ServerStatus } from './api/client';
import { ToastProvider } from './components/Toast';
import StatusBar from './components/StatusBar';
import ApiKeyManager from './components/ApiKeyManager';
import RoleModelConfig from './components/RoleModelConfig';
import BudgetSettings from './components/BudgetSettings';
import UsageDashboard from './components/UsageDashboard';
import { detectBrowserLanguage, getTranslations } from './i18n';
import type { Language } from './i18n';
import './index.css';

function AppContent() {
  const [config, setConfig] = useState<Config | null>(null);
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return false;
  });
  const [activeTab, setActiveTab] = useState<'config' | 'usage'>('config');
  const [language, setLanguage] = useState<Language>(() => detectBrowserLanguage());

  const t = getTranslations(language);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  const loadData = async () => {
    try {
      const [configData, statusData] = await Promise.all([
        api.getConfig(),
        api.getStatus(),
      ]);
      setConfig(configData);
      setStatus(statusData);
    } catch (error) {
      console.error('Failed to load data:', error);
    }
  };

  const handleConfigUpdate = (newConfig: Config) => {
    setConfig(newConfig);
    api.getStatus().then(setStatus).catch(console.error);
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="text-3xl">🔺</div>
              <div>
                <h1 className="text-xl font-bold text-slate-900 dark:text-white">
                  {t.appTitle}
                </h1>
                <p className="text-sm text-slate-500">
                  {t.appSubtitle}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {/* Status Badge */}
              {status && (
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      status.provider_count > 0
                        ? 'bg-emerald-500 animate-pulse'
                        : 'bg-yellow-500'
                    }`}
                  />
                  <span className="text-sm text-slate-600 dark:text-slate-400">
                    {status.provider_count} {t.llmKeysEnabled}
                  </span>
                </div>
              )}
              {/* Dark Mode Toggle */}
              <button
                onClick={() => setDarkMode(!darkMode)}
                className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                title={darkMode ? t.lightMode : t.darkMode}
              >
                {darkMode ? '☀️' : '🌙'}
              </button>
            </div>
          </div>
        </div>

        {/* Status Bar */}
        <StatusBar config={config} t={t} />

        {/* Tabs */}
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex gap-1 -mb-px">
            <button
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                activeTab === 'config'
                  ? 'text-blue-600 border-blue-600'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => setActiveTab('config')}
            >
              {t.tabConfig}
            </button>
            <button
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                activeTab === 'usage'
                  ? 'text-blue-600 border-blue-600'
                  : 'text-slate-500 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              onClick={() => setActiveTab('usage')}
            >
              {t.tabUsage}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {activeTab === 'config' ? (
          <div className="space-y-6">
            <ApiKeyManager config={config} onConfigUpdate={handleConfigUpdate} t={t} />
            <RoleModelConfig config={config} onConfigUpdate={handleConfigUpdate} t={t} />
            <BudgetSettings config={config} onConfigUpdate={handleConfigUpdate} t={t} />
          </div>
        ) : (
          <UsageDashboard t={t} />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 dark:border-slate-700 py-6 mt-12">
        <div className="max-w-5xl mx-auto px-4 text-center text-sm text-slate-500">
          <p>
            Ternion v0.4.0 • {t.appSubtitle} •{' '}
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              {t.footerApiDocs}
            </a>
          </p>
          {/* Language Toggle (for development) */}
          <div className="mt-3 flex items-center justify-center gap-2">
            <span className="text-slate-400">{t.languageToggle}:</span>
            <button
              onClick={() => setLanguage('en')}
              className={`px-2 py-1 rounded text-xs ${
                language === 'en'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
              }`}
            >
              English
            </button>
            <button
              onClick={() => setLanguage('zh')}
              className={`px-2 py-1 rounded text-xs ${
                language === 'zh'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
              }`}
            >
              中文
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}

function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}

export default App;
