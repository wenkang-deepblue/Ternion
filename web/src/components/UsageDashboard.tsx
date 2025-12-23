/**
 * Usage Dashboard component for Ternion Control Panel.
 *
 * Displays current month's usage statistics:
 * - Total cost
 * - Remaining budget
 * - Request count
 * - Cost breakdown by provider
 */

import { useState, useEffect } from 'react';
import api from '../api/client';
import type { UsageData } from '../api/client';
import type { Translations } from '../i18n';

interface UsageDashboardProps {
  t: Translations;
}

export function UsageDashboard({ t }: UsageDashboardProps) {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadUsage();
  }, []);

  const loadUsage = async () => {
    try {
      const data = await api.getUsage();
      setUsage(data);
    } catch (error) {
      console.error('Failed to load usage:', error);
    } finally {
      setLoading(false);
    }
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
    progressPct > 90
      ? 'bg-red-500'
      : progressPct > 70
      ? 'bg-yellow-500'
      : 'bg-emerald-500';

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card p-4">
          <div className="text-sm text-slate-500">{t.usageMonth}</div>
          <div className="text-2xl font-bold mt-1">{usage.month}</div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-slate-500">{t.usageTotal}</div>
          <div className="text-2xl font-bold mt-1 text-blue-600">
            ${usage.total_cost_usd.toFixed(2)}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-slate-500">{t.usageRemaining}</div>
          <div className="text-2xl font-bold mt-1 text-emerald-600">
            ${usage.remaining_usd.toFixed(2)}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-slate-500">{t.usageRequests}</div>
          <div className="text-2xl font-bold mt-1">{usage.request_count}</div>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="card p-4">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-slate-500">
            ${usage.total_cost_usd.toFixed(2)} / ${usage.monthly_limit_usd.toFixed(2)}
          </span>
          <span className="text-slate-500">{progressPct.toFixed(1)}%</span>
        </div>
        <div className="progress">
          <div
            className={`progress-bar ${progressColor}`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Provider Breakdown */}
      {usage.provider_costs && Object.keys(usage.provider_costs).length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3 className="font-semibold">{t.usageByProvider}</h3>
          </div>
          <div className="card-body">
            <div className="space-y-3">
              {Object.entries(usage.provider_costs).map(([provider, cost]) => (
                <div key={provider} className="flex justify-between items-center">
                  <span className="capitalize">{provider}</span>
                  <span className="font-medium">${(cost as number).toFixed(4)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default UsageDashboard;
