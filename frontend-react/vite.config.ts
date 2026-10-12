import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'
import type { Connect } from 'vite'

// Plugin to serve log files from ../logs (.json, .txt, .csv)
function serveLogsPlugin() {
  return {
    name: 'serve-logs',
    configureServer(server: any) {
      return () => {
        server.middlewares.use((req: Connect.IncomingMessage, res: Connect.ServerResponse, next: Connect.NextFunction) => {
          // Serve all log files from ../logs directory (.json, .txt, .csv)
          if (req.url && req.url.startsWith('/logs/')) {
            console.log('[serve-logs] Intercepting request:', req.url)
            
            // Only serve specific file types
            const isValidType = req.url.includes('.json') || req.url.includes('.txt') || req.url.includes('.csv')
            if (!isValidType) {
              console.log('[serve-logs] Invalid file type, passing through')
              next()
              return
            }
            
            // Strip query parameters (cache-busting timestamp) to get the actual filename
            let fileName = req.url.replace('/logs/', '').split('?')[0]
            const filePath = path.join(__dirname, '../logs', fileName)
            
            console.log('[serve-logs] Looking for file:', filePath)
            
            try {
              if (fs.existsSync(filePath)) {
                console.log('[serve-logs] ✅ Found file:', filePath)
                const content = fs.readFileSync(filePath, 'utf-8')
                console.log('[serve-logs] File size:', content.length, 'bytes')
                
                // Set appropriate content type based on file extension
                let contentType = 'application/json'
                if (fileName.endsWith('.txt')) contentType = 'text/plain'
                if (fileName.endsWith('.csv')) contentType = 'text/csv'
                
                res.setHeader('Content-Type', contentType)
                res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate')
                res.setHeader('Pragma', 'no-cache')
                res.setHeader('Expires', '0')
                res.setHeader('Access-Control-Allow-Origin', '*')
                res.end(content)
                return
              } else {
                console.log('[serve-logs] ❌ File not found:', filePath)
              }
            } catch (err) {
              console.error('[serve-logs] Error serving file:', err)
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
        // Use host.docker.internal to reach services from the host
        // This allows React container to reach strategy_worker service
        target: process.env.API_TARGET || 'http://host.docker.internal:5003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '/api'),
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
