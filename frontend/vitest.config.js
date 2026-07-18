import { defineConfig } from 'vitest/config'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// 로직 계층 단위 테스트. svelte 플러그인이 .svelte.js(runes) 파일을 컴파일한다.
// jsdom 환경 — localStorage/document/crypto 등 브라우저 API 필요.
export default defineConfig({
  plugins: [svelte()],
  test: {
    environment: 'jsdom',
    // opaque origin(about:blank)이면 localStorage가 동작하지 않는다 — URL을 명시.
    environmentOptions: { jsdom: { url: 'http://localhost' } },
    setupFiles: ['./src/test-setup.js'],
    globals: true,
    include: ['src/**/*.test.js'],
  },
})
