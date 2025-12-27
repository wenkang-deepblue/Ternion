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

export function ObservabilityPanel({ t, isDarkMode }: ObservabilityPanelProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const connectToLogStream = useCallback(() => {
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
      // Attempt reconnection after 3 seconds
      setTimeout(connectToLogStream, 3000);
    };
  }, []);

  useEffect(() => {
    connectToLogStream();
    return () => {
      eventSourceRef.current?.close();
    };
  }, [connectToLogStream]);

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

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
          title="Click to reveal in file manager"
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
            className="btn text-sm bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800 dark:bg-slate-700 dark:text-slate-200 dark:hover:bg-slate-600 dark:hover:text-white transition-all duration-200 active:scale-95"
          >
            {t.logsClear}
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
        </div>
      </div>
    </div>
  );
}

export default ObservabilityPanel;

