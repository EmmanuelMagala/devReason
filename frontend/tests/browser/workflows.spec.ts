import { test, expect, type Page } from '@playwright/test';

const repoId = '11111111-1111-4111-8111-111111111111';
const reviewId = '22222222-2222-4222-8222-222222222222';
const connectionId = '33333333-3333-4333-8333-333333333333';
const finding = {id: 'finding-1', agent: 'security_agent', severity: 'high', type: 'authz', file: 'src/api.py', line: 4, message: 'Missing resource ownership check', suggestion: 'Verify ownership before loading the resource.'};
const saved = {id: reviewId, repo_id: repoId, mode: 'pr', title: 'Validate resource ownership', pr_url: 'https://github.com/acme/widget/pull/1', pr_number: 1, commit_sha: 'a'.repeat(40), status: 'completed', created_at: '2026-10-13T12:00:00Z', findings: [finding], report_markdown: '## Review findings\n\nCheck ownership before loading data.\n\n```python\nassert resource.owner == user.id\n```', coverage: {total_files: 3, eligible_files: 2, reviewed_files: 2, reviewed_paths: ['src/api.py', 'requirements.txt'], skipped_files: 1, skipped_paths: ['README.md'], characters: 345, scope_complete: true}, check_outcomes: {code_analyst: {status: 'completed'}, security_agent: {status: 'completed'}, architecture_agent: {status: 'no_rules'}}, recommendation: 'request_changes', posting_status: 'not_requested'};

