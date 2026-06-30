// jsdom runtime harness for gimbal/prism/static/app.js
// 用法: node tests/jsdom_harness.js <scenario>
//
// scenarios:
//   initial-load    - 加载, 等 init 完成, 报 state / DOM / 脚本错误
//   click-add-step  - 加载 + 等 init + 模拟点击 #add-step + 报 state+DOM
//   import-ndjson   - 加载 + 等 init + 模拟 _importNdjsonFile 链路 + 报 steps

const { JSDOM } = require('C:/Users/jiaoshouxiang/AppData/Local/Temp/node_modules/jsdom');
const fs = require('fs');

const APP_JS = 'D:/M/ModelRegistry/gimbal/prism/static/app.js';
const INDEX_HTML = 'D:/M/ModelRegistry/gimbal/prism/static/index.html';
const FIXTURE_NDJSON = 'D:/M/ModelRegistry/tests/fixtures/sample_captures.ndjson';
const DUP_FIXTURE_NDJSON = 'D:/M/ModelRegistry/tests/fixtures/dup_captures.ndjson';

const scenario = process.argv[2] || 'initial-load';

let html = fs.readFileSync(INDEX_HTML, 'utf-8');
html = html.replace(/<script\s+src=["']\/static\/app\.js["']\s*><\/script>/, '');

const dom = new JSDOM(html, {
  url: 'http://127.0.0.1:8765/?scenario=' + scenario,
  runScripts: 'outside-only',
  pretendToBeVisual: true,
});
const { window } = dom;
const { document } = window;

// 抓 window 级错误 (关键: 脚本顶层 throw 走这里)
const scriptErrors = [];
window.addEventListener('error', (e) => {
  scriptErrors.push({ type: 'error', msg: String(e.error?.message || e.message), lineno: e.lineno });
});
window.addEventListener('unhandledrejection', (e) => {
  scriptErrors.push({ type: 'rejection', msg: String(e.reason?.message || e.reason) });
});

// Stub fetch
const fetchCalls = [];
let injectedEvents = [];  // 服务端模拟"已注入"的 events
window.fetch = async (url, opts = {}) => {
  fetchCalls.push({ url: String(url), method: opts.method || 'GET', body: opts.body || null });
  if (url.includes('/api/captures/inject')) {
    if (opts.body) {
      try { injectedEvents.push(JSON.parse(opts.body)); } catch (_) {}
    }
    return makeResp(200, { status: 'ok', sid: 'default' });
  }
  if (url.includes('/api/captures') && /[?&]sid=/.test(url)) {
    return makeResp(200, { count: injectedEvents.length, events: injectedEvents, sid: 'default' });
  }
  if (url.includes('/api/draft/')) {
    return makeResp(200, { draft: null });
  }
  return makeResp(200, {});
};
function makeResp(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'ERR',
    json: async () => body,
    text: async () => JSON.stringify(body),
    headers: { get: () => null },
  };
}

class FakeWS {
  constructor() { this.readyState = 1; }
  close() { this.readyState = 3; }
  send() {}
}
window.WebSocket = FakeWS;
window.confirm = () => true;
window.alert = () => {};
window.scrollTo = () => {};

// 注入 app.js (把"执行 + 暴露"放同一个 eval, 让 const 绑定可访问)
const appJs = fs.readFileSync(APP_JS, 'utf-8');
let scriptLoadErr = null;
try {
  // 同一个 Script Record 内: 跑 app.js, 然后把 const/let 提到 window
  window.eval(`
    ${appJs}
    ;window.__probe = {
      state: typeof state !== 'undefined' ? state : null,
      renderAll: typeof renderAll !== 'undefined' ? renderAll : null,
      renderSteps: typeof renderSteps !== 'undefined' ? renderSteps : null,
      _mergeCapturesIntoSteps: typeof _mergeCapturesIntoSteps !== 'undefined' ? _mergeCapturesIntoSteps : null,
      _pullCaptures: typeof _pullCaptures !== 'undefined' ? _pullCaptures : null,
      syncStepEmpty: typeof syncStepEmpty !== 'undefined' ? syncStepEmpty : null,
      _CAP_LIST_MAX: typeof _CAP_LIST_MAX !== 'undefined' ? _CAP_LIST_MAX : null,
    };
  `);
  const probe = window.__probe || {};
  for (const [k, v] of Object.entries(probe)) {
    if (v !== null && v !== undefined) window[k] = v;
  }
} catch (e) {
  scriptLoadErr = {
    msg: String(e.message),
    stack: String(e.stack || '').split('\n').slice(0, 5).join(' | '),
  };
}

function waitForInit() {
  return new Promise((resolve) => {
    const start = Date.now();
    const tick = () => {
      if (window.state && window.state.undoStack && window.state.undoStack.length > 0) {
        return resolve();
      }
      if (Date.now() - start > 3000) return resolve();
      setTimeout(tick, 50);
    };
    tick();
  });
}

(async () => {
  await new Promise((r) => setTimeout(r, 100));
  await waitForInit();

  const w = window;

  if (scenario === 'initial-load') {
    emitReport(w, { note: 'after init', scriptLoadErr });
    return;
  }

  if (scenario === 'click-add-step') {
    const beforeSteps = w.state?.steps?.length ?? 0;
    const btn = w.document.getElementById('add-step');
    if (!btn) {
      emitReport(w, { error: 'add-step button not found', scriptLoadErr });
      return;
    }
    btn.click();
    await new Promise((r) => setTimeout(r, 50));
    emitReport(w, {
      note: 'after add-step click',
      beforeSteps,
      afterSteps: w.state?.steps?.length ?? 0,
      domUpdates: {
        stepListHidden: w.document.getElementById('step-list')?.hidden,
        stepEmptyHidden: w.document.getElementById('step-empty')?.hidden,
        sidebarHasTab: (w.document.getElementById('step-sidebar')?.innerHTML || '').includes('page-tab'),
        tagsHasTag: (w.document.getElementById('step-tags')?.innerHTML || '').includes('step-tag'),
      },
      scriptLoadErr,
    });
    return;
  }

  if (scenario === 'import-ndjson') {
    // v0.5.6: 用 dup_captures.ndjson (5 行含 1 行 method+path 重复) 验证不再 dedup
    const lines = fs.readFileSync(DUP_FIXTURE_NDJSON, 'utf-8').trim().split('\n').filter(Boolean);
    const sid = encodeURIComponent(w.state?.sessionId || 'default');
    fetchCalls.length = 0;
    injectedEvents.length = 0;
    // 模拟 _importNdjsonFile 完整链路: 逐行 inject → pull → merge
    let injectStatus = null;
    for (const line of lines) {
      const ev = JSON.parse(line);
      const r1 = await w.fetch(`/api/captures/inject?sid=${sid}`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(ev),
      });
      injectStatus = r1.status;
    }
    const r2 = await w.fetch(`/api/captures?sid=${sid}`);
    const d = await r2.json();
    w.state.captures = d.events || [];
    const before = w.state.steps.length;
    await w._mergeCapturesIntoSteps();
    const after = w.state.steps.length;
    emitReport(w, {
      note: 'after _importNdjsonFile flow (dup fixture)',
      injectStatus,
      pullStatus: r2.status,
      capturesCount: w.state.captures.length,
      stepsBefore: before,
      stepsAfter: after,
      expectedStepsAfter: lines.length,        // v0.5.6: 应等于 fixture 行数, 不再去重
      domUpdates: {
        stepListHidden: w.document.getElementById('step-list')?.hidden,
        sidebarHasTab: (w.document.getElementById('step-sidebar')?.innerHTML || '').includes('page-tab'),
        tagsHasTag: (w.document.getElementById('step-tags')?.innerHTML || '').includes('step-tag'),
      },
      scriptLoadErr,
    });
    return;
  }

  emitReport(w, { error: 'unknown scenario: ' + scenario });
})();

function emitReport(w, extra = {}) {
  const report = {
    scenario,
    hasState: typeof w.state === 'object' && w.state !== null,
    stateSteps: w.state?.steps?.length ?? null,
    stateCaptures: w.state?.captures?.length ?? null,
    stateUndoStack: w.state?.undoStack?.length ?? null,
    stateCurrentPage: w.state?.currentPage ?? null,
    stateSessionId: w.state?.sessionId ?? null,
    dom: {
      stepListHidden: w.document.getElementById('step-list')?.hidden,
      stepEmptyHidden: w.document.getElementById('step-empty')?.hidden,
      stepSidebarHTMLLen: w.document.getElementById('step-sidebar')?.innerHTML.length,
      stepTagsHTMLLen: w.document.getElementById('step-tags')?.innerHTML.length,
      stepDetailHidden: w.document.getElementById('step-detail')?.hidden,
    },
    fetchCallCount: fetchCalls.length,
    fetchCalls: fetchCalls.slice(0, 5),
    scriptErrors,
    ...extra,
  };
  process.stdout.write(JSON.stringify(report, null, 2));
  process.exit(0);
}
