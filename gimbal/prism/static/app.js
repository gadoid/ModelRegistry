// prism configurator — v1.2.0
// 4-Tab + Card Stack + Pill tags + .auth-blk + 资源网格 + Step 卡片(Sub-Tab)
// + YAML 预览 + drag-sort + cURL 导出 + undo/redo + 快捷键 + drop 上传
//
// 设计原则:
// 1. state 是真相;DOM 反映 state,反之亦然用 bind/unbind 维持。
// 2. 任何破坏性操作(删除 step/user/resource)走 confirm。
// 3. 所有持久化(debounce 800ms + 5s 兜底 + Ctrl+S 立即)经过 saveDraft()。
// 4. server 是事件的真相;UI state.captures 是视图层镜像。
// 5. steps/resources/tags 用稳定 id (uid) 作为 key,展开折叠等状态按 id 跟踪。

const state = {
  sessionId: '',
  services: { 'tidb-test-service': 'https://fin-tidb.21eflag.com/' },
  users: [{
    key: 'codfish', url: 'https://fin-tidb.21eflag.com/',
    username: '', password: '', confirm_password: false,
    expires_in: 7200, token_type: 'Authorization', token: '',
  }],
  tags: ['smoke'],
  resources: {},                                       // name → ResourceDraft
  steps: [],                                           // [{id, capture, key_hint, ...}]
  captures: [],                                        // 来自 WS
  activeTab: 0,
  expandedSteps: new Set(),                            // v0.5.5: 保留供 undo/redo 兼容, 新逻辑不写
  collapsedSteps: new Set(),                           // v0.5.5: 保留供 undo/redo 兼容, 新逻辑不写
  currentPage: 1,                                      // v0.5.5: 1-based 页码, 渲染派生
  expandedStepSid: null,                               // v0.5.5: 当前展开的 step.__sid, 单展开手风琴
  undoStack: [],
  redoStack: [],
  dirty: false,                                        // 本地有未提交变更
  hydrating: false,                                    // loadDraft 期间禁止触发自动保存
  capturesLocallyCleared: false,                       // 本地刚清空,避免 hello 灌回
  autoInjectToSteps: false,                            // v0.5.4: 勾选后, 新 capture 自动合到 step
  showJsonView: false,                                 // YAML 模态本地 JSON 视图
  validation: { m_sid: true, m_name: true, m_req: true, retry_on: true }, // true=valid
};
const PAGE_SIZE = 10;                                  // v0.5.5: 模块级常量, 硬编码

// ── 工具 ──────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
const uid = (() => { let n = 0; return (p = 'id') => `${p}_${++n}_${Date.now().toString(36)}`; })();
const debounce = (fn, ms) => {
  let t;
  const wrapped = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
};
const escapeHtml = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
const escapeAttr = escapeHtml;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 客户端校验
const SID_RE = /^sc_[A-Za-z0-9_]+$/;
const REQ_RE = /^REQ-[A-Za-z0-9._-]+$/;
function validateAll() {
  state.validation.m_sid = SID_RE.test(($('m-sid').value || '').trim());
  state.validation.m_name = (($('m-name').value || '').trim().length > 0);
  const reqs = ($('m-req').value || '').split(',').map((s) => s.trim()).filter(Boolean);
  state.validation.m_req = reqs.every((r) => REQ_RE.test(r));
  // retry_on 必须是数字字符串或空
  const ros = ($('tp-retry-on').value || '').split(',').map((s) => s.trim()).filter(Boolean);
  state.validation.retry_on = ros.every((s) => /^[0-9]{3}$/.test(s) || /^[0-9]{3}-[0-9]{3}$/.test(s));
  // 反映到 UI
  const sidEl = $('m-sid'); sidEl.classList.toggle('invalid', !state.validation.m_sid);
  const nmEl = $('m-name'); nmEl.classList.toggle('invalid', !state.validation.m_name);
  const rqEl = $('m-req'); rqEl.classList.toggle('invalid', !state.validation.m_req);
  const roEl = $('tp-retry-on'); roEl.classList.toggle('invalid', !state.validation.retry_on);
}

// ── Toast ─────────────────────────────────────────────────
const TOAST_MAX = 5;
function toast(msg, kind = 'info', timeoutMs = 3200) {
  const host = $('toast-host');
  if (!host) { alert(msg); return; }
  // 限流:超限去掉最早的
  while (host.children.length >= TOAST_MAX) host.firstChild.remove();
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  const text = document.createElement('span');
  text.textContent = msg;
  text.style.flex = '1';
  const x = document.createElement('button');
  x.className = 'toast-x';
  x.type = 'button';
  x.setAttribute('aria-label', '关闭通知');
  x.textContent = '×';
  x.addEventListener('click', () => el.remove());
  el.appendChild(text);
  el.appendChild(x);
  host.appendChild(el);
  if (timeoutMs > 0) {
    setTimeout(() => {
      el.style.transition = 'opacity .2s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 220);
    }, timeoutMs);
  }
}

// ── 模态确认(替代 window.confirm 阻塞) ────────────────────
function confirmModal(title, body, opts = {}) {
  return new Promise((resolve) => {
    const wrap = document.createElement('div');
    wrap.className = 'confirm-modal';
    wrap.innerHTML = `
      <div class="confirm-box" role="alertdialog" aria-modal="true" aria-labelledby="cf-title-${Date.now()}">
        <header><span id="cf-title-${Date.now()}">${escapeHtml(title)}</span></header>
        <p>${escapeHtml(body)}</p>
        <footer>
          <button class="btn-secondary" data-act="cancel">${escapeHtml(opts.cancel || '取消')}</button>
          <button class="btn-danger" data-act="ok">${escapeHtml(opts.ok || '确定')}</button>
        </footer>
      </div>`;
    document.body.appendChild(wrap);
    const close = (v) => { wrap.remove(); resolve(v); };
    const onKey = (e) => {
      if (e.key === 'Escape') { close(false); document.removeEventListener('keydown', onKey, true); }
      if (e.key === 'Enter' && !e.target.matches('input,textarea')) {
        close(true); document.removeEventListener('keydown', onKey, true);
      }
    };
    document.addEventListener('keydown', onKey, true);
    wrap.addEventListener('click', (e) => {
      if (e.target === wrap) { close(false); document.removeEventListener('keydown', onKey, true); }
      if (e.target.dataset.act === 'cancel') { close(false); document.removeEventListener('keydown', onKey, true); }
      if (e.target.dataset.act === 'ok') { close(true); document.removeEventListener('keydown', onKey, true); }
    });
    wrap.querySelector('[data-act="ok"]').focus();
  });
}

// ── session ───────────────────────────────────────────────
function detectSession() {
  const meta = document.querySelector('meta[name="prism-session"]');
  if (meta) state.sessionId = meta.content;
  else {
    const url = new URL(window.location.href);
    state.sessionId = url.searchParams.get('session') || 'default';
  }
  // v0.5.4+: 同步到 header 输入框
  const inp = $('header-sid-input');
  if (inp) {
    inp.value = state.sessionId;
    inp.placeholder = state.sessionId;
  }
}

// v0.5.4+: 切换 session (从 header 输入框)
async function switchSession(newSid) {
  newSid = (newSid || '').trim();
  if (!newSid) {
    toast('session id 不能为空', 'error', 2000);
    return;
  }
  if (!/^[A-Za-z0-9._-]+$/.test(newSid)) {
    toast('session id 只能含字母数字 . _ -', 'error', 2500);
    return;
  }
  if (newSid === state.sessionId) {
    toast('session 未变化', 'info', 1200);
    return;
  }
  // 1. 提示用户保存未保存的修改
  if (state.dirty) {
    const ok = await confirmModal(
      '切换 session',
      `当前草稿未保存, 切换到 <code>${escapeHtml(newSid)}</code> 会丢失吗?`,
      { ok: '丢弃并切换', cancel: '取消' },
    );
    if (!ok) return;
  }
  // 2. 关闭旧 WS
  try { if (ws) ws.close(); } catch (_) {}
  // 3. 更新 state + URL
  state.sessionId = newSid;
  state.captures = [];
  state.capturesLocallyCleared = false;
  state.steps = [];
  state.undoStack = [];
  state.redoStack = [];
  const url = new URL(window.location.href);
  url.searchParams.set('session', newSid);
  window.history.replaceState({}, '', url);
  // 4. 同步 header
  const inp = $('header-sid-input');
  if (inp) inp.value = newSid;
  syncHeader();
  // 5. 重 loadDraft (从新 session 拉数据) + 重连 WS
  await loadDraft();
  connectWs();
  renderAll();
  toast(`已切换到 session: ${newSid}`, 'success', 2000);
}
const sessPath = () => `/api/draft/${encodeURIComponent(state.sessionId)}`;

// ── Undo / Redo ──────────────────────────────────────────
const HISTORY_MAX = 30;
function snapshot() {
  // 浅克隆,够用
  return JSON.stringify({
    services: state.services, users: state.users, tags: state.tags,
    resources: state.resources, steps: state.steps,
  });
}
function pushHistory() {
  if (state.hydrating) return;
  state.undoStack.push(snapshot());
  if (state.undoStack.length > HISTORY_MAX) state.undoStack.shift();
  state.redoStack.length = 0;
  state.dirty = true;
  scheduleSave();
}
function restoreSnapshot(snap) {
  const d = JSON.parse(snap);
  state.services = d.services; state.users = d.users; state.tags = d.tags;
  state.resources = d.resources; state.steps = d.steps;
  renderAll();
}
function undo() {
  if (state.undoStack.length < 2) { toast('没有可撤销的操作', 'info'); return; }
  const cur = state.undoStack.pop();
  state.redoStack.push(cur);
  const prev = state.undoStack[state.undoStack.length - 1];
  restoreSnapshot(prev);
  toast('已撤销', 'info', 1200);
}
function redo() {
  if (!state.redoStack.length) { toast('没有可重做的操作', 'info'); return; }
  const next = state.redoStack.pop();
  state.undoStack.push(next);
  restoreSnapshot(next);
  toast('已重做', 'info', 1200);
}