async function fixture(page: Page, options: {newUser?: boolean; failure?: boolean; revoked?: boolean; pending?: boolean; noPr?: boolean; snapshot?: boolean; running?: boolean; noRedirect?: boolean; unchangedSelection?: boolean} = {}) {
  let connected = !options.newUser; let review = {...saved, ...(options.snapshot ? {mode: 'snapshot', branch: 'main', pr_url: '', pr_number: 0, status: 'partial', recommendation: 'incomplete', coverage: {...saved.coverage, eligible_files: 120, scope_complete: false, next_offset: 50}} : {}), ...(options.running ? {status: 'running', findings: [], report_markdown: '', recommendation: ''} : {})};
  let rules = [{id: 'r1', content: 'Routes delegate database work to services.', status: 'suggested', source: 'suggested', created_at: saved.created_at}];
  let messages = [{role: 'user', content: 'What should I fix first?'}, {role: 'assistant', content: '**Ownership checks** should come first.\n\n```python\ncheck_owner()\n```'}];
  let posts = 0; let completed = false;
  const repositories = Array.from({length: 121}, (_, i) => ({id: i === 0 ? repoId : `repo-${i}`, owner: i % 2 ? 'org' : 'acme', name: i === 0 ? 'widget' : `project-${String(i).padStart(3, '0')}`, created_at: saved.created_at, github_installation_id: 123, details: {description: 'An engineering workspace with saved code reviews.', language: 'Python', default_branch: 'main', private: true}}));
  if (options.noRedirect) await page.context().route('**/fixture/github-access', route => route.fulfill({contentType: 'text/html', body: '<h1>GitHub repository access fixture</h1><button onclick="fetch(\'/api/test/save-selection\', {method: \'POST\'}).then(() => document.querySelector(\'p\').textContent = \'Selection saved\')">Save selection</button><p></p>'}));
  await page.context().route('**/api/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname; const method = route.request().method();
    if (!path.startsWith('/api/')) return route.continue();
    const json = (data: unknown, status = 200) => route.fulfill({status, contentType: 'application/json', body: JSON.stringify(data)});
    if (path.endsWith('/github/status')) return json({configured: true, connections: connected ? [{id: connectionId, login: 'engineer', status: options.revoked ? 'reconnect_required' : 'connected'}] : []});
    if (path.endsWith('/github/start')) { const target = new URL(route.request().postDataJSON().return_to, 'http://127.0.0.1:5190'); target.searchParams.set('github_ticket', 'fixture-ticket'); return json({authorize_url: target.href}); }
    if (path.endsWith('/github/install')) return json({install_url: options.noRedirect ? 'http://127.0.0.1:5190/fixture/github-access' : 'http://127.0.0.1:5190/settings/integrations?github_return=1&github_notice=Repository%20access%20updated.'});
    if (path === '/api/test/save-selection') { if (!options.unchangedSelection) repositories.push({...repositories[0], id: '44444444-4444-4444-8444-444444444444', name: 'widget-added'}); return json({saved: true}); }
    if (path.endsWith('/github/complete')) { if (completed) return json({detail: 'This connection ticket was already used.'}, 409); completed = true; connected = true; return json({connected: true, connection_id: connectionId}); }
    if (path === '/api/metrics') return json({accepted: true}, 202);
    if (path.endsWith('/github/refresh')) return json({accounts: options.pending ? [] : [{account: 'acme', connection_id: connectionId, installation_id: 123, status: 'connected', manage_url: 'https://github.com/settings/installations/123'}], notices: options.pending ? ['Organization approval is pending. Ask an administrator to approve the App.'] : []});
    if (path === '/api/repos/browse') {
      if (options.failure) return json({detail: 'GitHub repository loading failed. Please retry.'}, 502);
      const q = url.searchParams.get('q') || ''; const account = url.searchParams.get('account'); const currentPage = Number(url.searchParams.get('page') || 1);
      const filtered = repositories.filter(r => r.name.includes(q) && (!account || r.owner === account));
      return json({items: options.revoked || !connected ? [] : filtered.slice((currentPage - 1) * 20, currentPage * 20), total: options.revoked || !connected ? 0 : filtered.length, page: currentPage, page_size: 20, branch_reviews_enabled: true});
    }
    if (path === `/api/repos/${repoId}`) return json(repositories[0]);
    if (path.endsWith('/pulls')) return json({items: options.noPr ? [] : [{number: 1, title: 'Validate resource ownership', url: saved.pr_url, author: 'engineer', branch: 'security-fix', draft: false, commit_sha: saved.commit_sha}], has_next: false});
    if (path.endsWith('/branches')) return json({items: [{name: 'main', commit_sha: saved.commit_sha}]});
    if (path.endsWith('/scope')) return json({commit_sha: saved.commit_sha, paths: Array.from({length: 50}, (_, i) => `src/file-${i}.py`), total_files: 145, eligible_files: 120, offset: 0, next_offset: 50, character_limit: 100000});
    if (path === '/api/reviews' && method === 'POST') { const data = route.request().postDataJSON(); if (data.mode === 'snapshot') review = {...review, mode: 'snapshot', branch: data.branch, pr_url: '', status: 'partial', recommendation: 'incomplete'}; return json({id: reviewId, status: 'pending'}, 202); }
    if (path === '/api/reviews') return json({items: [review], total: 1, page: 1, page_size: 20});
    if (path === `/api/reviews/${reviewId}`) return json(review);
    if (path.endsWith('/stream')) { if (options.running) { review = {...saved}; return route.fulfill({contentType: 'text/event-stream', body: `id: 1-0\ndata: ${JSON.stringify({event: 'complete', data: {status: 'completed'}})}\n\n`}); } return route.fulfill({contentType: 'text/event-stream', body: ''}); }
    if (path.endsWith('/comparison')) return json({previous_review_id: null, new: 1, recurring: 0, resolved: 0, coverage_comparable: true});
    if (path.endsWith('/posting-preview')) return json({body: saved.report_markdown, target_url: saved.pr_url});
    if (path.endsWith('/post')) { if (++posts === 1) { review.posting_status = 'failed'; return json({detail: 'The report is saved, but GitHub posting failed. Check permissions and retry.'}, 502); } review.posting_status = 'posted'; return json({status: 'posted', url: 'https://github.com/acme/widget/pull/1#review-1'}); }
    if (path.endsWith('/conversation')) return json({items: messages, has_more: false, next_cursor: null});
    if (path.endsWith('/chat')) { const {message} = route.request().postDataJSON(); messages = [...messages, {role: 'user', content: message}, {role: 'assistant', content: '**Saved answer** with findings.'}]; return route.fulfill({contentType: 'text/plain', body: '**Saved answer** with findings.'}); }
    if (path.endsWith('/rules') && method === 'GET') return json(rules);
    if (path.endsWith('/rules') && method === 'POST') { const rule = {id: 'r2', ...route.request().postDataJSON(), status: 'approved', source: 'manual', created_at: saved.created_at}; rules.push(rule); return json(rule, 201); }
    if (path.includes('/rules/r1') && method === 'PATCH') { rules[0] = {...rules[0], ...route.request().postDataJSON()}; return json(rules[0]); }
    if (path.includes('/rules/r1') && method === 'DELETE') { rules = rules.filter(r => r.id !== 'r1'); return route.fulfill({status: 204}); }
    return json({detail: `Unhandled fixture endpoint ${path}`}, 404);
  });
}

