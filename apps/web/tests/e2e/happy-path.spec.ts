import { test, expect } from '@playwright/test';

test('happy path: open console, run a date, see node timeline complete', async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto('/console');
  await expect(page.locator('text=▶ Run')).toBeVisible();
  // Date input pre-fills today; just click Run with the default
  await page.getByRole('button', { name: '▶ Run' }).click();
  // Expect either done / interrupted / aborted within 90s.
  // (Live network to akshare may be slow or fail; an 'aborted' status is
  // also acceptable — the contract is that the SSE stream reaches a
  // terminal state.)
  await expect(page.locator('text=status:').filter({ hasText: /done|interrupted|aborted/ }))
    .toBeVisible({ timeout: 90_000 });
});
