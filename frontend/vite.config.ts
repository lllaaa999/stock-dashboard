import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { copyFileSync, existsSync, mkdirSync, readdirSync, renameSync, rmSync } from 'node:fs';
import path from 'path';
import {defineConfig, type Plugin} from 'vite';
import {VitePWA} from 'vite-plugin-pwa';

/**
 * 构建后自动把 frontend/dist 同步到 web/dist。
 * 服务端 web/main.py 只托管 web/dist，之前这一步靠手工复制，改完前端忘同步就会继续跑旧包。
 * 说明：
 * - 用 fs.cpSync() 在含中文的路径上会触发 Node 24 崩溃 (0xC0000409)，这里手写递归复制；
 * - 先复制到 web/.dist-tmp 再整体换名，复制失败不会清空正在服务的 web/dist。
 */
function syncWebDistPlugin(): Plugin {
  return {
    name: 'alphapulse:sync-web-dist',
    apply: 'build' as const,
    closeBundle: {
      order: 'post' as const,
      handler() {
        const distDir = path.resolve(__dirname, 'dist');
        const webDir = path.resolve(__dirname, '../web');
        const staging = path.join(webDir, '.dist-tmp');
        const target = path.join(webDir, 'dist');

        if (!existsSync(path.join(distDir, 'index.html'))) {
          console.warn('[sync-web-dist] 未找到 dist/index.html，跳过同步');
          return;
        }

        const copyDir = (src: string, dst: string): void => {
          mkdirSync(dst, { recursive: true });
          for (const entry of readdirSync(src, { withFileTypes: true })) {
            const from = path.join(src, entry.name);
            const to = path.join(dst, entry.name);
            if (entry.isDirectory()) copyDir(from, to);
            else copyFileSync(from, to);
          }
        };

        try {
          rmSync(staging, { recursive: true, force: true });
          copyDir(distDir, staging);
          rmSync(target, { recursive: true, force: true });
          renameSync(staging, target);
          this.info(`[sync-web-dist] 已同步 dist -> ${target}`);
        } catch (err) {
          this.error(`[sync-web-dist] 同步失败: ${String(err)}`);
        }
      },
    },
  };
}

export default defineConfig(() => {
  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['icon.svg', 'apple-touch-icon.png', 'pwa-192x192.png', 'pwa-512x512.png', 'pwa-maskable-512x512.png'],
        manifest: {
          id: '/',
          name: 'AlphaPulse L1 极速行情终端',
          short_name: 'AlphaPulse',
          description: '面向 A 股市场的专业级 Level-1 实时五档看盘与技术分析终端',
          theme_color: '#0d0e12',
          background_color: '#0d0e12',
          display: 'standalone',
          orientation: 'any',
          start_url: '/',
          scope: '/',
          icons: [
            {
              src: '/pwa-192x192.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'any',
            },
            {
              src: '/pwa-512x512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'any',
            },
            {
              src: '/pwa-maskable-512x512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'maskable',
            },
          ],
        },
        workbox: {
          globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],
          navigateFallbackDenylist: [/^\/api\//, /^\/ws/],
        },
        devOptions: {
          enabled: true,
          type: 'module',
        },
      }),
      syncWebDistPlugin(),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modify—file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
    },
  };
});
