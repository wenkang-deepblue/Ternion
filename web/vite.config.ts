/**
 * Vite configuration for Ternion Web Control Panel.
 *
 * DEVELOPMENT MODE: Reads port configuration from ~/.ternion/config.json
 * to allow dynamic port configuration through the UI.
 *
 * This file will be simplified when switching to production mode.
 * See: docs/ternion_architecture_design_doc.md Section 5.7.4
 */

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import os from 'os'

// Default port values
const DEFAULT_WEB_PORT = 7990
const DEFAULT_BACKEND_PORT = 8000

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

// Load ports at startup
const { webPort, backendPort } = loadPortConfig()

console.log(`[vite] Web port: ${webPort}, Backend port: ${backendPort}`)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
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
})