test('repository cards load while a slow GitHub refresh is still pending', async ({page}) => {
  await fixture(page);
  let release!: () => void;
  const wait=new Promise<void>(resolve => { release=resolve; });
  let refreshing=false;
  await page.context().route('**/api/auth/github/refresh', async route => {
    refreshing=true;
    await wait;
    await route.fulfill({contentType:'application/json',body:JSON.stringify({accounts:[],notices:[]})});
  });
  try {
    await page.goto('/repositories');
    await expect(page.getByRole('heading', {name:'widget',exact:true})).toBeVisible({timeout:5000});
    await expect.poll(() => refreshing).toBe(true);
    await expect(page.getByRole('status')).toContainText('Checking GitHub access in the background');
  } finally { release(); }
});

test('saved reviews do not start a repository sync and history uses summaries', async ({page}) => {
  await fixture(page);
  let syncs=0; let summary=false;
  page.on('request', request => {
    const url=new URL(request.url());
    if (url.pathname.endsWith('/github/refresh')) syncs++;
    if (url.pathname==='/api/reviews' && url.searchParams.get('summary')==='true') summary=true;
  });
  await page.goto('/reviews');
  await expect(page.getByRole('link', {name:/Validate resource ownership/})).toBeVisible();
  expect(summary).toBe(true);
  await page.getByRole('link', {name:/Validate resource ownership/}).click();
  await expect(page.getByRole('heading', {name:'Changes recommended'})).toBeVisible();
  expect(syncs).toBe(0);
});

test('history shows the count from a summary without downloading findings', async ({page}) => {
  await fixture(page);
  await page.context().route('**/api/reviews?*', route => route.fulfill({contentType:'application/json',body:JSON.stringify({items:[{...saved,findings:undefined,report_markdown:undefined,finding_count:42}],total:1,page:1,page_size:20})}));
  await page.goto('/reviews');
  await expect(page.getByRole('link', {name:/42 findings/})).toBeVisible();
  await page.getByRole('link', {name:/42 findings/}).click();
  await expect(page.getByText('Missing resource ownership check')).toBeVisible();
});

async function clickGitHub(page: Page, name: string) {
  const opened = page.waitForEvent('popup');
  await page.getByRole('button', {name, exact: true}).click();
  return opened;
}
async function closed(tab: Page) { await expect.poll(() => tab.isClosed()).toBe(true); }

// Every callback uses a real second browser tab and the production return page.
test('new GitHub connection opens a second tab and refreshes the original repository page', async ({page}) => {
  await fixture(page, {newUser: true}); await page.goto('/repositories');
  await expect(page.getByRole('heading', {name: 'Start with GitHub'})).toBeVisible();
  const tab = await clickGitHub(page, 'Connect GitHub');
  await closed(tab);
  await expect(page).toHaveURL('http://127.0.0.1:5190/repositories');
  await expect(page.getByRole('heading', {name: 'widget', exact: true})).toBeVisible();
  await expect(page.getByLabel('Installation ID')).toHaveCount(0);
});

test('connection keeps the settings page and its original search context', async ({page}) => {
  await fixture(page); await page.goto('/repositories?q=widget&account=acme');
  await page.getByRole('link', {name: 'Missing a repository? Grant access'}).click();
  await expect(page.getByRole('link', {name: 'Back to your workspace', exact: false})).toBeVisible();
  const original = page.url();
  const request = page.waitForRequest(request => request.url().endsWith('/github/start'));
  const tab = await clickGitHub(page, 'Connect GitHub account');
  const callback = new URL((await request).postDataJSON().return_to, original);
  expect(callback.pathname).toBe('/github/return');
  expect(callback.searchParams.get('workspace_return')).toBe('/repositories?q=widget&account=acme');
  await closed(tab); await expect(page).toHaveURL(original);
  await page.getByRole('link', {name: 'Back to your workspace', exact: false}).click();
  await expect(page.getByRole('textbox', {name: 'Search repositories'})).toHaveValue('widget');
});