// ── Tab 切换 ─────────────────────────────────────────────
function switchTo(idx) {
  if (state.activeTab === idx) return;
  state.activeTab = idx;
  $$('.tab').forEach((t) => {
    const on = +t.dataset.idx === idx;
    t.classList.toggle('active', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  $$('.page').forEach((p) => {
    const pi = +p.dataset.idx;
    if (pi === idx) p.classList.add('active');
    else p.classList.remove('active');
  });
}

// ── field setter (供 loadDraft 共用) ─────────────────────
function setFieldValue(id, v) {
  const el = $(id); if (!el) return;
  if (el.type === 'checkbox') el.checked = !!v;
  else el.value = v == null ? '' : String(v);
}

// ── Meta 字段同步(只 bind 一次) ─────────────────────────
const metaIds = ['m-name','m-desc','m-module','m-author','m-owner','m-version','m-req','m-sid',
                 'tp-seconds','tp-setup','tp-teardown','tp-retry-max','tp-retry-backoff','tp-retry-on'];
let _metaBound = false;
function bindMeta() {
  if (_metaBound) return;
  _metaBound = true;
  metaIds.forEach((id) => {
    const el = $(id);
    el.addEventListener('input', () => {
      syncHeader();
      validateAll();
      scheduleSave();
    });
  });
  $('m-priority').addEventListener('change', () => { syncHeader(); scheduleSave(); });
  $('m-expire').addEventListener('change', (e) => {
    $('m-expire-text').textContent = e.target.checked ? 'true' : 'false';
    scheduleSave();
  });
  $('tp-retry').addEventListener('change', (e) => {
    $('tp-retry-text').textContent = e.target.checked ? 'enabled' : 'null';
    $('retry-fields').hidden = !e.target.checked;
    scheduleSave();
  });
  $('tp-kind').addEventListener('change', scheduleSave);
  syncHeader();
  validateAll();
}
function syncHeader() {
  const sid = $('m-sid').value || 'sc_new';
  const span = $('header-sid');
  if (span) span.textContent = sid;
  // v0.5.4+: 同步 header 输入框 (但只在用户没在编辑时, 避免覆盖用户输入)
  const inp = $('header-sid-input');
  if (inp && document.activeElement !== inp) {
    inp.value = state.sessionId;
  }
}

// ── Pill tags ─────────────────────────────────────────────
function ensureTagIds() {
  state.tags.forEach((t, i) => { if (!t.__tagId) t.__tagId = uid('tag'); });
}
function tagIdByValue(t) { return t.__tagId || (t.__tagId = uid('tag')); }
function renderTags() {
  const wrap = $('tags-wrap');
  wrap.querySelectorAll('.tag-pill').forEach((n) => n.remove());
  state.tags.forEach((t, idx) => {
    const span = document.createElement('span');
    span.className = 'tag-pill';
    span.draggable = true;
    span.dataset.tid = tagIdByValue(t);
    span.title = `拖动重排 · ${t}`;
    span.innerHTML = `${escapeHtml(t)} <b class="tag-x" role="button" aria-label="删除标签 ${escapeAttr(t)}">×</b>`;
    span.querySelector('.tag-x').addEventListener('click', (e) => {
      e.stopPropagation();
      state.tags = state.tags.filter((x) => x !== t);
      pushHistory();
      renderTags();
    });
    bindDragSort(span, idx, (from, to) => {
      const [moved] = state.tags.splice(from, 1);
      state.tags.splice(to, 0, moved);
      pushHistory();
      renderTags();
    });
    wrap.insertBefore(span, $('m-tags'));
  });
}
function bindTagInput() {
  const inp = $('m-tags');
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const v = inp.value.trim();
      if (v && !state.tags.includes(v)) {
        v.__tagId = uid('tag');
        state.tags.push(v);
        pushHistory();
        renderTags();
        toast(`已添加标签: ${v}`, 'success', 1000);
      }
      inp.value = '';
    } else if (e.key === 'Backspace' && !inp.value && state.tags.length) {
      state.tags.pop();
      pushHistory();
      renderTags();
    }
  });
  inp.addEventListener('paste', (e) => {
    const text = (e.clipboardData || window.clipboardData).getData('text');
    if (!/[,\n]/.test(text)) return;
    e.preventDefault();
    const tokens = text.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    let added = 0;
    for (const t of tokens) {
      if (!state.tags.includes(t)) {
        t.__tagId = uid('tag');
        state.tags.push(t); added += 1;
      }
    }
    if (added) { pushHistory(); renderTags(); toast(`已粘贴 ${added} 个标签`, 'success', 1500); }
    inp.value = '';
  });
  inp.addEventListener('click', (e) => e.stopPropagation());
}

// ── Drag-Sort 通用(按索引交换,callback 接收 from/to) ────
function bindDragSort(handleEl, idx, onDrop) {
  handleEl.addEventListener('dragstart', (e) => {
    e.dataTransfer.setData('text/plain', String(idx));
    e.dataTransfer.effectAllowed = 'move';
    handleEl.classList.add('dragging');
  });
  handleEl.addEventListener('dragend', () => {
    handleEl.classList.remove('dragging');
    document.querySelectorAll('.prism-drop-target').forEach((n) => n.classList.remove('prism-drop-target'));
  });
  handleEl.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    handleEl.classList.add('prism-drop-target');
  });
  handleEl.addEventListener('dragleave', () => handleEl.classList.remove('prism-drop-target'));
  handleEl.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    const from = +e.dataTransfer.getData('text/plain');
    const to = idx;
    if (Number.isNaN(from) || from === to) return;
    onDrop(from, to);
  });
}

// ── Services KV ──────────────────────────────────────────
function renderServices() {
  const box = $('services');
  box.innerHTML = '';
  const entries = Object.entries(state.services);
  entries.forEach(([k, v], idx) => {
    const row = document.createElement('div');
    row.className = 'kv-row';
    row.draggable = true;
    row.innerHTML = `
      <input class="k" value="${escapeAttr(k)}" aria-label="服务别名" />
      <input class="v" value="${escapeAttr(v)}" aria-label="服务基址 URL" />
      <button class="del" title="删除" aria-label="删除服务 ${escapeAttr(k)}">×</button>`;
    const [kInp, vInp] = row.querySelectorAll('input');
    let lastK = k;
    kInp.addEventListener('change', () => {
      const nv = vInp.value;
      const nk = kInp.value.trim();
      if (!nk) { toast('服务别名不能为空', 'error'); renderServices(); return; }
      if (nk !== lastK && nk in state.services) { toast(`服务别名已存在: ${nk}`, 'error'); renderServices(); return; }
      delete state.services[lastK];
      state.services[nk] = nv;
      lastK = nk;
      pushHistory();
      renderServices();
    });
    vInp.addEventListener('change', () => {
      const nv = vInp.value.trim();
      try { if (nv) new URL(nv); } catch (_) { toast('URL 格式不正确', 'error'); return; }
      state.services[lastK] = nv;
      pushHistory();
    });
    row.querySelector('.del').addEventListener('click', async () => {
      const ok = await confirmModal('删除服务', `确定删除服务「${lastK}」?`, { ok: '删除' });
      if (!ok) return;
      delete state.services[lastK];
      pushHistory();
      renderServices();
    });
    bindDragSort(row, idx, (from, to) => {
      const keys = Object.keys(state.services);
      const [movedK] = keys.splice(from, 1);
      keys.splice(to, 0, movedK);
      const reordered = {};
      keys.forEach((kk) => { reordered[kk] = state.services[kk]; });
      state.services = reordered;
      pushHistory();
      renderServices();
    });
    box.appendChild(row);
  });
}
$('add-svc').addEventListener('click', (e) => {
  e.stopPropagation();
  let i = 1;
  while (`service${i}` in state.services) i++;
  state.services[`service${i}`] = 'https://';
  pushHistory();
  renderServices();
});

