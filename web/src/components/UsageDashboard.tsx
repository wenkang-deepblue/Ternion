/**
 * Usage Dashboard component for Ternion Control Panel.
 *
 * Displays comprehensive usage statistics:
 * - 4 statistics cards (total cost, remaining, input tokens, output tokens)
 * - Budget progress bar
 * - Daily usage chart with month selector
 * - Monthly usage chart with year selector
 */

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import api from '../api/client';
import type { UsageData, Config } from '../api/client';
import type { Translations } from '../i18n';

/**
 * Props for the UsageDashboard component.
 */
interface UsageDashboardProps {
  /** Translation function/object for localized strings. */
  t: Translations;
  /** Whether the application is currently in dark mode. */
  isDarkMode?: boolean;
  /** Optional callback fired when budget configuration is updated from within the dashboard. */
  onConfigUpdate?: (config: Config) => void;
}

type TokenType = 'all' | 'input' | 'output' | 'thoughts';
type ProviderFilter = 'all' | 'google' | 'anthropic' | 'openai';

// Provider logo imports
import geminiLogo from '../assets/icons/gemini_logo.png';
import claudeLogo from '../assets/icons/claude_logo.png';
import openaiLogo from '../assets/icons/openai_logo.png';

// Format large numbers with K/M suffix
function formatTokenCount(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return value.toString();
}

// Custom tooltip for charts - uses dataKey for formatting decisions
function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string; dataKey?: string }>;
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;

  // Helper to check if a dataKey represents cost (not tokens)
  const isCostField = (dataKey?: string): boolean => {
    if (!dataKey) return false;
    return dataKey.includes('cost');
  };

  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg p-3">
      <p className="font-medium text-slate-900 dark:text-white mb-2">{label}</p>
      {payload.map((entry, index) => (
        <p key={index} style={{ color: entry.color }} className="text-sm">
          {entry.name}: {isCostField(entry.dataKey)
            ? `$${entry.value.toFixed(4)}` 
            : formatTokenCount(entry.value)}
        </p>
      ))}
    </div>
  );
}

