async (page) => {
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  await page.getByText('Compare methods', {exact: true}).click();
  await page.getByRole('checkbox', {name: 'Hybrid', exact: true}).check();
  await page.getByRole('checkbox', {name: 'Basic', exact: true}).uncheck();
  await page.getByText('Compare methods', {exact: true}).click();
  await page.getByRole('button', {name: 'Sony ZV-E10', exact: true}).click();
  const results = page.getByRole('region', {name: 'Search results', exact: true});
  await results.getByRole('button', {name: /Rank 1/}).waitFor({state: 'visible'});
  check(await results.getByRole('img', {name: /Sony ZV-E10/}).count() >= 2,
    'Sony ZV-E10 photos must appear directly in search results');
  check(await results.getByRole('link', {name: 'Photo by Solomon203', exact: true}).count() >= 2,
    'Result photos must retain their attribution');
  check(await results.getByRole('link', {name: 'CC BY-SA 4.0', exact: true}).count() >= 2,
    'Result photos must retain their license links');
  check(await results.locator('button a').count() === 0,
    'Photo credit links must remain outside product selection buttons');
  return {passed: true, checks: ['visible result photos', 'attribution', 'license', 'separate links']};
}
