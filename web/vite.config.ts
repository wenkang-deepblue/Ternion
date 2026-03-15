/**
 * Vite configuration for Ternion Web Control Panel.
 *
 * DEVELOPMENT MODE: Reads port configuration from ~/.ternion/config.json
 * to allow dynamic port configuration through the UI.
 *
 * This file will be simplified when switching to production mode.
 * See: docs/ternion_architecture_design_doc.md Section 5.7.4
 */

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import os from 'os'

const DEFAULT_WEB_PORT = 9120
const DEFAULT_BACKEND_PORT = 9110

/**
 * Read port configuration from user config file.
 * Falls back to defaults if file doesn't exist or is invalid.
 */
function loadPortConfig(): { webPort: number; backendPort: number } {
  const configPath = path.join(os.homedir(), '.ternion', 'config.json')

  try {
    if (fs.existsSync(configPath)) {
      const configContent = fs.readFileSync(configPath, 'utf-8')
      const config = JSON.parse(configContent)
      return {
        webPort: config.ports?.web || DEFAULT_WEB_PORT,
        backendPort: config.ports?.backend || DEFAULT_BACKEND_PORT,
      }
    }
  } catch (error) {
    console.warn('[vite] Failed to read port config, using defaults:', error)
  }

  return {
    webPort: DEFAULT_WEB_PORT,
    backendPort: DEFAULT_BACKEND_PORT,
  }
}

const { webPort, backendPort } = loadPortConfig()

console.log(`[vite] Web port: ${webPort}, Backend port: ${backendPort}`)

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Dev mode keeps root-relative paths for the standalone Vite server.
  // Build mode targets the embedded FastAPI mount point at /panel/.
  base: command === 'build' ? '/panel/' : '/',
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
  server: {
    port: webPort,
    proxy: {
      '/api': {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
}))