// ── Users (.auth-blk) ────────────────────────────────────
function renderUsers() {
  const box = $('users');
  box.innerHTML = '';
  state.users.forEach((u, i) => {
    const block = document.createElement('div');
    block.className = 'user-block';
    block.dataset.uidx = String(i);
    block.innerHTML = `
      <div class="ub-head">
        <span class="ub-key">user · ${escapeHtml(u.key)}</span>
        <span class="ub-status" data-status="${u.confirm_password ? 'confirmed' : 'redacted'}" aria-live="polite">${u.confirm_password ? '已确认' : '已脱敏'}</span>
        <button class="del" aria-label="删除用户 ${escapeAttr(u.key)}">删除</button>
      </div>
      <div class="field-row"><label>key</label>
        <input class="fin mono" data-f="key" value="${escapeAttr(u.key)}" />
      </div>
      <div class="field-row"><label>url</label>
        <input class="fin" data-f="url" value="${escapeAttr(u.url || '')}" />
      </div>
      <div class="field-row"><label>username</label>
        <input class="fin" data-f="username" value="${escapeAttr(u.username || '')}" />
      </div>
      <div class="field-row"><label>password</label>
        <div class="pwd-row">
          <input class="fin" data-f="password" type="password" value="${escapeAttr(u.password || '')}" />
          <button class="pwd-toggle" aria-label="显示或隐藏密码">显示</button>
          <button class="pwd-clear" aria-label="清空密码" title="清空密码">⌫</button>
        </div>
      </div>
      <div class="field-row"><label>expires_in</label>
        <div>
          <input class="fin" data-f="expires_in" type="number" value="${u.expires_in}" style="width:80px" min="0" />
          <span class="unit">秒</span>
        </div>
      </div>
      <div class="field-row"><label>token_type</label>
        <input class="fin" data-f="token_type" value="${escapeAttr(u.token_type)}" />
      </div>
      <div class="field-row"><label>confirm_pwd</label>
        <label class="tog">
          <input type="checkbox" data-f="confirm_password" ${u.confirm_password ? 'checked' : ''} />
          <span class="tog-slider"></span>
          <span class="tog-text">${u.confirm_password ? '落实值' : '占位'}</span>
        </label>
      </div>
    `;
    block.querySelector('.del').addEventListener('click', async () => {
      const ok = await confirmModal('删除用户', `确定删除用户「${u.key}」?`, { ok: '删除' });
      if (!ok) return;
      state.users.splice(i, 1);
      pushHistory();
      renderUsers();
    });
    block.querySelectorAll('[data-f]').forEach((el) => {
      const f = el.dataset.f;
      const evt = el.type === 'checkbox' ? 'change' : 'input';
      el.addEventListener(evt, () => {
        let v = el.type === 'checkbox' ? el.checked : el.value;
        if (f === 'expires_in') v = Math.max(0, +v || 0);
        if (f === 'password' && v) u.confirm_password = false;
        u[f] = v;
        if (f === 'key') block.querySelector('.ub-key').textContent = `user · ${v}`;
        if (f === 'confirm_password') {
          const status = block.querySelector('.ub-status');
          status.dataset.status = v ? 'confirmed' : 'redacted';
          status.textContent = v ? '已确认' : '已脱敏';
          block.querySelector('.tog-text').textContent = v ? '落实值' : '占位';
        }
        scheduleSave();
      });
    });
    block.querySelector('.pwd-toggle').addEventListener('click', (e) => {
      e.stopPropagation();
      const inp = block.querySelector('[data-f="password"]');
      const showing = inp.type === 'text';
      inp.type = showing ? 'password' : 'text';
      e.target.textContent = showing ? '显示' : '隐藏';
    });
    block.querySelector('.pwd-clear').addEventListener('click', (e) => {
      e.stopPropagation();
      const inp = block.querySelector('[data-f="password"]');
      inp.value = '';
      u.password = '';
      u.confirm_password = false;
      const status = block.querySelector('.ub-status');
      status.dataset.status = 'redacted';
      status.textContent = '已脱敏';
      scheduleSave();
    });
    box.appendChild(block);
  });
}
$('add-user').addEventListener('click', (e) => {
  e.stopPropagation();
  let i = 1;
  while (state.users.some((u) => u.key === `u${i}`)) i++;
  state.users.push({
    key: `u${i}`, url: '', username: '', password: '', confirm_password: false,
    expires_in: 7200, token_type: 'Authorization', token: '',
  });
  pushHistory();
  renderUsers();
});

// ── Resource 网格 + 块 ────────────────────────────────────
function ensureResourceIds() {
  Object.entries(state.resources).forEach(([n, r]) => {
    if (!r.__rid) r.__rid = uid('res');
  });
}
function renderResources() {
  const box = $('resource-list');
  box.innerHTML = '';
  const entries = Object.entries(state.resources);
  ensureResourceIds();
  entries.forEach(([name, r], idx) => {
    const block = document.createElement('div');
    block.className = 'user-block';
    block.dataset.rname = name;
    block.dataset.rid = r.__rid;
    block.draggable = true;
    block.innerHTML = `
      <div class="ub-head">
        <span class="ub-key">${escapeHtml(r.kind)} · ${escapeHtml(name)}</span>
        <button class="del" aria-label="删除资源 ${escapeAttr(name)}">删除</button>
      </div>
      <div class="field-row"><label>name</label>
        <input class="fin mono" data-f="name" value="${escapeAttr(name)}" />
      </div>
      <div class="field-row"><label>kind</label>
        <select class="fin" data-f="kind" aria-label="资源类型">
          ${['mock','mock_ref','file','file_ref','variable'].map((k) =>
            `<option value="${k}" ${r.kind === k ? 'selected' : ''}>${k}</option>`).join('')}
        </select>
      </div>
      ${r.kind === 'mock' ? `
        <div class="field-row"><label>image</label><input class="fin" data-f="image" value="${escapeAttr(r.image || '')}" /></div>
        <div class="field-row"><label>config (JSON)</label><textarea class="fin fta mono" data-f="config" rows="2">${escapeHtml(JSON.stringify(r.config || {}, null, 2))}</textarea></div>
        <div class="field-row"><label>portMapping</label><textarea class="fin fta mono" data-f="port_mapping" rows="2">${escapeHtml(JSON.stringify(r.port_mapping || {}, null, 2))}</textarea></div>
      ` : ''}
      ${r.kind === 'file' ? `<div class="field-row"><label>path</label><input class="fin" data-f="path" value="${escapeAttr(r.path || '')}" /></div>` : ''}
      ${r.kind.endsWith('_ref') ? `<div class="field-row"><label>ref</label><input class="fin" data-f="ref" value="${escapeAttr(r.ref || '')}" /></div>` : ''}
      ${r.kind === 'variable' ? `<div class="field-row"><label>value</label><input class="fin mono" data-f="value" value="${escapeAttr(r.value ?? '')}" /></div>` : ''}
    `;
    block.querySelector('.del').addEventListener('click', async () => {
      const ok = await confirmModal('删除资源', `确定删除资源「${name}」?`, { ok: '删除' });
      if (!ok) return;
      delete state.resources[name];
      pushHistory();
      renderResources();
    });
    block.querySelectorAll('[data-f]').forEach((el) => {
      const evt = el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input';
      el.addEventListener(evt, () => {
        const f = el.dataset.f;
        let v = el.value;
        if (f === 'config' || f === 'port_mapping') {
          try { v = JSON.parse(v); el.classList.remove('invalid'); }
          catch (_) { el.classList.add('invalid'); toast(`JSON 解析失败: ${f}`, 'error'); return; }
        }
        if (f === 'name') {
          const nn = v.trim();
          if (!nn) { toast('name 不能为空', 'error'); renderResources(); return; }
          if (nn !== name) {
            if (nn in state.resources) { toast(`name 已存在: ${nn}`, 'error'); renderResources(); return; }
            const val = state.resources[name];
            delete state.resources[name];
            val.name = nn;
            state.resources[nn] = val;
            pushHistory();
            renderResources();
            return;
          }
        } else {
          r[f] = v;
          if (f === 'kind') { pushHistory(); renderResources(); return; }
          scheduleSave();
        }
      });
    });
    bindDragSort(block, idx, (from, to) => {
      const keys = Object.keys(state.resources);
      const [movedK] = keys.splice(from, 1);
      keys.splice(to, 0, movedK);
      const reordered = {};
      keys.forEach((kk) => { reordered[kk] = state.resources[kk]; });
      state.resources = reordered;
      pushHistory();
      renderResources();
    });
    box.appendChild(block);
  });
  $('resource-empty-hint').hidden = entries.length > 0;
}
$$('.resource-tile').forEach((tile) => {
  const handler = (e) => {
    e.stopPropagation();
    const kind = tile.dataset.rkind;
    const map = { db: 'mock', mock: 'mock', file: 'file', variable: 'variable' };
    let i = 1;
    while (state.resources[`${map[kind]}_${i}`]) i++;
    const name = `${map[kind]}_${i}`;
    const r = {
      name, kind: map[kind], image: 'nginx:latest', config: {}, port_mapping: {},
      path: '', ref: '', value: null,
    };
    r.__rid = uid('res');
    state.resources[name] = r;
    pushHistory();
    renderResources();
  };
  tile.addEventListener('click', handler);
  tile.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handler(e); }
  });
});