test('installation callback without query state notifies the original tab safely', async ({page}) => {
  await fixture(page); await page.goto('/repositories?q=widget');
  await page.getByRole('link', {name: 'Missing a repository? Grant access'}).click();
  await expect(page.getByRole('link', {name: 'Back to your workspace', exact: false})).toBeVisible();
  const original = page.url();
  const tab = await clickGitHub(page, 'Grant repository access');
  await closed(tab); await expect(page).toHaveURL(original);
  await expect(page.getByRole('status')).toContainText('Repository access updated.');
  expect(await page.evaluate(() => sessionStorage.getItem('devreason:github-tab'))).toBeNull();
});

for (const screen of ['repositories', 'settings/integrations']) {
  test(`GitHub connect gives immediate feedback and prevents repeat clicks on ${screen}`, async ({page}) => {
    await fixture(page, {newUser: true});
    let release!: () => void; let requests = 0;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/auth/github/start', async route => {
      requests++; await gate;
      const target = new URL(route.request().postDataJSON().return_to, 'http://127.0.0.1:5190');
      target.searchParams.set('github_ticket', 'fixture-ticket');
      await route.fulfill({contentType: 'application/json', body: JSON.stringify({authorize_url: target.href})});
    });
    await page.goto(`/${screen}`);
    const tab = await clickGitHub(page, 'Connect GitHub account');
    await expect(tab.getByText('Opening GitHub… Keep DevReason open in the original tab.')).toBeVisible();
    expect(await tab.evaluate(() => window.opener)).toBeNull();
    const progress = page.getByRole('button', {name: 'Opening GitHub…', exact: true});
    const count = await progress.count(); expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) await expect(progress.nth(i)).toBeDisabled();
    await expect(page.getByRole('status').filter({hasText: 'Opening GitHub in a new tab'})).toBeVisible();
    await expect.poll(() => requests).toBe(1);
    await page.screenshot({path: `../.audit/implementation/github-connecting-${screen.split('/')[0]}.png`});
    release(); await closed(tab);
    await expect(page.getByRole('button', {name: 'Connect GitHub account', exact: true})).toBeEnabled();
  });
}

test('Grant and Manage access open new tabs while preserving the branch workspace link', async ({page}) => {
  await fixture(page);
  const target = `/repos/${repoId}?tab=branches&branch=main#scope`;
  for (const action of ['Grant repository access', 'Manage access']) {
    await page.goto(`/settings/integrations?return_to=${encodeURIComponent(target)}`);
    const original = page.url();
    let release!: () => void; let requests = 0;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/auth/github/install?**', async route => {
      requests++; const params = new URL(route.request().url()).searchParams;
      const callback = new URL(params.get('return_to')!, original);
      expect(callback.pathname).toBe('/github/return');
      expect(callback.searchParams.get('workspace_return')).toBe(target);
      expect(params.get('installation_id')).toBe(action === 'Manage access' ? '123' : null);
      await gate;
      await route.fulfill({contentType: 'application/json', body: JSON.stringify({install_url: 'http://127.0.0.1:5190/settings/integrations?github_return=1&github_notice=Repository%20access%20updated.'})});
    });
    const tab = await clickGitHub(page, action);
    await expect(page.getByRole('button', {name: 'Opening GitHub…', exact: true})).toBeDisabled();
    await expect(page.getByRole('button', {name: 'Connect GitHub account', exact: true})).toBeDisabled();
    await expect(page.getByRole('button', {name: 'Disconnect', exact: true})).toBeDisabled();
    await expect.poll(() => requests).toBe(1);
    await page.screenshot({path: `../.audit/implementation/github-${action.split(' ')[0].toLowerCase()}-pending.png`});
    release(); await closed(tab); await expect(page).toHaveURL(original);
    await expect(page.getByRole('button', {name: action, exact: true})).toBeEnabled();
    await page.unroute('**/api/auth/github/install?**');
  }
  await page.getByRole('link', {name: 'Back to your workspace', exact: false}).click();
  await expect(page.getByLabel('Branch', {exact: true})).toHaveValue('main');
});

