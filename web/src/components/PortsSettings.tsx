/**
 * Ports Settings component for Ternion Control Panel.
 *
 * Allows users to view and modify server port configuration:
 * - Backend API port (default: 9110)
 * - Web control panel port (default: 9120)
 *
 * Port changes are saved to config but require manual server restart.
 */

import { useState, useEffect } from 'react';
import api from '../api/client';
import type { PortsConfig } from '../api/client';
import { useToast } from './toastContext';
import type { Translations } from '../i18n';
import { getErrorMessage } from '../i18n';
import type { Language } from '../i18n';

// Port settings icons
import portIconLight from '../assets/icons/port_light_mode_50dp.svg';
import portIconDark from '../assets/icons/port_dark_mode_50dp.svg';
import warningIconLight from '../assets/icons/warning_light_mode_50dp.svg';
import warningIconDark from '../assets/icons/warning_dark_mode_50dp.svg';

/**
 * Props for the PortsSettings component.
 */
interface PortsSettingsProps {
  /** Translation function/object for localized strings. */
  t: Translations;
  /** Whether the application is currently in dark mode. */
  isDarkMode: boolean;
  /** The currently selected language code. */
  language: Language;
}

export function PortsSettings({ t, isDarkMode, language }: PortsSettingsProps) {
  const { showToast } = useToast();
  const [ports, setPorts] = useState<PortsConfig>({
    backend: 9110,
    web: 9120,
  });
  const [originalPorts, setOriginalPorts] = useState<PortsConfig>({
    backend: 9110,
    web: 9120,
  });
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    loadPorts();
  }, []);

  const loadPorts = async () => {
    try {
      const data = await api.getPorts();
      setPorts(data);
      setOriginalPorts(data);
    } catch (error) {
      console.error('Failed to load ports:', error);
    }
  };

  const validatePort = (port: number): boolean => {
    return port >= 1024 && port <= 65535;
  };

  const handleBackendChange = (value: string) => {
    const numValue = parseInt(value, 10);
    if (!isNaN(numValue)) {
      setPorts(prev => ({ ...prev, backend: numValue }));
      setHasChanges(numValue !== originalPorts.backend || ports.web !== originalPorts.web);
    }
  };

  const handleWebChange = (value: string) => {
    const numValue = parseInt(value, 10);
    if (!isNaN(numValue)) {
      setPorts(prev => ({ ...prev, web: numValue }));
      setHasChanges(ports.backend !== originalPorts.backend || numValue !== originalPorts.web);
    }
  };

  const handleSave = async () => {
    // Validate ports
    if (!validatePort(ports.backend) || !validatePort(ports.web)) {
      showToast(t.portsInvalid, 'error');
      return;
    }

    setSaving(true);
    try {
      const result = await api.updatePorts(ports);
      setOriginalPorts(result.ports);
      setHasChanges(false);

      // Show success toast with new port values and URLs
      const restartNote = result.restart_required ? `\n${t.portsRestartNote}` : '';
      showToast(
        `${t.portsSaved}${restartNote}\n${t.portsBackendLabel}: ${result.ports.backend} | ${t.portsWebLabel}: ${result.ports.web}`,
        'success'
      );
    } catch (error) {
      console.error('Failed to save ports:', error);
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode, language), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <img src={isDarkMode ? portIconDark : portIconLight} alt="" className="w-6 h-6" />
            {t.portsTitle}
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {t.portsDescription}
          </p>
        </div>
        {hasChanges && (
          <button
            style={{ minWidth: '100px', height: '46px', flexShrink: 0 }}
            className="btn btn-primary text-xs whitespace-nowrap"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? t.saving : t.saveChanges}
          </button>
        )}
      </div>

      <div className="card-body">
        {/* Current Port Display */}
        <div className="mt-6 mb-12 text-center">
          <span className="text-lg font-medium text-slate-700 dark:text-slate-300">
            {t.portsCurrentBackend}: <span className="font-bold" style={{ color: '#4083f2' }}>{originalPorts.backend}</span>
          </span>
          <span className="mx-3 text-xl text-slate-400">|</span>
          <span className="text-lg font-medium text-slate-700 dark:text-slate-300">
            {t.portsCurrentWeb}: <span className="font-bold" style={{ color: '#4083f2' }}>{originalPorts.web}</span>
          </span>
        </div>

        {/* Warning Banner */}
        <div className="mb-10 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
          <p className="text-amber-800 dark:text-amber-200 text-sm font-medium flex items-center justify-center gap-2">
            <img src={isDarkMode ? warningIconDark : warningIconLight} alt="" className="w-6 h-6" />
            {t.portsWarning}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* Backend Port */}
          <div>
            <label className="label">{t.portsBackend}</label>
            <div className="input-rainbow-glow">
              <input
                type="number"
                className="input"
                style={{ width: '100%' }}
                value={ports.backend}
                onChange={(e) => handleBackendChange(e.target.value)}
                min="1024"
                max="65535"
              />
            </div>
            <p className="text-sm text-slate-500 mt-1">
              http://localhost:{ports.backend}
            </p>
          </div>

          {/* Web Port */}
          <div>
            <label className="label">{t.portsWeb}</label>
            <div className="input-rainbow-glow">
              <input
                type="number"
                className="input"
                style={{ width: '100%' }}
                value={ports.web}
                onChange={(e) => handleWebChange(e.target.value)}
                min="1024"
                max="65535"
              />
            </div>
            <p className="text-sm text-slate-500 mt-1">
              http://localhost:{ports.web}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PortsSettings;