// ── Steps ────────────────────────────────────────────────
function cURLForStep(s) {
  const api = s.api || {};
  const method = (api.method || 'GET').toUpperCase();
  const svc = (api.service || '').replace(/\/+$/, '');
  const path = api.path || '/';
  const url = svc ? `${svc}${path}` : path;
  const req = s.req || {};
  const headers = { ...(req.headers || {}) };
  if (s.usersKey) headers.Authorization = `Bearer ${s.usersKey}`;
  const params = req.params || {};
  const body = req.body;
  const lines = [`curl -X ${method} ${JSON.stringify(url)}`];
  for (const [k, v] of Object.entries(headers)) lines.push(`  -H ${JSON.stringify(`${k}: ${v}`)}`);
  if (Object.keys(params).length) {
    const qs = new URLSearchParams(params).toString();
    lines[0] = `curl -X ${method} ${JSON.stringify(url + (url.includes('?') ? '&' : '?') + qs)}`;
  }
  if (body && Object.keys(body).length && method !== 'GET') {
    lines.push(`  --data-raw ${JSON.stringify(JSON.stringify(body))}`);
  }
  return lines.join(' \\\n');
}
function _pathSlug(p) { return (p || '').replace(/[^a-zA-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 32) || 'step'; }
function _renderStepCardBody(s, globalIdx) {
  // 抽出原 renderSteps() 内的 step-card innerHTML 生成代码
  // globalIdx: step 在 state.steps 中的全局索引 (0-based), 用于 seq 编号和 url-preview id
  const method = s.api?.method || s.capture?.method || 'GET';
  const path = s.api?.path || s.capture?.path || '/';
  const status = s.capture?.response?.status;
  const ms = s.capture?.response_ms;
  const isExpanded = !state.collapsedSteps.has(s.__sid);
  return `
    <div class="shdr" role="button" tabindex="0" aria-expanded="${isExpanded}" aria-controls="sbody-${s.__sid}">
      <span class="seq">${globalIdx + 1}-${escapeHtml(s.key_hint || _pathSlug(path) || 'step')}</span>
      <span class="method-pill ${method}">${method}</span>
      <span class="path" title="${escapeAttr(path)}">${escapeHtml(path)}</span>
      ${status ? `<span class="status-badge s${Math.floor(status / 100)}xx">${status}</span>` : ''}
      ${ms != null ? `<span class="ms-pill">${ms}ms</span>` : ''}
      <span class="grow"></span>
      <button class="curl-copy" title="复制 cURL" aria-label="复制 cURL 命令">cURL</button>
      <button class="del" aria-label="删除 Step ${globalIdx + 1}">删除</button>
      <button class="toggle-exp" aria-expanded="${isExpanded}" aria-controls="sbody-${s.__sid}">${isExpanded ? '收起' : '展开'}</button>
    </div>
    <div class="sbody" id="sbody-${s.__sid}" role="region" aria-label="Step ${globalIdx + 1} 详情">
      <div class="sub-tabs" role="tablist">
        <button class="active" data-sub="api" role="tab" aria-selected="true">API</button>
        <button data-sub="req" role="tab" aria-selected="false">Request</button>
        <button data-sub="str" role="tab" aria-selected="false">Strategy</button>
      </div>
      <div class="url-preview" id="url-preview-${globalIdx}"></div>
      <div class="sub-pane" data-pane="api">
        <div class="field-row"><label>service</label>
          <input class="fin mono" data-sf="service" value="${escapeAttr(s.api?.service || '')}" list="svc-list" />
          <datalist id="svc-list">
            ${Object.keys(state.services).map((k) => `<option value="${escapeAttr(k)}">`).join('')}
          </datalist>
        </div>
        <div class="field-row"><label>method</label>
          <select class="fin" data-sf="method">
            ${['GET','POST','PUT','DELETE','PATCH','HEAD','OPTIONS'].map((m) =>
              `<option ${s.api?.method === m ? 'selected' : ''}>${m}</option>`).join('')}
          </select>
        </div>
        <div class="field-row"><label>path</label>
          <input class="fin mono" data-sf="path" value="${escapeAttr(s.api?.path || '')}" />
        </div>
        <div class="field-row"><label>key_hint</label>
          <input class="fin" data-sf="key_hint" value="${escapeAttr(s.key_hint || '')}" placeholder="如 call_login" />
        </div>
      </div>
      <div class="sub-pane" data-pane="req" hidden>
        <div class="field-row"><label>params (JSON)</label>
          <textarea class="fin fta mono" data-sf="params" rows="2">${escapeHtml(JSON.stringify(s.req?.params || {}, null, 2))}</textarea>
        </div>
        <div class="field-row"><label>body (JSON)</label>
          <textarea class="fin fta mono" data-sf="body" rows="6">${escapeHtml(JSON.stringify(s.req?.body || {}, null, 2))}</textarea>
        </div>
        <div class="field-row"><label>headers (JSON)</label>
          <textarea class="fin fta mono" data-sf="headers" rows="3">${escapeHtml(JSON.stringify(s.req?.headers || {}, null, 2))}</textarea>
        </div>
      </div>
      <div class="sub-pane" data-pane="str" hidden>
        <div id="str-list-${s.__sid}"></div>
        <div class="add-row">
          <button class="add-btn" data-add="assertion">+ assertion</button>
          <button class="add-btn" data-add="extract">+ extract</button>
          <button class="add-btn" data-add="assign">+ assign</button>
        </div>
      </div>
    </div>
  `;
}
function updateUrlPreview(card, s) {
  const el = card.querySelector('.url-preview');
  if (!el) return;
  const api = s.api || {};
  const svc = state.services[api.service] || (api.service || '');
  const method = (api.method || 'GET').toUpperCase();
  const path = api.path || '/';
  const full = svc ? `${svc.replace(/\/+$/, '')}${path}` : path;
  const color = { GET: '#166534', POST: '#4c1d95', PUT: '#854d0e', DELETE: '#881337', PATCH: '#155e75' }[method] || '#64748b';
  el.innerHTML = `<span class="up-method" style="color:${color}">${method}</span> <code>${escapeHtml(full)}</code>`;
}
function syncStepEmpty() { $('step-empty').hidden = state.steps.length > 0; }
function ensureStepIds() { state.steps.forEach((s) => { if (!s.__sid) s.__sid = uid('step'); }); }

function renderStepSidebar() {
  const nav = $('step-sidebar');
  if (!nav) return;
  if (state.steps.length === 0) { nav.innerHTML = ''; return; }
  const ranges = _computePageRanges();
  nav.innerHTML = ranges.map((r, i) => {
    const active = (i + 1) === state.currentPage;
    return `<button class="page-tab${active ? ' active' : ''}" data-page="${i + 1}" role="tab" aria-selected="${active}">
      ${r.label}<span class="page-count">${r.end - r.start} / ${state.steps.length}</span>
    </button>`;
  }).join('');
  nav.querySelectorAll('.page-tab').forEach((b) => {
    b.addEventListener('click', () => {
      const k = parseInt(b.dataset.page, 10);
      if (!Number.isFinite(k)) return;
      state.currentPage = Math.min(Math.max(1, k), _computePageRanges().length || 1);
      renderSteps();
    });
  });
}

function renderStepTags() {
  const box = $('step-tags');
  if (!box) return;
  if (state.steps.length === 0) { box.innerHTML = ''; return; }
  const ranges = _computePageRanges();
  const range = ranges[state.currentPage - 1];
  if (!range) { box.innerHTML = ''; return; }
  const pageSteps = state.steps.slice(range.start, range.end);
  box.innerHTML = pageSteps.map((s) => {
    const method = (s.api?.method || s.capture?.method || 'GET').toUpperCase();
    const path = s.api?.path || s.capture?.path || '/';
    const active = state.expandedStepSid === s.__sid;
    return `<div class="step-tag${active ? ' active' : ''}" data-sid="${escapeAttr(s.__sid)}" draggable="true" role="listitem" tabindex="0">
      <span class="method-pill ${method}">${method}</span>
      <span class="path" title="${escapeAttr(path)}">${escapeHtml(path)}</span>
      <button class="del" aria-label="删除 Step">×</button>
    </div>`;
  }).join('');
  // 事件: tag click → 展开/收起
  box.querySelectorAll('.step-tag').forEach((tagEl) => {
    const sid = tagEl.dataset.sid;
    tagEl.addEventListener('click', (e) => {
      if (e.target.closest('.del')) return;  // 删除按钮独立处理
      state.expandedStepSid = (state.expandedStepSid === sid) ? null : sid;
      renderSteps();
    });
    tagEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        state.expandedStepSid = (state.expandedStepSid === sid) ? null : sid;
        renderSteps();
      }
    });
  });
  // 删除按钮
  box.querySelectorAll('.step-tag .del').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const tagEl = btn.closest('.step-tag');
      const sid = tagEl?.dataset.sid;
      const globalIdx = state.steps.findIndex((x) => x.__sid === sid);
      if (globalIdx < 0) return;
      const s = state.steps[globalIdx];
      const method = s.api?.method || s.capture?.method || 'GET';
      const path = s.api?.path || s.capture?.path || '/';
      const ok = await confirmModal('删除 Step', `确定删除 Step ${globalIdx + 1} (${method} ${path})?`, { ok: '删除' });
      if (!ok) return;
      state.steps.splice(globalIdx, 1);
      if (state.expandedStepSid === sid) state.expandedStepSid = null;
      pushHistory();
      _syncStepPagination();
      renderSteps();
    });
  });
  // 拖拽重排 (当前页内 10 个 tag)
  let _dragFromIdx = null;
  box.querySelectorAll('.step-tag').forEach((tagEl) => {
    tagEl.addEventListener('dragstart', (e) => {
      const sid = tagEl.dataset.sid;
      _dragFromIdx = state.steps.findIndex((x) => x.__sid === sid);
      tagEl.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    tagEl.addEventListener('dragend', () => {
      tagEl.classList.remove('dragging');
      box.querySelectorAll('.step-tag.drag-over').forEach((x) => x.classList.remove('drag-over'));
      _dragFromIdx = null;
    });
    tagEl.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (_dragFromIdx == null) return;
      tagEl.classList.add('drag-over');
    });
    tagEl.addEventListener('dragleave', () => {
      tagEl.classList.remove('drag-over');
    });
    tagEl.addEventListener('drop', (e) => {
      e.preventDefault();
      tagEl.classList.remove('drag-over');
      if (_dragFromIdx == null) return;
      const sid = tagEl.dataset.sid;
      const toGlobalIdx = state.steps.findIndex((x) => x.__sid === sid);
      if (toGlobalIdx < 0 || toGlobalIdx === _dragFromIdx) return;
      // 仅在当前页内允许重排 (pageSteps 内)
      const range = _computePageRanges()[state.currentPage - 1];
      if (!range) return;
      if (_dragFromIdx < range.start || _dragFromIdx >= range.end) return;
      if (toGlobalIdx < range.start || toGlobalIdx >= range.end) return;
      const [moved] = state.steps.splice(_dragFromIdx, 1);
      state.steps.splice(toGlobalIdx, 0, moved);
      pushHistory();
      scheduleSave();
      renderSteps();
    });
  });
}