for (const mode of ['switch back', 'close tab']) {
  test(`repository changes refresh without a GitHub redirect when users ${mode}`, async ({page}) => {
    await fixture(page, {noRedirect: true});
    await page.goto('/settings/integrations?return_to=%2Frepositories%3Fq%3Dwidget');
    const tab = await clickGitHub(page, 'Grant repository access');
    await expect(tab.getByRole('heading', {name: 'GitHub repository access fixture'})).toBeVisible();
    // The original tab remains usable while the GitHub tab is open.
    await page.getByRole('link', {name: 'Back to your workspace', exact: false}).click();
    await expect(page).toHaveURL('http://127.0.0.1:5190/repositories?q=widget');
    await expect(page.getByRole('heading', {name: 'widget-added', exact: true})).toHaveCount(0);
    const original = page.url();
    let refreshes = 0;
    page.on('request', request => { if (request.url().endsWith('/github/refresh')) refreshes++; });
    // Headless Chrome keeps every tab focused and emits no native focus event.
    // Emulate that browser event; popup/close/callback paths remain real tabs.
    await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    await tab.bringToFront();
    await tab.getByRole('button', {name: 'Save selection'}).click();
    await expect(tab.getByText('Selection saved')).toBeVisible();
    if (mode === 'close tab') await tab.close();
    await page.bringToFront();
    if (mode === 'switch back') await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(page.getByRole('heading', {name: 'widget-added', exact: true})).toBeVisible();
    await expect.poll(() => refreshes).toBeGreaterThan(0);
    await expect(page).toHaveURL(original);
    await expect(page.getByRole('textbox', {name: 'Search repositories'})).toHaveValue('widget');
    await page.screenshot({path: `../.audit/implementation/github-access-refreshed-${mode.replace(' ', '-')}.png`, fullPage: true});
    if (!tab.isClosed()) await tab.close();
  });
}

test('blocked new tabs keep the current page and allow retry without starting authorization', async ({page}) => {
  await page.addInitScript(() => { window.open = () => null; });
  await fixture(page); await page.goto('/settings/integrations');
  let requests = 0;
  page.on('request', request => { if (request.url().includes('/github/install')) requests++; });
  await page.getByRole('button', {name: 'Grant repository access', exact: true}).click();
  await expect(page.getByRole('alert')).toContainText('blocked the GitHub tab');
  await expect(page.getByRole('button', {name: 'Grant repository access', exact: true})).toBeEnabled();
  await expect(page).toHaveURL('http://127.0.0.1:5190/settings/integrations');
  expect(requests).toBe(0);
});

test('saving the existing selection refreshes access when users switch back', async ({page}) => {
  await fixture(page, {noRedirect: true, unchangedSelection: true});
  await page.goto('/settings/integrations');
  const tab = await clickGitHub(page, 'Grant repository access');
  await expect(tab.getByRole('heading', {name: 'GitHub repository access fixture'})).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await tab.bringToFront();
  await tab.getByRole('button', {name: 'Save selection'}).click();
  await expect(tab.getByText('Selection saved')).toBeVisible();
  let refreshes = 0;
  page.on('request', request => { if (request.url().endsWith('/github/refresh')) refreshes++; });
  await page.bringToFront();
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect.poll(() => refreshes).toBeGreaterThan(0);
  await expect(page.getByRole('status')).toContainText('repository access refreshed');
  await expect(page).toHaveURL('http://127.0.0.1:5190/settings/integrations');
  await tab.close();
});

test('failed account verification never appears connected in the original tab', async ({page}) => {
  await fixture(page, {newUser: true});
  await page.context().route('**/api/auth/github/complete', route => route.fulfill({status: 403, contentType: 'application/json', body: JSON.stringify({detail: 'Sign in to the account that started this GitHub connection.'})}));
  await page.goto('/repositories');
  const tab = await clickGitHub(page, 'Connect GitHub');
  await closed(tab);
  await expect(page.getByRole('alert')).toContainText('account that started');
  await expect(page.getByRole('heading', {name: 'Start with GitHub'})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'widget', exact: true})).toHaveCount(0);
});

test('GitHub launch failure closes the temporary tab and permits another attempt', async ({page}) => {
  await fixture(page); await page.goto('/settings/integrations?return_to=%2Frepositories%3Fq%3Dwidget');
  const original = page.url(); let attempts = 0;
  await page.route('**/api/auth/github/install?**', async route => {
    if (++attempts === 1) return route.fulfill({status: 503, contentType: 'application/json', body: JSON.stringify({detail: 'GitHub connection is temporarily unavailable. Please retry shortly.'})});
    return route.fallback();
  });
  await closed(await clickGitHub(page, 'Grant repository access'));
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable');
  await expect(page.getByRole('button', {name: 'Grant repository access', exact: true})).toBeEnabled();
  await closed(await clickGitHub(page, 'Grant repository access'));
  await expect(page).toHaveURL(original); expect(attempts).toBe(2);
});

