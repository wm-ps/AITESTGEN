import { test, expect } from '@playwright/test';
import { CREDENTIALS } from '../../support/config';
import { ensureVisible } from '../../support/interactions';

const NAVIGATION_TIMEOUT_MS = 30000;
const ASSERTION_TIMEOUT_MS = 15000;
const TEST_TIMEOUT_MS = 180000;

const SIGN_IN_URL =
  'https://keycloak-poc.onwavemaker.com/realms/CMVDemoRealm/protocol/openid-connect/auth?client_id=cmv-demo&redirect_uri=https%3A%2F%2Fpoc-angular-app.onwavemaker.com%2Fbm_catalog_backoffice_ui%2Freact-pages%2FHome&state=f5ae2e4d-f660-4b52-9c0c-7b873f903418&response_mode=query&response_type=code&scope=openid&nonce=2b31a97a-6917-4a56-98d2-00b6a5c171c8&code_challenge=aouZwVky34Uq8XloDpZfNp7GWQjw0C4mqvY7Bbexbx8&code_challenge_method=S256';

async function assertNoServerError(page: Parameters<typeof test>[0] extends never ? never : any) {
  const bodyText = await page.content();
  const errorMarkers = [
    'Internal Server Error',
    'Exception Report',
    'HTTP Status 500',
    'HTTP Status 404',
    'Service Unavailable',
  ];

  for (const marker of errorMarkers) {
    if (bodyText.includes(marker)) {
      throw new Error(`Server returned an error page instead of the expected content: ${marker}`);
    }
  }
}

test('Sign-in with a missing password', { tag: '@public' }, async ({ page }) => {
  test.setTimeout(TEST_TIMEOUT_MS);

  const response = await page.goto(SIGN_IN_URL, {
    timeout: NAVIGATION_TIMEOUT_MS,
  });

  if (!response || response.status() >= 400) {
    throw new Error(`Failed to load page. HTTP status: ${response?.status()}`);
  }

  await page.waitForLoadState('domcontentloaded', {
    timeout: NAVIGATION_TIMEOUT_MS,
  });
  await assertNoServerError(page);

  const pageTitle = page.getByText('Welcome Back!', { exact: true });
  await expect(pageTitle).toBeVisible({
    timeout: NAVIGATION_TIMEOUT_MS,
  });

  const usernameField = await ensureVisible(page.locator('#username'));
  await usernameField.fill(CREDENTIALS.username, {
    timeout: ASSERTION_TIMEOUT_MS,
  });

  const passwordField = await ensureVisible(page.locator('#password'));
  await expect(passwordField).toHaveValue('', {
    timeout: ASSERTION_TIMEOUT_MS,
  });

  const submitButton = await ensureVisible(
    page.getByRole('button', { name: /login/i }).first(),
  );
  await submitButton.click({
    timeout: ASSERTION_TIMEOUT_MS,
  });

  await expect(pageTitle).toBeVisible({
    timeout: ASSERTION_TIMEOUT_MS,
  });

  const passwordIsMissing = await passwordField.evaluate((element) => {
    const input = element as HTMLInputElement;
    return input.value === '' && input.validity.valueMissing;
  });
  expect(passwordIsMissing).toBe(true);
});