function renderStepDetail() {
  const det = $('step-detail');
  if (!det) return;
  if (!state.expandedStepSid) { det.hidden = true; det.innerHTML = ''; return; }
  const s = state.steps.find((x) => x.__sid === state.expandedStepSid);
  if (!s) { det.hidden = true; det.innerHTML = ''; return; }
  const globalIdx = state.steps.indexOf(s);
  det.hidden = false;
  det.innerHTML = `<div class="step-card" data-sid="${escapeAttr(s.__sid)}" data-idx="${globalIdx}">${_renderStepCardBody(s, globalIdx)}</div>`;
  // 触发原 step-card 内部的事件绑定 (复用现有 attach logic)
  // 简化: 重新走一遍原 renderSteps 内的事件绑定 (见 attachStepCardEvents)
  attachStepCardEvents(det.querySelector('.step-card'), s, globalIdx);
}

function attachStepCardEvents(card, s, globalIdx) {
  // 抽出原 renderSteps() 内的 step-card 事件绑定代码 (约 app.js:789-936)
  // 输入: card DOM 元素 + step 对象 + 全局索引
  // 行为: 绑定 shdr click / del / curl-copy / sub-tabs / data-sf / strategy items
  const shdr = card.querySelector('.shdr');
  shdr.addEventListener('click', (e) => {
    if (e.target.closest('button')) return;
    toggleStep(s, card);
  });
  shdr.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      if (e.target === shdr) { e.preventDefault(); toggleStep(s, card); }
    }
  });
  const method = s.api?.method || s.capture?.method || 'GET';
  const path = s.api?.path || s.capture?.path || '/';
  card.querySelector('.shdr .del').addEventListener('click', async (e) => {
    e.stopPropagation();
    const ok = await confirmModal('删除 Step', `确定删除 Step ${globalIdx + 1} (${method} ${path})?`, { ok: '删除' });
    if (!ok) return;
    state.steps.splice(globalIdx, 1);
    state.expandedSteps.delete(s.__sid);
    state.collapsedSteps.delete(s.__sid);
    if (state.expandedStepSid === s.__sid) state.expandedStepSid = null;
    _syncStepPagination();
    pushHistory();
    renderSteps();
  });
  card.querySelector('.toggle-exp').addEventListener('click', (e) => {
    e.stopPropagation();
    toggleStep(s, card);
  });
  card.querySelector('.curl-copy').addEventListener('click', async (e) => {
    e.stopPropagation();
    const text = cURLForStep(s);
    try { await navigator.clipboard.writeText(text); toast(`Step ${globalIdx + 1} cURL 已复制`, 'success', 1500); }
    catch (_) { toast('复制失败', 'error'); }
  });
  card.querySelectorAll('.sub-tabs button').forEach((b) => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      card.querySelectorAll('.sub-tabs button').forEach((x) => {
        x.classList.remove('active');
        x.setAttribute('aria-selected', 'false');
      });
      b.classList.add('active');
      b.setAttribute('aria-selected', 'true');
      card.querySelectorAll('.sub-pane').forEach((p) => { p.hidden = p.dataset.pane !== b.dataset.sub; });
    });
  });
  card.querySelectorAll('[data-sf]').forEach((el) => {
    el.addEventListener('input', () => {
      const f = el.dataset.sf;
      let v = el.value;
      if (['params','body','headers'].includes(f)) {
        try { v = JSON.parse(v); el.classList.remove('invalid'); }
        catch (_) { el.classList.add('invalid'); toast(`JSON 解析失败: ${f}`, 'error', 1800); return; }
      }
      if (f === 'service' || f === 'method' || f === 'path') {
        s.api = s.api || {}; s.api[f] = v;
      } else if (f === 'key_hint') {
        s.key_hint = v;
      } else {
        s.req = s.req || {}; s.req[f] = v;
      }
      if (f === 'method' || f === 'path' || f === 'service') {
        updateUrlPreview(card, s);
        if (f === 'method' || f === 'path') {
          card.querySelector('.method-pill').textContent = (s.api.method || 'GET').toUpperCase();
          card.querySelector('.method-pill').className = `method-pill ${s.api.method || 'GET'}`;
          card.querySelector('.path').textContent = s.api.path || '/';
          card.querySelector('.path').title = s.api.path || '/';
          const seq = card.querySelector('.seq');
          seq.textContent = `${globalIdx + 1}-${s.key_hint || _pathSlug(s.api.path) || 'step'}`;
        }
      }
      scheduleSave();
    });
  });
  s.assertions = s.assertions || [];
  s.extracts = s.extracts || [];
  s.assigns = s.assigns || [];
  const strList = card.querySelector(`#str-list-${s.__sid}`);
  function renderStr() {
    strList.innerHTML = '';
    const items = [
      ...s.assertions.map((a) => ({ kind: 'assertion', data: a })),
      ...s.extracts.map((e) => ({ kind: 'extract', data: e })),
      ...s.assigns.map((a) => ({ kind: 'assign', data: a })),
    ];
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state-sm';
      empty.textContent = '尚无策略 — 添加 assertion / extract / assign';
      strList.appendChild(empty);
      return;
    }
    items.forEach((it) => {
      const div = document.createElement('div');
      div.className = 'strategy-item';
      const summary = it.kind === 'assertion'
        ? `${it.data.target || 'response_status'} ${it.data.operator || 'eq'} ${JSON.stringify(it.data.expected)}`
        : it.kind === 'extract'
          ? `${it.data.expression} → ${it.data.target}`
          : `${it.data.source} → ${it.data.target}`;
      div.innerHTML = `
        <span class="type-pill">${it.kind}</span>
        <span class="target" title="${escapeAttr(summary)}">${escapeHtml(summary)}</span>
        <button class="edit" aria-label="编辑">✎</button>
        <button class="del" aria-label="删除">×</button>`;
      div.querySelector('.del').addEventListener('click', (e) => {
        e.stopPropagation();
        if (it.kind === 'assertion') s.assertions = s.assertions.filter((x) => x !== it.data);
        if (it.kind === 'extract') s.extracts = s.extracts.filter((x) => x !== it.data);
        if (it.kind === 'assign') s.assigns = s.assigns.filter((x) => x !== it.data);
        pushHistory();
        renderStr();
      });
      div.querySelector('.edit').addEventListener('click', (e) => {
        e.stopPropagation();
        openStrategyEditor(it, () => { pushHistory(); renderStr(); });
      });
      strList.appendChild(div);
    });
  }
  renderStr();
  card.querySelectorAll('[data-add]').forEach((b) => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      const k = b.dataset.add;
      const newItem = k === 'assertion'
        ? { name: `a${s.assertions.length}`, target: 'response_status', operator: 'eq', expected: 200, message: '' }
        : k === 'extract'
          ? { name: `e${s.extracts.length}`, expression: '$.data.id', target: 'id', scope: 'scenario' }
          : { name: `as${s.assigns.length}`, source: '', target: '', scope: 'scenario' };
      openStrategyEditor({ kind: k, data: newItem }, (edited) => {
        if (k === 'assertion') s.assertions.push(edited);
        if (k === 'extract') s.extracts.push(edited);
        if (k === 'assign') s.assigns.push(edited);
        pushHistory();
        renderStr();
      }, true);
    });
  });
  card.draggable = true;
  bindDragSort(card, globalIdx, (from, to) => {
    const [moved] = state.steps.splice(from, 1);
    state.steps.splice(to, 0, moved);
    pushHistory();
    renderSteps();
  });
  updateUrlPreview(card, s);
}

function renderSteps() {
  ensureStepIds();
  _syncStepPagination();
  renderStepSidebar();
  renderStepTags();
  renderStepDetail();
  syncStepEmpty();
}
function toggleStep(s, card) {
  const collapsed = card.classList.toggle('collapsed');
  card.querySelector('.toggle-exp').textContent = collapsed ? '展开' : '收起';
  card.querySelector('.toggle-exp').setAttribute('aria-expanded', String(!collapsed));
  card.querySelector('.shdr').setAttribute('aria-expanded', String(!collapsed));
}
$('add-step').addEventListener('click', (e) => {
  e.stopPropagation();
  const ns = {
    capture: { method: 'GET', path: '/health' },
    api: { service: '', method: 'GET', path: '/health' },
    req: { body: {} }, assertions: [], extracts: [], assigns: [],
  };
  ns.__sid = uid('step');
  state.steps.push(ns);
  pushHistory();
  renderSteps();
});
$('expand-all').addEventListener('click', (e) => {
  e.stopPropagation();
  state.collapsedSteps.clear();
  renderSteps();
});
$('collapse-all').addEventListener('click', (e) => {
  e.stopPropagation();
  state.collapsedSteps = new Set(state.steps.map((s) => s.__sid));
  renderSteps();
});

