import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  use: { baseURL: 'http://localhost:3000' },
  webServer: [
    {
      command: 'cd ../.. && source .venv/bin/activate && uvicorn apps.api.main:app --port 8000',
      port: 8000,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: 'npm run dev',
      port: 3000,
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
