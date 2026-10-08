import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'
import type { Connect } from 'vite'

// Plugin to serve JSON files from ../logs
function serveLogsPlugin() {
  return {
    name: 'serve-logs',
    configureServer(server: any) {
      return () => {
        server.middlewares.use((req: Connect.IncomingMessage, res: Connect.ServerResponse, next: Connect.NextFunction) => {
          // Serve JSON files from ../logs directory
          if (req.url && req.url.startsWith('/logs/') && req.url.includes('.json')) {
            // Strip query parameters (cache-busting timestamp) to get the actual filename
            let fileName = req.url.replace('/logs/', '').split('?')[0]
            const filePath = path.join(__dirname, '../logs', fileName)
            
            try {
              if (fs.existsSync(filePath)) {
                const content = fs.readFileSync(filePath, 'utf-8')
                res.setHeader('Content-Type', 'application/json')
                res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate')
                res.setHeader('Pragma', 'no-cache')
                res.setHeader('Expires', '0')
                res.setHeader('Access-Control-Allow-Origin', '*')
                res.end(content)
                return
              }
            } catch (err) {
              console.error(`Error serving ${filePath}:`, err)
            }
          }
          next()
        })
      }
    },
  }
}

export default defineConfig({
  plugins: [react(), serveLogsPlugin()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@components': path.resolve(__dirname, './src/components'),
      '@pages': path.resolve(__dirname, './src/pages'),
      '@hooks': path.resolve(__dirname, './src/hooks'),
      '@stores': path.resolve(__dirname, './src/stores'),
      '@types': path.resolve(__dirname, './src/types'),
      '@utils': path.resolve(__dirname, './src/utils'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    open: false,
    proxy: {
      '/api': {
        target: 'http://localhost:4000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '/api'),
      },
      '/logs/': {
        target: 'http://localhost:4000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/logs/, '/api/logs'),
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom'],
          charts: ['recharts'],
          utils: ['date-fns', 'clsx', 'papaparse'],
        },
      },
    },
  },
})