// ── Strategy 行内编辑器 ─────────────────────────────────
const ASSERTION_OPERATORS = ['eq','ne','gt','ge','lt','le','in','nin','contains','startswith','endswith','regex','isnull','notnull'];
function openStrategyEditor(item, onSave, isNew = false) {
  const modal = document.createElement('div');
  modal.className = 'strategy-modal';
  const k = item.kind;
  const d = item.data;
  const fields = k === 'assertion' ? `
    <div class="field-row"><label>name</label><input class="fin mono" data-se="name" value="${escapeAttr(d.name || '')}" /></div>
    <div class="field-row"><label>target</label><input class="fin mono" data-se="target" value="${escapeAttr(d.target || 'response_status')}" /></div>
    <div class="field-row"><label>operator</label>
      <select class="fin" data-se="operator">
        ${ASSERTION_OPERATORS.map((op) => `<option ${d.operator === op ? 'selected' : ''}>${op}</option>`).join('')}
      </select>
    </div>
    <div class="field-row"><label>expected</label><textarea class="fin fta mono" data-se="expected" rows="2">${escapeHtml(JSON.stringify(d.expected, null, 2))}</textarea></div>
    <div class="field-row"><label>message</label><input class="fin" data-se="message" value="${escapeAttr(d.message || '')}" /></div>
  ` : k === 'extract' ? `
    <div class="field-row"><label>name</label><input class="fin mono" data-se="name" value="${escapeAttr(d.name || '')}" /></div>
    <div class="field-row"><label>expression</label><input class="fin mono" data-se="expression" value="${escapeAttr(d.expression || '$.data.id')}" placeholder="如 $.data.id" /></div>
    <div class="field-row"><label>target</label><input class="fin mono" data-se="target" value="${escapeAttr(d.target || '')}" /></div>
    <div class="field-row"><label>scope</label>
      <select class="fin" data-se="scope">
        ${['scenario','step','case','suite'].map((s) => `<option ${d.scope === s ? 'selected' : ''}>${s}</option>`).join('')}
      </select>
    </div>
  ` : `
    <div class="field-row"><label>name</label><input class="fin mono" data-se="name" value="${escapeAttr(d.name || '')}" /></div>
    <div class="field-row"><label>source</label><input class="fin mono" data-se="source" value="${escapeAttr(d.source || '')}" /></div>
    <div class="field-row"><label>target</label><input class="fin mono" data-se="target" value="${escapeAttr(d.target || '')}" /></div>
    <div class="field-row"><label>scope</label>
      <select class="fin" data-se="scope">
        ${['scenario','step','case','suite'].map((s) => `<option ${d.scope === s ? 'selected' : ''}>${s}</option>`).join('')}
      </select>
    </div>
  `;
  modal.innerHTML = `
    <div class="confirm-box" role="dialog" aria-modal="true" aria-labelledby="se-title">
      <header>
        <span id="se-title">${isNew ? '添加' : '编辑'} ${k}</span>
        <button class="se-close" type="button" aria-label="关闭">×</button>
      </header>
      <div class="se-body">${fields}</div>
      <footer>
        <button class="btn-secondary se-cancel">取消</button>
        <button class="btn-primary se-ok">保存</button>
      </footer>
    </div>`;
  document.body.appendChild(modal);
  const close = () => { modal.remove(); document.removeEventListener('keydown', onKey, true); };
  const save = () => {
    const out = { ...d };
    let bad = false;
    modal.querySelectorAll('[data-se]').forEach((el) => {
      const f = el.dataset.se;
      let v = el.value;
      if (f === 'expected') {
        try { v = JSON.parse(v); el.classList.remove('invalid'); }
        catch (_) { el.classList.add('invalid'); toast('expected 必须是合法 JSON', 'error'); bad = true; }
      }
      out[f] = v;
    });
    if (bad) return;
    onSave(out);
    close();
  };
  const onKey = (e) => {
    if (e.key === 'Escape') { e.stopPropagation(); close(); }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); save(); }
  };
  document.addEventListener('keydown', onKey, true);
  modal.addEventListener('click', (e) => { if (e.target === modal) close(); });
  modal.querySelector('.se-close').addEventListener('click', close);
  modal.querySelector('.se-cancel').addEventListener('click', close);
  modal.querySelector('.se-ok').addEventListener('click', save);
  modal.querySelector('[data-se="name"], [data-se="expression"], [data-se="source"]')?.focus();
}

// ── Step 分页原语 (v0.5.5) ────────────────────────────────
function _computePageRanges() {
  const ranges = [];
  for (let p = 0; p * PAGE_SIZE < state.steps.length; p++) {
    const start = p * PAGE_SIZE;
    const end = Math.min(start + PAGE_SIZE, state.steps.length);
    const from = start + 1;
    const to = end;
    ranges.push({ label: `${from}-${to}`, start, end });
  }
  return ranges;
}

function _syncStepPagination() {
  const pageCount = Math.max(1, Math.ceil(state.steps.length / PAGE_SIZE));
  if (state.currentPage > pageCount) state.currentPage = pageCount;
  if (state.currentPage < 1) state.currentPage = 1;
  if (state.expandedStepSid &&
      !state.steps.some(s => s.__sid === state.expandedStepSid)) {
    state.expandedStepSid = null;
  }
}

// ── Capture: 拉取 + 翻译 + Drop ──────────────────────────
function _safeParseBody(raw) {
  if (!raw) return {};
  if (typeof raw === 'object') return raw;
  try { return JSON.parse(raw); } catch (_) { return { _raw: raw }; }
}
function _eventToStepDraft(c) {
  const body = _safeParseBody(c.body);
  const query = c.query && typeof c.query === 'object' ? c.query : {};
  const headers = c.headers && typeof c.headers === 'object' ? c.headers : {};
  const scheme = c.scheme || 'https';
  const port = c.port && ((scheme === 'https' && c.port !== 443) || (scheme === 'http' && c.port !== 80)) ? `:${c.port}` : '';
  return {
    capture: c,
    api: {
      service: c.host ? `${scheme}://${c.host}${port}` : '',
      method: c.method || 'GET',
      path: c.path || '/',
    },
    req: { params: query, headers, body },
    assertions: [], extracts: [], assigns: [],
    key_hint: '',
  };
}
async function _pullCaptures() {
  const listR = await fetch('/api/captures');
  const listD = await listR.json();
  state.captures = Array.isArray(listD.events) ? listD.events : [];
  updateCapturesBadge();
}
async function _mergeCapturesIntoSteps() {
  const sigSet = new Set(
    state.steps
      .map((s) => `${s.capture?.method || s.api?.method || ''}|${s.capture?.path || s.api?.path || ''}`)
      .filter((x) => x !== '|'),
  );
  let added = 0;
  for (const c of state.captures) {
    const sig = `${c.method || ''}|${c.path || ''}`;
    if (!sig.replace('|', '') || sigSet.has(sig)) continue;
    sigSet.add(sig);
    const ns = _eventToStepDraft(c);
    ns.__sid = uid('step');
    state.steps.push(ns);
    added += 1;
  }
  if (added > 0) { state.expandedSteps.delete('__dummy'); pushHistory(); }
  renderSteps();
  renderCaptures();
  return { added, total: state.captures.length };
}
async function _importNdjsonFile(file) {
  const text = await file.text();
  if (!text || !text.trim()) {
    toast('文件为空, 无可导入', 'info');
    return { added: 0, total: 0, readLines: 0 };
  }
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const injectSid = encodeURIComponent(state.sessionId || 'default');
  let n = 0;
  for (const line of lines) {
    try {
      const ev = JSON.parse(line);
      const r = await fetch(`/api/captures/inject?sid=${injectSid}`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(ev),
      });
      if (!r.ok) {
        console.warn(`inject failed: ${r.status} ${r.statusText}`, ev);
        continue;
      }
      n += 1;
    } catch (_) { /* skip bad line */ }
  }
  state.capturesLocallyCleared = false;
  await _pullCaptures();
  const r = await _mergeCapturesIntoSteps();
  return { ...r, readLines: n };
}

// ── Step v0.5.5: 空状态触发文件选择器 ──────────────────────
const _stepEmpty = $('step-empty');
if (_stepEmpty) {
  const triggerFilePicker = () => $('ndjson-file-input').click();
  _stepEmpty.addEventListener('click', triggerFilePicker);
  _stepEmpty.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      triggerFilePicker();
    }
  });
}

const _ndjsonInput = $('ndjson-file-input');
if (_ndjsonInput) {
  _ndjsonInput.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';                          // 允许重选同一文件
    if (!file) return;
    if (!/\.ndjson$/i.test(file.name)) {
      toast('请选择 .ndjson 文件', 'error');
      return;
    }
    await _importNdjsonFile(file);
  });
}

// ── Step v0.5.5: 拖拽 .ndjson 到空状态 / step 区域 ───────────
function _handleNdjsonDrop(e) {
  e.preventDefault();
  const target = e.currentTarget;
  target?.classList.remove('prism-drop-target');
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  if (!/\.ndjson$/i.test(file.name)) {
    toast('请拖入 .ndjson 文件', 'error');
    return;
  }
  _importNdjsonFile(file);
}
const _dropTargets = [$('step-empty'), document.querySelector('.step-main')].filter(Boolean);
_dropTargets.forEach((el) => {
  ['dragenter', 'dragover'].forEach((evt) => {
    el.addEventListener(evt, (e) => {
      e.preventDefault();
      el.classList.add('prism-drop-target');
    });
  });
  ['dragleave', 'drop'].forEach((evt) => {
    el.addEventListener(evt, (e) => {
      e.preventDefault();
      el.classList.remove('prism-drop-target');
    });
  });
  el.addEventListener('drop', _handleNdjsonDrop);
});

