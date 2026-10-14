import { defineConfig, loadEnv } from 'vite'
import path from 'path'
import createVitePlugins from './vite/plugins'

export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd())
  const { VITE_APP_ENV } = env
  return {
    base: VITE_APP_ENV === 'production' ? '/' : '/',
    plugins: createVitePlugins(env, command === 'build'),
    // 依赖预构建：显式声明「只在懒加载路由/组件里用到」的第三方依赖，
    // 避免 dev server 运行中才扫描到它们、触发重新预构建，
    // 导致浏览器请求旧的 hash → 504 (Outdated Optimize Dep) / 动态导入失败。
    optimizeDeps: {
      include: ['turndown', 'marked', 'dompurify', 'katex']
    },
    resolve: {
      alias: {
        '~': path.resolve(__dirname, './'),
        '@': path.resolve(__dirname, './src')
      },
      extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue']
    },
    server: {
      port: 3167,
      host: true,
      open: false,
      proxy: {
        // 代理 /ai 开头的请求到 FastAPI 后端
        '/ai': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path
        },
        // 代理 /dev-api 开头的请求
        '/dev-api': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/dev-api/, '')
        },
        // 代理 /profile 开头的静态资源请求（上传文件）
        '/profile': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path
        },
        // 代理 /carousel-static 开头的静态资源请求（预置轮播图）
        '/carousel-static': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path
        },
        // 代理 /rag 开头的请求
        '/rag': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path
        },
        // 代理 /system 开头的 API 请求（排除页面导航）
        '/system': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path,
          bypass: (req) => {
            if (req.headers.accept && req.headers.accept.includes('text/html')) {
              return '/index.html'
            }
          }
        },
        // 代理 /questionBank 开头的 API 请求（排除页面导航）
        '/questionBank': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path,
          bypass: (req) => {
            if (req.headers.accept && req.headers.accept.includes('text/html')) {
              return '/index.html'
            }
          }
        },
        // 代理 /questionMain 开头的 API 请求（排除页面导航）
        '/questionMain': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path,
          bypass: (req) => {
            if (req.headers.accept && req.headers.accept.includes('text/html')) {
              return '/index.html'
            }
          }
        },
        // 代理 /questionError 开头的 API 请求（排除页面导航）
        '/questionError': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path,
          bypass: (req) => {
            if (req.headers.accept && req.headers.accept.includes('text/html')) {
              return '/index.html'
            }
          }
        },
        // 代理 /questionMarked 开头的 API 请求（排除页面导航）
        '/questionMarked': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path,
          bypass: (req) => {
            if (req.headers.accept && req.headers.accept.includes('text/html')) {
              return '/index.html'
            }
          }
        },
        // 代理 /favoriteBank 开头的 API 请求（排除页面导航）
        '/favoriteBank': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path,
          bypass: (req) => {
            if (req.headers.accept && req.headers.accept.includes('text/html')) {
              return '/index.html'
            }
          }
        },
        // 代理 /favoriteQuestion 开头的 API 请求（排除页面导航）
        '/favoriteQuestion': {
          target: 'http://localhost:9101',
          changeOrigin: true,
          rewrite: (path) => path,
          bypass: (req) => {
            if (req.headers.accept && req.headers.accept.includes('text/html')) {
              return '/index.html'
            }
          }
        },
        // WebSocket 代理
        '/ws': {
          target: 'http://localhost:9101',
          ws: true,
          changeOrigin: true
        }
      }
    },
    css: {
      postcss: {
        plugins: [
          {
            postcssPlugin: 'internal:charset-removal',
            AtRule: {
              charset: (atRule) => {
                if (atRule.name === 'charset') {
                  atRule.remove();
                }
              }
            }
          }
        ]
      }
    }
  }
})