export function UsageDashboard({ t, isDarkMode = false, onConfigUpdate }: UsageDashboardProps) {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedMonth, setSelectedMonth] = useState<string>('');
  const [selectedYear, setSelectedYear] = useState<string>('');
  const [dailyTokenType, setDailyTokenType] = useState<TokenType>('all');
  const [monthlyTokenType, setMonthlyTokenType] = useState<TokenType>('all');
  const [dailyProvider, setDailyProvider] = useState<ProviderFilter>('all');
  const [monthlyProvider, setMonthlyProvider] = useState<ProviderFilter>('all');
  const [showDisclaimer, setShowDisclaimer] = useState(true);
  const [alertThreshold, setAlertThreshold] = useState(0.9);
  
  // Budget edit popup state
  const [showBudgetEdit, setShowBudgetEdit] = useState(false);
  const [newBudgetLimit, setNewBudgetLimit] = useState<string>('');
  const [budgetSaving, setBudgetSaving] = useState(false);
  const budgetEditRef = useRef<HTMLDivElement>(null);
  const providerLabels: Record<ProviderFilter, string> = {
    all: t.usageAllProviders,
    google: t.providerGoogle,
    anthropic: t.providerAnthropic,
    openai: t.providerOpenai,
  };
  const tokenTypeLabels: Record<TokenType, string> = {
    all: t.usageAllTokens,
    input: t.usageInputTokens,
    output: t.usageOutputTokens,
    thoughts: t.usageThoughtsTokens,
  };

  // Load disclaimer preference from config
  useEffect(() => {
    const loadConfig = async () => {
      try {
        const config = await api.getConfig();
        if (config.preferences?.hide_usage_disclaimer) {
          setShowDisclaimer(false);
        }
        if (config.budget?.alert_threshold) {
          setAlertThreshold(config.budget.alert_threshold);
        }
      } catch (error) {
        console.error('Failed to load config:', error);
      }
    };
    loadConfig();
  }, []);

  // Handle dismiss disclaimer
  const handleDismissDisclaimer = async () => {
    setShowDisclaimer(false);
    try {
      await api.updatePreferences({ hide_usage_disclaimer: true });
    } catch (error) {
      console.error('Failed to save preference:', error);
    }
  };

  // Close budget edit popup on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (budgetEditRef.current && !budgetEditRef.current.contains(event.target as Node)) {
        setShowBudgetEdit(false);
        setNewBudgetLimit('');
      }
    };
    if (showBudgetEdit) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showBudgetEdit]);

  // Handle budget edit button click
  const handleBudgetEditClick = () => {
    setNewBudgetLimit(usage?.monthly_limit_usd?.toString() || '50');
    setShowBudgetEdit(true);
  };

  // Handle budget save
  const handleBudgetSave = async () => {
    const newLimit = parseFloat(newBudgetLimit);
    if (isNaN(newLimit) || newLimit <= 0) {
      return;
    }
    setBudgetSaving(true);
    try {
      const updatedConfig = await api.updateConfig({ budget: { monthly_limit_usd: newLimit } });
      
      // Update local usage state immediately for better UX
      if (usage) {
        setUsage({
          ...usage,
          monthly_limit_usd: newLimit,
          // Recalculate usage_pct based on new limit
          usage_pct: (usage.total_cost_usd / newLimit) * 100
        });
      }
      
      // Notify parent to refresh config
      if (onConfigUpdate) {
        onConfigUpdate(updatedConfig);
      }
      
      // Reload usage data to get canonical data from server
      await loadUsage();
      
      setShowBudgetEdit(false);
      setNewBudgetLimit('');
    } catch (error) {
      console.error('Failed to save budget:', error);
    } finally {
      setBudgetSaving(false);
    }
  };

  const loadUsage = useCallback(async () => {
    try {
      const data = await api.getUsage();
      setUsage(data);
      // Set default selections
      if (data.available_months?.length > 0) {
        setSelectedMonth(data.available_months[0]);
      }
      if (data.available_years?.length > 0) {
        setSelectedYear(data.available_years[0]);
      }
    } catch (error) {
      console.error('Failed to load usage:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUsage();
  }, [loadUsage]);

  // Helper to calculate cost from separate fields
  const calcProviderCost = (prov: { input_cost?: number; output_cost?: number; thoughts_cost?: number } | undefined): number => {
    if (!prov) return 0;
    return (prov.input_cost || 0) + (prov.output_cost || 0) + (prov.thoughts_cost || 0);
  };

  // Filter daily data by selected month and provider
  const filteredDailyData = useMemo(() => {
    if (!usage?.daily_data) return [];
    return usage.daily_data
      .filter((d) => d.date.startsWith(selectedMonth))
      .map((d) => {
        // If filtering by provider, use provider-specific data
        if (dailyProvider !== 'all' && d.providers) {
          const prov = d.providers[dailyProvider];
          return {
            date: d.date,
            displayDate: d.date.split('-')[2],
            cost: calcProviderCost(prov),
            input_cost: prov?.input_cost || 0,
            output_cost: prov?.output_cost || 0,
            thoughts_cost: prov?.thoughts_cost || 0,
            input_tokens: prov?.input_tokens || 0,
            output_tokens: prov?.output_tokens || 0,
            thoughts_tokens: prov?.thoughts_tokens || 0,
          };
        }
        return {
          ...d,
          displayDate: d.date.split('-')[2],
        };
      });
  }, [usage?.daily_data, selectedMonth, dailyProvider]);

  // Filter monthly data by selected year and provider
  const filteredMonthlyData = useMemo(() => {
    if (!usage?.monthly_data) return [];
    return usage.monthly_data
      .filter((d) => d.month.startsWith(selectedYear))
      .map((d) => {
        // If filtering by provider, use provider-specific data
        if (monthlyProvider !== 'all' && d.providers) {
          const prov = d.providers[monthlyProvider];
          return {
            month: d.month,
            displayMonth: d.month.split('-')[1],
            cost: calcProviderCost(prov),
            input_cost: prov?.input_cost || 0,
            output_cost: prov?.output_cost || 0,
            thoughts_cost: prov?.thoughts_cost || 0,
            input_tokens: prov?.input_tokens || 0,
            output_tokens: prov?.output_tokens || 0,
            thoughts_tokens: prov?.thoughts_tokens || 0,
          };
        }
        return {
          ...d,
          displayMonth: d.month.split('-')[1],
        };
      });
  }, [usage?.monthly_data, selectedYear, monthlyProvider]);

  // Get token field based on selection
  const getTokenField = (type: TokenType): string => {
    switch (type) {
      case 'input': return 'input_tokens';
      case 'output': return 'output_tokens';
      case 'thoughts': return 'thoughts_tokens';
      default: return 'all';
    }
  };

  // Get cost field based on token type selection
  const getCostField = (type: TokenType): string => {
    switch (type) {
      case 'input': return 'input_cost';
      case 'output': return 'output_cost';
      case 'thoughts': return 'thoughts_cost';
      default: return 'cost';
    }
  };

  // Chart colors
  const chartColors = {
    cost: isDarkMode ? '#60a5fa' : '#3b82f6',  // Blue
    tokens: isDarkMode ? '#fb923c' : '#f97316', // Orange
    grid: isDarkMode ? '#374151' : '#e5e7eb',
    text: isDarkMode ? '#9ca3af' : '#6b7280',
  };

  if (loading) {
    return (
      <div className="card">
        <div className="card-body text-center py-12 text-slate-500">
          {t.loading}
        </div>
      </div>
    );
  }

  if (!usage) {
    return (
      <div className="card">
        <div className="card-body text-center py-12 text-slate-500">
          {t.usageNoData}
        </div>
      </div>
    );
  }

  const progressPct = Math.min(usage.usage_pct, 100);
  const progressColor =
    progressPct >= alertThreshold * 100
      ? 'bg-[#e84133]'
      : progressPct > 70
      ? 'bg-yellow-500'
      : 'bg-emerald-500';

  return (
    <div className="space-y-6">
      {/* Disclaimer Notice */}
      {showDisclaimer && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-3">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-sm text-amber-700 dark:text-amber-300 flex-1">
              {t.usageDisclaimer}
            </p>
            <button
              onClick={handleDismissDisclaimer}
              className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-200 underline whitespace-nowrap shrink-0 ml-2 cursor-pointer"
            >
              <span className="inline-flex items-center justify-center w-3.5 h-3.5 border border-current rounded">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </span>
              {t.usageDontRemind}
            </button>
          </div>
        </div>
      )}

      {/* Statistics Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card p-4">
          <div className="text-sm text-slate-500 dark:text-slate-400">{usage.month} {t.usageTotal}</div>
          <div className="text-2xl font-bold mt-1 text-blue-600 dark:text-blue-400">
            ${usage.total_cost_usd.toFixed(2)}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-slate-500 dark:text-slate-400">{usage.month} {t.usageRemaining}</div>
          <div className="text-2xl font-bold mt-1 text-emerald-600 dark:text-emerald-400">
            ${usage.remaining_usd.toFixed(2)}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-slate-500 dark:text-slate-400">{usage.month} {t.usageInputTokens}</div>
          <div className="text-2xl font-bold mt-1 text-slate-900 dark:text-white">
            {formatTokenCount(usage.input_tokens || 0)}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-slate-500 dark:text-slate-400">{usage.month} {t.usageOutputTokens}</div>
          <div className="text-2xl font-bold mt-1 text-slate-900 dark:text-white">
            {formatTokenCount(usage.output_tokens || 0)}
          </div>
        </div>
      </div>

      {/* Provider Statistics Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card p-4">
          <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
            <img src={geminiLogo} alt={t.providerGoogle} className="w-5 h-5" />
            <span>{usage.month} {t.providerGoogle}</span>
          </div>
          <div className="text-xl font-bold mt-1 text-slate-900 dark:text-white">
            ${calcProviderCost(usage.provider_details?.google).toFixed(2)}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {t.usageInputTokens}: {formatTokenCount(usage.provider_details?.google?.input_tokens || 0)} / 
            {t.usageOutputTokens}: {formatTokenCount(usage.provider_details?.google?.output_tokens || 0)}
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
            <img src={claudeLogo} alt={t.providerAnthropic} className="w-5 h-5" />
            <span>{usage.month} {t.providerAnthropic}</span>
          </div>
          <div className="text-xl font-bold mt-1 text-slate-900 dark:text-white">
            ${calcProviderCost(usage.provider_details?.anthropic).toFixed(2)}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {t.usageInputTokens}: {formatTokenCount(usage.provider_details?.anthropic?.input_tokens || 0)} / 
            {t.usageOutputTokens}: {formatTokenCount(usage.provider_details?.anthropic?.output_tokens || 0)}
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
            <img src={openaiLogo} alt={t.providerOpenai} className="w-5 h-5" />
            <span>{usage.month} {t.providerOpenai}</span>
          </div>
          <div className="text-xl font-bold mt-1 text-slate-900 dark:text-white">
            ${calcProviderCost(usage.provider_details?.openai).toFixed(2)}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {t.usageInputTokens}: {formatTokenCount(usage.provider_details?.openai?.input_tokens || 0)} / 
            {t.usageOutputTokens}: {formatTokenCount(usage.provider_details?.openai?.output_tokens || 0)}
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="card p-4">
        <div className="flex justify-between text-sm mb-2">
          <div className="flex items-center gap-2">
            <span className="text-slate-500 dark:text-slate-400">
              {usage.month} {t.usagePercentage}: ${usage.total_cost_usd.toFixed(2)} / ${usage.monthly_limit_usd.toFixed(2)}
            </span>
            {/* Budget Edit Button */}
            <div className="relative" ref={budgetEditRef}>
              <button
                onClick={handleBudgetEditClick}
                className="ml-2 px-2.5 h-5 flex items-center text-[10px] font-medium text-white bg-[#1871e6] hover:bg-[#145ab4] rounded shadow-sm hover:scale-105 active:scale-95 transition-all duration-200 cursor-pointer"
              >
                {t.usageModifyBudget}
              </button>
              {/* Budget Edit Popup */}
              <div
                className={`absolute left-0 top-full mt-2 bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 p-3 z-50 origin-top-left transition-all duration-300 ease-in-out ${
                  showBudgetEdit
                    ? 'scale-100 opacity-100 translate-y-0 translate-x-0'
                    : 'scale-0 opacity-0 -translate-y-2 translate-x-2 pointer-events-none'
                }`}
                style={{ minWidth: '280px' }}
              >
                <div className="text-sm text-slate-600 dark:text-slate-300 mb-2">
                  {t.usageCurrentBudget}: ${usage.monthly_limit_usd.toFixed(2)}, {t.usageChangeTo}:
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1 input-rainbow-glow">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 z-10">$</span>
                    <input
                      type="number"
                      value={newBudgetLimit}
                      onChange={(e) => setNewBudgetLimit(e.target.value)}
                      className="input w-full pl-6! pr-3 py-2 text-sm border-slate-300 dark:border-slate-600 dark:bg-slate-700 text-slate-900 dark:text-white"
                      placeholder="50"
                      min="1"
                      step="1"
                      autoFocus
                    />
                  </div>
                  <button
                    onClick={handleBudgetSave}
                    disabled={budgetSaving}
                    className="px-4 py-2 text-sm bg-[#1871e6] hover:bg-[#145ab4] text-white rounded-lg transition-all duration-200 hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
                  >
                    {budgetSaving ? t.saving : t.usageConfirm}
                  </button>
                </div>
              </div>
            </div>
          </div>
          <span className="text-slate-500 dark:text-slate-400">{progressPct.toFixed(1)}%</span>
        </div>
        <div className="progress">
          <div
            className={`progress-bar ${progressColor}`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Daily Usage Chart */}
      <div className="card">
        <div className="card-header">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">{t.usageDailyUsage}</h3>
            <div className="flex items-center gap-3">
              <select
                className="select text-sm py-1 px-2"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
              >
                {usage.available_months?.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <select
                className="select text-sm py-1 px-2"
                value={dailyProvider}
                onChange={(e) => setDailyProvider(e.target.value as ProviderFilter)}
              >
                <option value="all">{providerLabels.all}</option>
                <option value="google">{providerLabels.google}</option>
                <option value="anthropic">{providerLabels.anthropic}</option>
                <option value="openai">{providerLabels.openai}</option>
              </select>
              <select
                className="select text-sm py-1 px-2"
                value={dailyTokenType}
                onChange={(e) => setDailyTokenType(e.target.value as TokenType)}
              >
                <option value="all">{tokenTypeLabels.all}</option>
                <option value="input">{tokenTypeLabels.input}</option>
                <option value="output">{tokenTypeLabels.output}</option>
                <option value="thoughts">{tokenTypeLabels.thoughts}</option>
              </select>
            </div>
          </div>
        </div>
        <div className="card-body">
          {filteredDailyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={filteredDailyData}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} />
                <XAxis 
                  dataKey="displayDate" 
                  stroke={chartColors.text}
                  tick={{ fill: chartColors.text, fontSize: 12 }}
                />
                <YAxis 
                  yAxisId="left" 
                  stroke={chartColors.cost}
                  tick={{ fill: chartColors.text, fontSize: 12 }}
                  tickFormatter={(v) => `$${v.toFixed(2)}`}
                />
                <YAxis 
                  yAxisId="right" 
                  orientation="right" 
                  stroke={chartColors.tokens}
                  tick={{ fill: chartColors.text, fontSize: 12 }}
                  tickFormatter={formatTokenCount}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Bar 
                  yAxisId="left" 
                  dataKey={getCostField(dailyTokenType)} 
                  name={t.usageCost}
                  fill={chartColors.cost} 
                  radius={[4, 4, 0, 0]}
                />
                {dailyTokenType === 'all' ? (
                  <>
                    <Line 
                      yAxisId="right" 
                      type="monotone" 
                      dataKey="input_tokens" 
                      name={tokenTypeLabels.input}
                      stroke="#22c55e" 
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line 
                      yAxisId="right" 
                      type="monotone" 
                      dataKey="output_tokens" 
                      name={tokenTypeLabels.output}
                      stroke={chartColors.tokens} 
                      strokeWidth={2}
                      dot={false}
                    />
                  </>
                ) : (
                  <Line 
                    yAxisId="right" 
                    type="monotone" 
                    dataKey={getTokenField(dailyTokenType)} 
                    name={tokenTypeLabels[dailyTokenType]}
                    stroke={chartColors.tokens} 
                    strokeWidth={2}
                    dot={false}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-12 text-slate-500">
              {t.usageNoData}
            </div>
          )}
        </div>
      </div>

      {/* Monthly Usage Chart */}
      <div className="card">
        <div className="card-header">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">{t.usageMonthlyUsage}</h3>
            <div className="flex items-center gap-3">
              <select
                className="select text-sm py-1 px-2"
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
              >
                {usage.available_years?.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
              <select
                className="select text-sm py-1 px-2"
                value={monthlyProvider}
                onChange={(e) => setMonthlyProvider(e.target.value as ProviderFilter)}
              >
                <option value="all">{providerLabels.all}</option>
                <option value="google">{providerLabels.google}</option>
                <option value="anthropic">{providerLabels.anthropic}</option>
                <option value="openai">{providerLabels.openai}</option>
              </select>
              <select
                className="select text-sm py-1 px-2"
                value={monthlyTokenType}
                onChange={(e) => setMonthlyTokenType(e.target.value as TokenType)}
              >
                <option value="all">{tokenTypeLabels.all}</option>
                <option value="input">{tokenTypeLabels.input}</option>
                <option value="output">{tokenTypeLabels.output}</option>
                <option value="thoughts">{tokenTypeLabels.thoughts}</option>
              </select>
            </div>
          </div>
        </div>
        <div className="card-body">
          {filteredMonthlyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={filteredMonthlyData}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} />
                <XAxis 
                  dataKey="displayMonth" 
                  stroke={chartColors.text}
                  tick={{ fill: chartColors.text, fontSize: 12 }}
                />
                <YAxis 
                  yAxisId="left" 
                  stroke={chartColors.cost}
                  tick={{ fill: chartColors.text, fontSize: 12 }}
                  tickFormatter={(v) => `$${v.toFixed(2)}`}
                />
                <YAxis 
                  yAxisId="right" 
                  orientation="right" 
                  stroke={chartColors.tokens}
                  tick={{ fill: chartColors.text, fontSize: 12 }}
                  tickFormatter={formatTokenCount}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Bar 
                  yAxisId="left" 
                  dataKey={getCostField(monthlyTokenType)} 
                  name={t.usageCost}
                  fill={chartColors.cost} 
                  radius={[4, 4, 0, 0]}
                />
                {monthlyTokenType === 'all' ? (
                  <>
                    <Line 
                      yAxisId="right" 
                      type="monotone" 
                      dataKey="input_tokens" 
                      name={tokenTypeLabels.input}
                      stroke="#22c55e" 
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line 
                      yAxisId="right" 
                      type="monotone" 
                      dataKey="output_tokens" 
                      name={tokenTypeLabels.output}
                      stroke={chartColors.tokens} 
                      strokeWidth={2}
                      dot={false}
                    />
                  </>
                ) : (
                  <Line 
                    yAxisId="right" 
                    type="monotone" 
                    dataKey={getTokenField(monthlyTokenType)} 
                    name={tokenTypeLabels[monthlyTokenType]}
                    stroke={chartColors.tokens} 
                    strokeWidth={2}
                    dot={false}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-12 text-slate-500">
              {t.usageNoData}
            </div>
          )}
        </div>
      </div>


    </div>
  );
}

export default UsageDashboard;