// ── WebSocket ────────────────────────────────────────────
let ws;
let wsBackoff = 1000;
const WS_BACKOFF_MAX = 30000;
let wsReconnectCount = 0;
function connectWs() {
  const sid = encodeURIComponent(state.sessionId || 'default');
  try { ws = new WebSocket(`${proto}://${window.location.host}/ws/captures?sid=${sid}`); }
  catch (e) { scheduleReconnect(); return; }
  ws.onopen = () => {
    wsBackoff = 1000;
    wsReconnectCount = 0;
    const text = $('prism-status-text');
    text.textContent = 'prism · live';
    $('prism-status-dot').classList.remove('offline');
    $('prism-status-text').title = 'WebSocket 已连接';
  };
  ws.onclose = () => {
    const text = $('prism-status-text');
    const cap = Math.min(wsReconnectCount + 1, 99);
    text.textContent = `prism · offline (重试 ${cap}+)`;
    $('prism-status-dot').classList.add('offline');
    $('prism-status-text').title = 'WebSocket 断开,正在按指数退避重连';
    scheduleReconnect();
  };
  ws.onerror = () => { try { ws.close(); } catch (_) {} };
  ws.onmessage = (msg) => {
    let p;
    try { p = JSON.parse(msg.data); } catch (_) { return; }
    if (p.type === 'hello') {
      // 只在没有被本地清空的情况下灌入
      if (!state.capturesLocallyCleared) {
        state.captures = Array.isArray(p.events) ? p.events : [];
        updateCapturesBadge();
        renderCaptures();
        // v0.5.4: 如果开启了"自动注入", 把 hello 里的历史 captures 也合到 steps
        if (state.autoInjectToSteps) {
          _mergeCapturesIntoSteps();
        }
      }
      return;
    }
    if (p.type === 'capture' && p.data) {
      const c = p.data;
      const sig = `${c.ts}|${c.method}|${c.path}`;
      if (!state.captures.some((x) => `${x.ts}|${x.method}|${x.path}` === sig)) {
        state.captures.push(c);
        updateCapturesBadge();
        renderCaptures();
        // v0.5.4: 自动注入到 step (可选, 勾选开启)
        if (state.autoInjectToSteps) {
          const before = state.steps.length;
          _mergeCapturesIntoSteps();
          const added = state.steps.length - before;
          if (added > 0) {
            renderSteps();
            scheduleSave();
            toast(`已自动注入 step: ${c.method} ${c.path}`, 'success', 1500);
          }
        } else {
          toast(`${c.method} ${c.path}`, 'info', 1800);
        }
      }
    }
  };
}
function scheduleReconnect() {
  setTimeout(connectWs, wsBackoff);
  wsBackoff = Math.min(wsBackoff * 2, WS_BACKOFF_MAX);
}
function updateCapturesBadge() {
  const el = $('captures-count');
  if (el) {
    el.textContent = String(state.captures.length);
    el.dataset.empty = state.captures.length === 0 ? 'true' : 'false';
  }
  // v0.5.3: 同步更新 captures 列表内的 inline 计数
  const el2 = $('captures-count-inline');
  if (el2) el2.textContent = String(state.captures.length);
}

// ── v0.5.3: 实时 captures 列表 (Step tab 上方) ──────────────────────
const _CAP_LIST_MAX = 200;  // 列表最多保留 200 条, 防止长会话内存爆炸

function _fmtMs(ms) {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function _statusClass(s) {
  if (s == null) return '';
  const c = Math.floor(s / 100);
  return `s${c}xx`;
}

function _methodPill(m) {
  const safe = (m || 'GET').toUpperCase();
  return `<span class="method-pill ${safe}">${safe}</span>`;
}

function renderCaptures() {
  const tbody = $('captures-tbody');
  const empty = $('captures-empty');
  if (!tbody) return;

  // 截断 (最新的 200 条)
  const list = state.captures.slice(-_CAP_LIST_MAX);

  if (list.length === 0) {
    tbody.innerHTML = '';
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;

  // 倒序显示 (最新在上)
  const rows = list.slice().reverse().map((c) => {
    const sig = `${c.ts || ''}|${c.method || ''}|${c.path || ''}`;
    return `<tr data-sig="${escapeAttr(sig)}">
      <td class="cell-method">${_methodPill(c.method)}</td>
      <td class="cell-path" title="${escapeAttr(c.host || '')}${escapeAttr(c.path || '')}">${escapeHtml(c.path || '/')}</td>
      <td class="cell-status ${_statusClass(c.response?.status)}">${c.response?.status ?? '-'}</td>
      <td class="cell-ms">${_fmtMs(c.response_ms)}</td>
    </tr>`;
  }).join('');
  tbody.innerHTML = rows;
}
$('clear-captures').addEventListener('click', async () => {
  if (!state.captures.length) return;
  const ok = await confirmModal('清空 captures', '清空内存中的所有捕获事件(steps 不会被删除),确认?', { ok: '清空' });
  if (!ok) return;
  await fetch('/api/captures', { method: 'DELETE' });
  state.captures = [];
  state.capturesLocallyCleared = true;
  updateCapturesBadge();
  renderCaptures();
  toast('captures 已清空', 'info');
});

// ── Draft 持久化 ─────────────────────────────────────────
function serializeDraft() {
  return {
    scenario_id: $('m-sid').value || 'sc_new',
    name: $('m-name').value,
    description: $('m-desc').value,
    module: $('m-module').value,
    priority: +$('m-priority').value,
    author: $('m-author').value,
    owner: $('m-owner').value,
    tags: state.tags,
    version: $('m-version').value,
    expire: $('m-expire').checked,
    requirement_ref: ($('m-req').value || '').split(',').map((s) => s.trim()).filter(Boolean),
    services: state.services,
    users: state.users,
    time_policy_kind: $('tp-kind').value,
    time_policy_seconds: +$('tp-seconds').value,
    retry_enabled: $('tp-retry').checked,
    retry_max_attempts: +$('tp-retry-max').value,
    retry_backoff_seconds: +$('tp-retry-backoff').value,
    retry_on: ($('tp-retry-on').value || '').split(',').map((s) => s.trim()).filter(Boolean).map(String),
    setup_refs: ($('tp-setup').value || '').split(',').map((s) => s.trim()).filter(Boolean),
    teardown_refs: ($('tp-teardown').value || '').split(',').map((s) => s.trim()).filter(Boolean),
    resources: Object.entries(state.resources).map(([n, r]) => {
      const { __rid, ...rest } = r;
      return { name: n, ...rest };
    }),
    // v0.5.1: 发完整 step 自定义, 替换 v0 的 step_ids (基于 captures 索引, 错位)
    // UI 本地字段 (以 __ 开头的, 如 __sid) 全部剥离
    // req_override 只覆盖 params/body (headers 在 api 上, 走 api_override 或 capture 兜底)
    steps: state.steps.map((s) => {
      const out = {
        capture: s.capture,
        enabled: s.enabled !== false,
        add_status_assertion: s.add_status_assertion !== false,
        extracts: s.extracts || [],
        assigns: s.assigns || [],
        assertions: s.assertions || [],
        key_hint: s.key_hint || '',
        note: s.note || '',
      };
      if (s.api_override) out.api_override = s.api_override;
      if (s.req_override) {
        // 过滤 undefined 字段, 不污染 wire
        out.req_override = {
          params: s.req_override.params || {},
          body: s.req_override.body || {},
        };
      }
      return out;
    }),
  };
}
const _save = async () => {
  if (state.hydrating) return;
  validateAll();
  try {
    const r = await fetch(sessPath(), {
      method: 'PUT', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(serializeDraft()),
    });
    if (!r.ok) {
      let detail = `HTTP ${r.status}`;
      try { detail = (await r.text()) || detail; } catch (_) {}
      throw new Error(detail.slice(0, 200));
    }
    state.dirty = false;
  } catch (e) {
    toast(`草稿保存失败: ${e.message}`, 'error', 4000);
    console.warn('[prism] saveDraft failed', e);
  }
};
const debouncedSave = debounce(_save, 800);
function scheduleSave() { state.dirty = true; debouncedSave(); }
async function saveDraft() {
  if (debouncedSave.cancel) debouncedSave.cancel();
  await _save();
}

async function loadDraft() {
  try {
    const r = await fetch(sessPath());
    if (!r.ok) return;
    const d = await r.json();
    const draft = d.draft;
    if (!draft) return;
    state.hydrating = true;
    // 回填 inputs (使用 setFieldValue)
    setFieldValue('m-sid', draft.scenario_id);
    setFieldValue('m-name', draft.name);
    setFieldValue('m-desc', draft.description);
    setFieldValue('m-module', draft.module);
    setFieldValue('m-priority', draft.priority);
    setFieldValue('m-author', draft.author);
    setFieldValue('m-owner', draft.owner);
    setFieldValue('m-version', draft.version);
    setFieldValue('m-req', (draft.requirement_ref || []).join(', '));
    setFieldValue('tp-kind', draft.time_policy_kind);
    setFieldValue('tp-seconds', draft.time_policy_seconds);
    setFieldValue('tp-retry', draft.retry_enabled);
    setFieldValue('tp-retry-max', draft.retry_max_attempts);
    setFieldValue('tp-retry-backoff', draft.retry_backoff_seconds);
    setFieldValue('tp-retry-on', (draft.retry_on || []).join(', '));
    setFieldValue('tp-setup', (draft.setup_refs || []).join(', '));
    setFieldValue('tp-teardown', (draft.teardown_refs || []).join(', '));
    setFieldValue('m-expire', draft.expire);
    $('m-expire-text').textContent = draft.expire ? 'true' : 'false';
    $('tp-retry-text').textContent = draft.retry_enabled ? 'enabled' : 'null';
    $('retry-fields').hidden = !draft.retry_enabled;
    // 回填 state
    state.services = draft.services || {};
    state.users = draft.users || [];
    state.tags = (draft.tags || []).map((t) => { if (typeof t === 'string') t.__tagId = uid('tag'); return t; });
    state.resources = {};
    for (const r of (draft.resources || [])) {
      const name = r.name;
      const { __rid, ...rest } = r;
      rest.__rid = uid('res');
      state.resources[name] = rest;
    }
    state.steps = (draft.step_ids || []).map((sid) => {
      const ev = state.captures[+sid];
      const ns = ev ? _eventToStepDraft(ev) : {
        capture: { method: 'GET', path: '/' },
        api: { service: '', method: 'GET', path: '/' },
        req: { body: {} }, assertions: [], extracts: [], assigns: [],
      };
      ns.__sid = uid('step');
      return ns;
    });
    validateAll();
    state.hydrating = false;
    state.undoStack = [snapshot()];
    syncHeader();
    renderAll();
  } catch (e) {
    state.hydrating = false;
    console.warn('[prism] loadDraft failed', e);
  }
}
function renderAll() {
  renderTags();
  renderServices();
  renderUsers();
  renderResources();
  renderSteps();
  updateCapturesBadge();
  renderCaptures();
}

// ── YAML Modal ───────────────────────────────────────────
function renderYamlWithLineNumbers(text) {
  const lines = text.split('\n');
  const w = String(lines.length).length;
  return lines.map((ln, i) => {
    return `<span class="ln-no">${String(i + 1).padStart(w, ' ')}</span>${escapeHtml(ln) || '&nbsp;'}`;
  }).join('\n');
}
$('yaml-toggle').addEventListener('click', async () => {
  $('yaml-modal').hidden = false;
  $('yaml-pre').textContent = '加载中…';
  state.showJsonView = false;
  try {
    const r = await fetch(`${sessPath()}/yaml`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(serializeDraft()),
    });
    if (!r.ok) {
      const errText = await r.text().catch(() => '');
      $('yaml-pre').innerHTML = renderYamlWithLineNumbers(`服务器错误: HTTP ${r.status}\n${errText}`);
      return;
    }
    const d = await r.json();
    const yaml = d.yaml || JSON.stringify(d, null, 2);
    $('yaml-pre').innerHTML = renderYamlWithLineNumbers(yaml);
    $('yaml-pre').dataset.raw = yaml;
  } catch (e) {
    $('yaml-pre').textContent = '请求失败: ' + (e?.message || e);
  }
});
function closeYamlModal() { $('yaml-modal').hidden = true; }
$('yaml-close').addEventListener('click', closeYamlModal);
$('yaml-modal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeYamlModal();
});
$('yaml-copy').addEventListener('click', async () => {
  const text = $('yaml-pre').dataset.raw || $('yaml-pre').textContent;
  try { await navigator.clipboard.writeText(text); toast('已复制到剪贴板', 'success', 1500); }
  catch (_) { toast('复制失败(浏览器拦截)', 'error'); }
});
$('yaml-export').addEventListener('click', async () => {
  const btn = $('yaml-export');
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = '导出中…';
  try {
    const r = await fetch(`${sessPath()}/export`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ ...serializeDraft(), fmt: 'yaml' }),
    });
    const d = await r.json();
    if (d.path) toast(`已导出到: ${d.path}`, 'success', 6000);
    else toast('导出失败: ' + JSON.stringify(d), 'error', 5000);
  } catch (e) {
    toast('导出异常: ' + (e?.message || e), 'error', 5000);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
});
$('yaml-json').addEventListener('click', () => {
  state.showJsonView = !state.showJsonView;
  if (state.showJsonView) {
    const draft = serializeDraft();
    const json = JSON.stringify(draft, null, 2);
    $('yaml-pre').innerHTML = renderYamlWithLineNumbers(json);
    $('yaml-pre').dataset.raw = json;
    $('yaml-json').textContent = '回到 YAML';
    toast('已切换到 JSON 视图(本地 draft)', 'info', 1200);
  } else {
    // 重新拉 YAML
    $('yaml-toggle').click();
    $('yaml-json').textContent = '本地 JSON 视图';
  }
});

