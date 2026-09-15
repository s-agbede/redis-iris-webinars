// Run with the Playwright browser_run_code tool's filename argument against the local API.
async (page) => {
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('http://127.0.0.1:8001');
  await page.locator('#search-query').waitFor();
  check(await page.getByRole('heading', { name: 'Find your next camera.' }).count() === 1, 'The landing page should lead with a simple camera search heading');
  check(await page.locator('.method-result').count() === 0, 'Result lists should appear only after a search');
  check(await page.getByRole('button', { name: 'Sony ZV-E10', exact: true }).count() === 1, 'Provide a short example query');
  await page.getByRole('combobox', { name: 'Search cameras', exact: true }).fill('Sony');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.locator('.product-select').first().waitFor();
  check(await page.locator('.method-result').count() === 1, 'Show one result list at a time');
  const selected = page.locator('.product-select').first();
  await selected.click();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor();
  check(await dialog.evaluate(el => el.matches(':modal')), 'Evidence should open in a modal side panel');
  await page.keyboard.press('Shift+Tab');
  check(await dialog.evaluate(el => el.contains(document.activeElement)), 'Focus must remain inside the side panel');
  await page.keyboard.press('Escape');
  check(await dialog.count() === 0, 'Escape should close evidence');
  check(await selected.evaluate(el => el === document.activeElement), 'Closing evidence should restore focus to the selected result');
  const widths = [];
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    check(await page.locator('.method-result').count() === 1, `One results list at ${width}px`);
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `No horizontal overflow at ${width}px`);
    widths.push(width);
  }
  return { passed: true, checks: ['quiet landing', 'search', 'single results list', 'modal focus', 'Escape and focus restoration', 'responsive layout'], widths };
}