test('unrelated cross-tab messages cannot finish another GitHub flow', async ({page}) => {
  await fixture(page, {noRedirect: true}); await page.goto('/settings/integrations');
  const request = page.waitForRequest(request => request.url().includes('/github/install'));
  const tab = await clickGitHub(page, 'Grant repository access');
  const id = new URL(new URL((await request).url()).searchParams.get('return_to')!, page.url()).searchParams.get('github_flow')!;
  await expect(tab.getByRole('heading', {name: 'GitHub repository access fixture'})).toBeVisible();
  await tab.evaluate(id => {
    const channel = new BroadcastChannel('devreason:github-tab:' + id);
    channel.postMessage({kind: 'result', flowId: '00000000-0000-4000-8000-000000000000', error: 'forged callback', expires: Date.now() + 60000});
    channel.close();
  }, id);
  await expect(page.getByRole('button', {name: 'GitHub tab open', exact: true})).toBeDisabled();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await tab.close();
});

test('a pending GitHub callback survives reloading the original DevReason tab', async ({page}) => {
  await fixture(page, {noRedirect: true}); await page.goto('/settings/integrations');
  const request = page.waitForRequest(request => request.url().includes('/github/install'));
  const tab = await clickGitHub(page, 'Grant repository access');
  const callback = new URL(new URL((await request).url()).searchParams.get('return_to')!, page.url());
  await expect(tab.getByRole('heading', {name: 'GitHub repository access fixture'})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', {name: 'GitHub tab open', exact: true})).toBeDisabled();
  callback.searchParams.set('github_connected', '1');
  await tab.goto(callback.href); await closed(tab);
  await expect(page.getByRole('button', {name: 'Grant repository access', exact: true})).toBeEnabled();
  await expect(page).toHaveURL('http://127.0.0.1:5190/settings/integrations');
});

test('returning user discovers over 100 repos, reviews a PR, and reopens saved results', async ({page}) => {
  await fixture(page); await page.goto('/repositories');
  await expect(page.getByText('121 repositories · Page 1')).toBeVisible();
  for (let i = 0; i < 6; i++) await page.getByRole('button', {name: 'Next', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'project-120'})).toBeVisible();
  await page.getByRole('textbox', {name: 'Search repositories'}).fill('widget');
  await page.getByRole('link').filter({has: page.getByRole('heading', {name: 'widget', exact: true})}).click();
  await page.getByRole('button', {name: 'Review pull request 1'}).click();
  await expect(page.getByRole('heading', {name: 'Changes recommended'})).toBeVisible();
  await page.reload(); await expect(page.getByText('Missing resource ownership check')).toBeVisible();
  await page.screenshot({path: '../.audit/implementation/review-desktop.png', fullPage: true});
});
test('branch scope is visible before submission and limited results remain explicit', async ({page}) => {
  await fixture(page, {noPr: true, snapshot: true}); await page.goto(`/repos/${repoId}`);
  await page.getByRole('button', {name: 'Review a branch'}).click(); await page.getByLabel('Branch', {exact: true}).selectOption('main');
  await expect(page.getByText('120 eligible files', {exact: false})).toBeVisible();
  await expect(page.getByRole('checkbox')).toHaveCount(50);
  await page.getByRole('button', {name: 'Review selected scope'}).click();
  await expect(page.getByRole('heading', {name: 'Limited or incomplete review'})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Preview GitHub posting'})).toHaveCount(0);
});
test('loading failure has an error and never renders an empty repository result', async ({page}) => {
  await fixture(page, {failure: true}); await page.goto('/repositories');
  await expect(page.getByRole('alert')).toContainText('GitHub repository loading failed');
  await expect(page.getByRole('heading', {name: 'Your repositories will appear here'})).toHaveCount(0);
});
test('organization approval and revoked access have recovery paths', async ({page}) => {
  await fixture(page, {pending: true}); await page.goto('/settings/integrations');
  await expect(page.getByText('Organization approval is pending.', {exact: false})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Grant repository access'})).toBeVisible();
  await page.unroute('**/api/**'); await fixture(page, {revoked: true}); await page.goto('/repositories');
  await expect(page.getByRole('button', {name: 'Reconnect GitHub'})).toBeVisible();
});
test('mobile navigation is keyboard accessible with no horizontal overflow', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844}); await fixture(page); await page.goto('/');
  await page.getByRole('button', {name: 'Open navigation'}).press('Enter');
  await page.getByRole('navigation', {name: 'Main navigation'}).filter({visible: true}).getByRole('link', {name: 'Repositories'}).click();
  await expect(page.getByRole('heading', {name: 'Repositories', exact: true})).toBeVisible();
  await expect(page.getByRole('textbox', {name: 'Search repositories'})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({path: '../.audit/implementation/repositories-mobile.png', fullPage: true});
  for (const route of [`/repos/${repoId}`, `/reviews/${reviewId}`, `/repos/${repoId}/chat`, `/repos/${repoId}/settings`, '/settings/integrations']) {
    await page.goto(route); await expect(page.getByRole('main')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
});
test('chat history renders Markdown and survives reload; approved rules can be edited and deleted', async ({page}) => {
  await fixture(page); await page.goto(`/repos/${repoId}/chat`);
  await expect(page.locator('strong').filter({hasText: 'Ownership checks'})).toBeVisible();
  await page.getByLabel('Message', {exact: true}).fill('Which findings recur?'); await page.getByRole('button', {name: 'Send message'}).click();
  await expect(page.getByText('Saved answer', {exact: false})).toBeVisible(); await page.reload(); await expect(page.getByText('Which findings recur?')).toBeVisible();
  await page.goto(`/repos/${repoId}/settings`); await page.getByRole('button', {name: 'Approve rule'}).click(); await expect(page.getByText('Approved · enforced')).toBeVisible();
  await page.getByRole('button', {name: 'Edit', exact: true}).click(); await page.getByLabel('Edit rule content').fill('Check access before database work.'); await page.getByRole('button', {name: 'Save changes'}).click(); await expect(page.getByText('Check access before database work.')).toBeVisible();
  await page.getByRole('button', {name: 'Delete', exact: true}).click(); await page.getByRole('button', {name: 'Confirm deletion'}).click(); await expect(page.getByText('Check access before database work.')).toHaveCount(0);
});
test('posting failure preserves report and explicit retry succeeds', async ({page}) => {
  await fixture(page); await page.goto(`/reviews/${reviewId}`); await page.getByRole('button', {name: 'Preview GitHub posting'}).click();
  await page.getByRole('button', {name: 'Post this review to GitHub'}).click(); await expect(page.getByRole('alert')).toContainText('report is saved');
  await expect(page.getByRole('heading', {name: 'Review report'})).toBeVisible();
  await page.getByRole('button', {name: 'Post this review to GitHub'}).click(); await expect(page.getByRole('button', {name: 'Posted to GitHub'})).toBeDisabled();
});
test('running review finishes through replay and saved results are independent in two tabs', async ({page, context}) => {
  await fixture(page, {running: true}); await page.goto(`/reviews/${reviewId}`);
  await expect(page.getByRole('heading', {name: 'Changes recommended'})).toBeVisible();
  const second = await context.newPage(); await fixture(second); await second.goto(`/reviews/${reviewId}`);
  await expect(second.getByText('Missing resource ownership check')).toBeVisible();
  await page.reload(); await expect(page.getByText('Missing resource ownership check')).toBeVisible();
});

test('switching reviews through navigation clears the previous report and filters', async ({page}) => {
  await fixture(page); const previous = '44444444-4444-4444-8444-444444444444';
  await page.route('**/api/reviews/*/comparison', route => route.fulfill({contentType: 'application/json', body: JSON.stringify({previous_review_id: previous, new: 1, recurring: 0, resolved: 0, coverage_comparable: true})}));
  await page.route(`**/api/reviews/${previous}`, route => route.fulfill({contentType: 'application/json', body: JSON.stringify({...saved, id: previous, title: 'Previous change', report_markdown: '## Previous result\n\nA distinct saved report.', findings: [{...finding, file: 'src/other.py', message: 'A different finding'}]})}));
  await page.goto(`/reviews/${reviewId}`); await page.getByLabel('Finding file').selectOption('src/api.py');
  await page.getByRole('link', {name: 'Open previous review'}).click();
  await expect(page.getByText('A distinct saved report.')).toBeVisible();
  await expect(page.getByText('A different finding')).toBeVisible();
  await expect(page.getByText('Missing resource ownership check')).toHaveCount(0);
});