// ── Help Modal ──────────────────────────────────────────
$('help-toggle').addEventListener('click', () => { $('help-modal').hidden = false; });
$('help-close').addEventListener('click', () => { $('help-modal').hidden = true; });
$('help-modal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) $('help-modal').hidden = true;
});

// ── 顶栏全局操作 ─────────────────────────────────────────
$('undo-btn').addEventListener('click', (e) => { e.stopPropagation(); undo(); });
$('redo-btn').addEventListener('click', (e) => { e.stopPropagation(); redo(); });

// ── 快捷键 ──────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (!$('yaml-modal').hidden) closeYamlModal();
    if (!$('help-modal').hidden) $('help-modal').hidden = true;
  }
  // Ctrl/Cmd 组合:在任何输入框内都允许 (Ctrl+S / Z / Y),但 Ctrl+1..4 不触发
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    saveDraft().then(() => toast('已保存草稿', 'info', 1200));
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
    e.preventDefault();
    undo();
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
    e.preventDefault();
    redo();
  }
  // Ctrl+1..4 仅在非输入控件触发
  if ((e.ctrlKey || e.metaKey) && ['1','2','3','4'].includes(e.key)) {
    if (e.target.matches('input,textarea,select')) return;
    e.preventDefault();
    switchTo(+e.key - 1);
  }
  if (e.key === '?' && !e.target.matches('input,textarea,select')) {
    $('help-modal').hidden = false;
  }
});

// beforeunload 提示
window.addEventListener('beforeunload', (e) => {
  if (state.dirty) {
    e.preventDefault();
    e.returnValue = '有未保存的修改,确定离开?';
  }
});

// ── 启动 ────────────────────────────────────────────────
// v0.5.5: 全局错误捕获,init 任何 throw 都会在页面顶部显示红条
window.addEventListener('error', (e) => {
  if (!e || !e.error) return;
  const banner = document.createElement('div');
  banner.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#dc2626;color:#fff;padding:8px 12px;font:12px/1.4 monospace;z-index:99999;white-space:pre-wrap;';
  banner.textContent = `[v0.5.5 JS ERROR] ${e.error.message || e.message} @ ${e.filename || '?'}:${e.lineno || '?'}`;
  document.body && document.body.appendChild(banner);
});
window.addEventListener('unhandledrejection', (e) => {
  if (!e || !e.reason) return;
  const banner = document.createElement('div');
  banner.style.cssText = 'position:fixed;top:32px;left:0;right:0;background:#dc2626;color:#fff;padding:8px 12px;font:12px/1.4 monospace;z-index:99999;white-space:pre-wrap;';
  banner.textContent = `[v0.5.5 PROMISE REJECT] ${e.reason && e.reason.message ? e.reason.message : e.reason}`;
  document.body && document.body.appendChild(banner);
});

(async function init() {
  detectSession();
  bindMeta();
  bindTagInput();
  // v0.5.4+: header sid 输入框事件
  const sidInp = $('header-sid-input');
  const sidBtn = $('header-sid-switch');
  if (sidInp) {
    sidInp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        switchSession(sidInp.value);
      }
    });
    sidInp.addEventListener('focus', () => sidInp.select());
  }
  if (sidBtn) {
    sidBtn.addEventListener('click', () => switchSession(sidInp ? sidInp.value : ''));
  }
  // v0.5.4: 自动注入 toggle
  const autoInj = $('auto-inject-toggle');
  if (autoInj) {
    const textEl = autoInj.parentElement.querySelector('.tog-text');
    autoInj.addEventListener('change', () => {
      state.autoInjectToSteps = autoInj.checked;
      if (textEl) textEl.dataset.on = String(autoInj.checked);
      if (state.autoInjectToSteps) {
        // 立即灌入当前所有 captures (用 _mergeCapturesIntoSteps 已有 dedup)
        const before = state.steps.length;
        _mergeCapturesIntoSteps();
        const added = state.steps.length - before;
        if (added > 0) {
          renderSteps();
          scheduleSave();
          toast(`已注入 ${added} 条历史 capture 为 step`, 'success', 2000);
        } else {
          toast('自动注入已开启 (新 capture 实时进 step)', 'info', 2000);
        }
      } else {
        toast('自动注入已关闭', 'info', 1500);
      }
    });
  }
  // tab 事件 — tab 按钮用 HTML 内联 onclick (见 index.html),这里只绑 page click 委托
  $$('.page').forEach((p) => {
    p.addEventListener('click', (e) => {
      if (e.target.closest('input,select,textarea,button,.tag-pill,.tags-wrap,.user-block,.resource-tile,.step-card,.strategy-item'))
        e.stopPropagation();
    });
  });
  await loadDraft();
  // 初始 history snapshot
  if (!state.undoStack.length) state.undoStack = [snapshot()];
  connectWs();
  setInterval(() => { if (state.dirty) _save(); }, 5000);
})();
