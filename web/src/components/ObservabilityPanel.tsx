/**
 * Observability Panel component for Ternion Control Panel.
 *
 * Displays real-time backend processing logs via SSE streaming.
 * Features:
 * - Live log streaming with auto-scroll
 * - Log level filtering (INFO, WARN, ERROR)
 * - Professional log format display
 * - Clickable file paths to reveal in system file manager
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import type { Translations } from '../i18n';
import api from '../api/client';

// Log section icon
import logIconLight from '../assets/icons/realtime_log_light_mode_dp50.svg';
import logIconDark from '../assets/icons/realtime_log_dark_mode_dp50.svg';

interface LogEntry {
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  category: 'LIFECYCLE' | 'WORKFLOW' | 'PROVIDER' | 'USER_ACTION' | 'ERROR';
  message: string;
}

interface ObservabilityPanelProps {
  t: Translations;
  isDarkMode: boolean;
  isVisible?: boolean;
}

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

const LOG_LEVEL_COLORS: Record<string, string> = {
  INFO: 'text-blue-400',
  WARN: 'text-yellow-400',
  ERROR: 'text-red-400',
};

const CATEGORY_COLORS: Record<string, string> = {
  LIFECYCLE: 'text-emerald-400',
  WORKFLOW: 'text-purple-400',
  PROVIDER: 'text-cyan-400',
  USER_ACTION: 'text-amber-400',
  ERROR: 'text-red-400',
};

export function ObservabilityPanel({ t, isDarkMode, isVisible = true }: ObservabilityPanelProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [autoScroll, setAutoScroll] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [lastDownload, setLastDownload] = useState<{
    filePath: string;
    logCount: number;
    timestamp: string;
  } | null>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear any pending reconnect timer
  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  // Disconnect SSE stream
  const disconnectStream = useCallback(() => {
    clearReconnectTimer();
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setStatus('disconnected');
  }, [clearReconnectTimer]);

  // Connect to SSE stream
  const connectToLogStream = useCallback(() => {
    // Clear any existing connection and timer
    clearReconnectTimer();
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setStatus('connecting');
    const es = new EventSource('/api/logs/stream');
    eventSourceRef.current = es;

    es.onopen = () => {
      setStatus('connected');
    };

    es.onmessage = (event) => {
      try {
        const logEntry: LogEntry = JSON.parse(event.data);
        setLogs((prev) => [...prev.slice(-499), logEntry]);
      } catch {
        // Ignore parse errors for malformed messages
      }
    };

    es.onerror = () => {
      setStatus('disconnected');
      es.close();
      eventSourceRef.current = null;
      // Schedule reconnection with timer ref for proper cleanup
      reconnectTimerRef.current = setTimeout(connectToLogStream, 3000);
    };
  }, [clearReconnectTimer]);

  // Connect/disconnect based on visibility
  useEffect(() => {
    if (isVisible) {
      connectToLogStream();
    } else {
      disconnectStream();
    }
    return () => {
      disconnectStream();
    };
  }, [isVisible, connectToLogStream, disconnectStream]);

  useEffect(() => {
    if (!autoScroll || !isVisible) return;
    const id = requestAnimationFrame(() => {
      // Use scrollTop for reliable scrolling (works even after display:none -> block)
      if (logContainerRef.current) {
        logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
      }
    });
    return () => cancelAnimationFrame(id);
  }, [logs, autoScroll, isVisible]);

  const handleClear = () => {
    setLogs([]);
  };

  const handleRevealFile = async (path: string) => {
    try {
      await api.revealFile(path);
    } catch (err) {
      console.error('Failed to reveal file:', err);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const result = await api.downloadLogs();
      if (result.success) {
        setLastDownload({
          filePath: result.file_path,
          logCount: result.log_count,
          timestamp: new Date().toLocaleTimeString(),
        });
      } else {
        setDownloadError(t.logsDownloadError);
      }
    } catch (err) {
      console.error('Failed to download logs:', err);
      setDownloadError(t.logsDownloadError);
    } finally {
      setDownloading(false);
    }
  };

  const formatTimestamp = (iso: string): string => {
    try {
      const date = new Date(iso);
      return date.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3,
      });
    } catch {
      return iso;
    }
  };

  const renderMessage = (message: string) => {
    // Parse [file]...[/file] tags and render as clickable links
    const fileTagRegex = /\[file\](.*?)\[\/file\]/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    while ((match = fileTagRegex.exec(message)) !== null) {
      // Add text before the match
      if (match.index > lastIndex) {
        parts.push(message.slice(lastIndex, match.index));
      }
      // Add clickable file link
      const filePath = match[1];
      parts.push(
        <button
          key={match.index}
          onClick={() => handleRevealFile(filePath)}
          className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 cursor-pointer transition-colors"
          title={t.logsOpenFile}
        >
          {filePath}
        </button>
      );
      lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < message.length) {
      parts.push(message.slice(lastIndex));
    }

    return parts.length > 0 ? parts : message;
  };

  const getStatusIndicator = () => {
    switch (status) {
      case 'connected':
        return (
          <span className="flex items-center gap-1.5 text-emerald-500">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            {t.logsConnected}
          </span>
        );
      case 'connecting':
        return (
          <span className="flex items-center gap-1.5 text-yellow-500">
            <span className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
            {t.logsConnecting}
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1.5 text-red-500">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            {t.logsDisconnected}
          </span>
        );
    }
  };

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <img src={isDarkMode ? logIconDark : logIconLight} alt="" className="w-6 h-6" />
            {t.logsTitle}
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {t.logsDescription}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-sm">{getStatusIndicator()}</div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="w-4 h-4 rounded cursor-pointer"
            />
            {t.logsAutoScroll}
          </label>
          <button
            onClick={handleClear}
            className="btn text-xs w-22 h-10 flex items-center justify-center bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-200 transition-all duration-200 active:scale-95 hover:-translate-y-0.5 hover:bg-[#fae6e4] hover:text-[#e84133] dark:hover:bg-[#fae6e4] dark:hover:text-[#e84133]"
          >
            {t.logsClear}
          </button>
          <button
            onClick={handleDownload}
            disabled={downloading || logs.length === 0}
            className="btn btn-primary text-xs w-22 h-10 whitespace-nowrap"
          >
            {downloading ? t.logsDownloading : t.logsDownload}
          </button>
        </div>
      </div>
      <div className="card-body p-0">
        <div
          ref={logContainerRef}
          className="h-96 overflow-y-auto bg-slate-900 dark:bg-slate-950 p-4 font-mono text-sm"
          style={{ }}
        >
          {logs.length === 0 ? (
            <div className="text-slate-500 text-center py-8">
              {t.logsNoLogs}
            </div>
          ) : (
            logs.map((log, index) => (
              <div key={index} className="whitespace-pre-wrap mb-1 leading-relaxed">
                <span className="text-slate-500">[{formatTimestamp(log.timestamp)}]</span>
                {' '}
                <span className={`font-semibold ${LOG_LEVEL_COLORS[log.level] || 'text-slate-400'}`}>
                  [{log.level}]
                </span>
                {' '}
                <span className={CATEGORY_COLORS[log.category] || 'text-slate-400'}>
                  [{log.category}]
                </span>
                {' '}
                <span className="text-slate-200">{renderMessage(log.message)}</span>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
        {/* Download error notification */}
        {downloadError && (
          <div className="mt-5 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-300">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <span className="font-medium">{downloadError}</span>
            </div>
            <button
              onClick={() => setDownloadError(null)}
              className="text-red-400 hover:text-red-600 dark:hover:text-red-300 transition-colors"
              title="Dismiss"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        {/* Download success notification */}
        {lastDownload && (
          <div className="mt-5 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg px-4 py-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span className="font-medium">{t.logsDownloadSuccess}</span>
              <span className="text-emerald-600 dark:text-emerald-400">
                ({lastDownload.logCount} {t.logsEntriesCount})
              </span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <span className="text-slate-500 dark:text-slate-400">{t.logsDownloadedTo}:</span>
              <button
                onClick={() => handleRevealFile(lastDownload.filePath)}
                className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline underline-offset-2 transition-colors font-mono text-xs cursor-pointer"
                title={t.logsOpenFile}
              >
                {lastDownload.filePath}
              </button>
              <button
                onClick={() => setLastDownload(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                title="Dismiss"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ObservabilityPanel;

