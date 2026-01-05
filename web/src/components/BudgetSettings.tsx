/**
 * Budget Settings component for Ternion Control Panel.
 *
 * Provides UI for configuring:
 * - Monthly budget limit in USD
 * - Alert threshold percentage
 */

import { useState, useEffect } from 'react';
import api from '../api/client';
import type { Config, BudgetConfig } from '../api/client';
import { useToast } from './Toast';
import type { Translations } from '../i18n';
import { getErrorMessage } from '../i18n';

// Budget section icon
import budgetIconLight from '../assets/icons/budget_light_mode_50dp.svg';
import budgetIconDark from '../assets/icons/budget_dark_mode_50dp.svg';

interface BudgetSettingsProps {
  config: Config | null;
  onConfigUpdate: (config: Config) => void;
  t: Translations;
  isDarkMode: boolean;
}

const THRESHOLD_OPTIONS = [
  { value: 0.5, label: '50%' },
  { value: 0.6, label: '60%' },
  { value: 0.7, label: '70%' },
  { value: 0.8, label: '80%' },
  { value: 0.85, label: '85%' },
  { value: 0.9, label: '90%' },
  { value: 0.95, label: '95%' },
];

export function BudgetSettings({ config, onConfigUpdate, t, isDarkMode }: BudgetSettingsProps) {
  const { showToast } = useToast();
  const [budget, setBudget] = useState<BudgetConfig>({
    monthly_limit_usd: 50,
    alert_threshold: 0.9,
  });
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    if (config?.budget) {
      setBudget(config.budget);
    }
  }, [config]);

  const handleLimitChange = (value: string) => {
    const numValue = parseFloat(value);
    if (!isNaN(numValue) && numValue >= 0) {
      setBudget(prev => ({ ...prev, monthly_limit_usd: numValue }));
      setHasChanges(true);
    }
  };

  const handleThresholdChange = (value: string) => {
    const numValue = parseFloat(value);
    setBudget(prev => ({ ...prev, alert_threshold: numValue }));
    setHasChanges(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updatedConfig = await api.updateConfig({ budget });
      onConfigUpdate(updatedConfig);
      setHasChanges(false);

      // Show toast with saved settings
      const thresholdPct = (budget.alert_threshold * 100).toFixed(0);
      showToast(
        `${t.budgetSaved}\n${t.monthlyLimitLabel}: $${budget.monthly_limit_usd}\n${t.alertThreshold}: ${thresholdPct}%`,
        'success'
      );
    } catch (error) {
      console.error('Failed to save:', error);
      const errorCode = error instanceof Error ? error.message : String(error);
      showToast(getErrorMessage(t, errorCode), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <img src={isDarkMode ? budgetIconDark : budgetIconLight} alt="" className="w-6 h-6" />
            {t.budgetTitle}
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {t.budgetDescription}
          </p>
        </div>
        {hasChanges && (
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? t.saving : t.saveChanges}
          </button>
        )}
      </div>
      <div className="card-body">
        <div className="grid grid-cols-2 gap-6">
          {/* Monthly Limit */}
          <div>
            <label className="label">{t.monthlyLimit}</label>
            <div className="flex items-center gap-2">
              <span className="text-slate-500 font-medium text-lg">$</span>
              <div className="input-rainbow-glow flex-1">
                <input
                  type="number"
                  className="input"
                  style={{ width: '100%' }}
                  value={budget.monthly_limit_usd}
                  onChange={(e) => handleLimitChange(e.target.value)}
                  min="0"
                  step="5"
                />
              </div>
            </div>
            <p className="text-sm text-slate-500 mt-1">
              {t.budgetLimitNote}
            </p>
          </div>

          {/* Alert Threshold */}
          <div>
            <label className="label">{t.alertThreshold}</label>
            <select
              className="select"
              value={budget.alert_threshold}
              onChange={(e) => handleThresholdChange(e.target.value)}
            >
              {THRESHOLD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <p className="text-sm text-slate-500 mt-1">
              {t.budgetThresholdNote}
            </p>
          </div>
        </div>

        {/* Preview */}
        <div className="mt-6 p-4 bg-slate-50 dark:bg-slate-800/50 rounded-lg">
          <h4 className="text-sm font-medium mb-3">{t.preview}</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-slate-500">{t.monthlyLimitLabel}: </span>
              <span className="font-medium">${budget.monthly_limit_usd.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-slate-500">{t.alertTriggerLabel}: </span>
              <span className="font-medium">
                ${(budget.monthly_limit_usd * budget.alert_threshold).toFixed(2)}
              </span>
              <span className="text-slate-400 ml-1">
                ({(budget.alert_threshold * 100).toFixed(0)}%)
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default BudgetSettings;
