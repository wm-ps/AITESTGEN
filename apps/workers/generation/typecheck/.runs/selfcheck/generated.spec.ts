import { test, expect } from '@playwright/test';
test('x', async ({ page }) => {
  const username = process.env.TEST_USERNAME ?? "default";
  const password = process.env.TEST_PASSWORD ?? "default";
  await page.goto("https://example.com");
  await expect(page).toHaveURL(/example/);
});
