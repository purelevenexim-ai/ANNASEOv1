const { test, expect } = require('playwright/test');

test('kw2 page audit smoke', async ({ page }) => {
  const token = 'eyJ1c2VyX2lkIjogInVzZXJfNzk0MzFkZmMxYiIsICJlbWFpbCI6ICJrdzJhdWRpdF9saXZlXzE3NzU3MTA3NThAdGVzdC5jb20iLCAicm9sZSI6ICJ1c2VyIiwgImV4cCI6ICIyMDI2LTA1LTA5VDA0OjU5OjE4Ljg2MjQyMCJ9.9ca85b22f1e4a4e10ab03ccbb3b4c4ac21932659df4ccc3c3bf90bbaa9e8b36c';
  const project = 'proj_85ff9d2bff';
  const events = [];

  page.on('console', msg => events.push(`console: ${msg.type()} ${msg.text()}`));
  page.on('pageerror', err => events.push(`pageerror: ${String(err)}`));
  page.on('response', async res => {
    if (res.status() >= 400) {
      let body = '';
      try { body = (await res.text()).slice(0, 240); } catch {}
      events.push(`response: ${res.status()} ${res.url()} ${body}`);
    }
  });

  await page.addInitScript(([t, p]) => {
    localStorage.setItem('annaseo_token', t);
    localStorage.setItem('annaseo_project', p);
  }, [token, project]);

  await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Keywords v2' }).click();
  await expect(page.getByText('Keyword Research')).toBeVisible();

  await page.getByText('New Keyword Research').click();
  await page.getByPlaceholder(/Turmeric 2026/i).fill('UI Default V2 Create');
  await page.getByRole('button', { name: /Create Session/i }).click();
  await page.waitForTimeout(2000);
  const body1 = await page.locator('body').innerText();
  events.push(`assert: default-v2-error-visible=${/mode must be one of: brand, expand, review/i.test(body1)}`);

  await page.getByText('Audit Direct V2').click();
  await page.waitForTimeout(2000);
  const allSessions = await page.getByRole('button', { name: /All Sessions/i }).isVisible().catch(() => false);
  events.push(`assert: existing-session-opened=${allSessions}`);
  if (allSessions) {
    await page.getByRole('button', { name: /All Sessions/i }).click();
    await page.waitForTimeout(1000);
  }

  await page.getByRole('button', { name: /Select/i }).click();
  await page.getByText('Audit Brand A').click();
  await page.getByText('Audit Expand A').click();
  await page.getByRole('button', { name: /Delete 2/i }).click();
  await page.getByRole('button', { name: /^Delete 2$/ }).click();
  await page.waitForTimeout(2500);
  const body2 = await page.locator('body').innerText();
  events.push(`assert: brand-still-visible=${/Audit Brand A/.test(body2)}`);
  events.push(`assert: expand-still-visible=${/Audit Expand A/.test(body2)}`);

  console.log('EVENTS_START');
  for (const ev of events) console.log(ev);
  console.log('EVENTS_END');
});
