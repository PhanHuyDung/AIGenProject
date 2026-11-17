/* AIGenProject – giao diện web (JS thuần, không build). */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const el = (tag, attrs = {}, ...children) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'html') n.innerHTML = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else if (v === true) n.setAttribute(k, '');
      else n.setAttribute(k, v);
    }
    for (const c of children.flat()) if (c != null) n.append(c.nodeType ? c : document.createTextNode(String(c)));
    return n;
  };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtMs = (ms) => ms == null ? '–' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
  const fmtCost = (c) => c == null ? '–' : `$${Number(c).toFixed(4)}`;
  const fmtTime = (iso) => iso ? iso.replace('T', ' ').slice(0, 19) : '';
  const confClass = (c) => c === 'cao' ? 'cao' : c === 'trung bình' ? 'tb' : c === 'thấp' ? 'thap' : 'none';

  // ---------------------------------------------------------------- toast / modal
  let toastTimer;
  function toast(msg, kind = 'error', ms = 6000) {
    const t = $('#toast');
    t.textContent = typeof msg === 'string' ? msg : detailText(msg);
    t.className = 'toast' + (kind === 'info' ? ' info' : '');
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), ms);
  }
  function detailText(err) {
    const d = err?.detail ?? err?.message ?? err;
    if (typeof d === 'string') return d;
    if (d && typeof d === 'object') {
      let s = d.message || JSON.stringify(d);
      if (d.current) s += `\nPhiên hiện tại: ${d.current.kind} – ${d.current.prompt || d.current.skill || d.current.proposal || ''}`;
      if (d.domains) s += `\nLĩnh vực hợp lệ: ${d.domains.join(', ')}`;
      return s;
    }
    return String(d);
  }
  function modal(title, placeholder = '') {
    return new Promise((resolve) => {
      const m = $('#modal'); $('#modalTitle').textContent = title;
      const inp = $('#modalInput'); inp.value = ''; inp.placeholder = placeholder;
      m.hidden = false; inp.focus();
      const done = (v) => { m.hidden = true; ok.onclick = cancel.onclick = null; resolve(v); };
      const ok = $('#modalOk'), cancel = $('#modalCancel');
      ok.onclick = () => done(inp.value); cancel.onclick = () => done(null);
    });
  }

  // ---------------------------------------------------------------- API
  async function api(path, { method = 'GET', body } = {}) {
    const res = await fetch(path, {
      method, headers: body !== undefined ? { 'content-type': 'application/json' } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let data = null;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('json')) data = await res.json(); else data = await res.text();
    if (!res.ok) { const e = new Error(detailText(data)); e.status = res.status; e.data = data; throw e; }
    return data;
  }

  /** POST + đọc SSE qua ReadableStream (EventSource không gửi được POST). */
  function sse(path, body, onEvent) {
    const ctrl = new AbortController();
    const done = (async () => {
      const res = await fetch(path, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body), signal: ctrl.signal,
      });
      if (!res.ok) {
        let data; try { data = await res.json(); } catch { data = await res.text(); }
        const e = new Error(detailText(data)); e.status = res.status; e.data = data; throw e;
      }
      const reader = res.body.getReader(); const dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const frame = buf.slice(0, i); buf = buf.slice(i + 2);
          if (!frame.trim() || frame.startsWith(':')) continue;
          let type = 'message', data = '';
          for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) type = line.slice(6).trim();
            else if (line.startsWith('data:')) data += line.slice(5).trim();
          }
          try { onEvent(JSON.parse(data)); } catch (e) { console.warn('SSE parse', e, data); }
        }
      }
    })();
    return { abort: () => ctrl.abort(), done };
  }

  // ---------------------------------------------------------------- markdown
  function splitFrontmatter(text) {
    const m = /^---\s*\n([\s\S]*?)\n---\s*\n?/.exec(text || '');
    if (!m) return { fm: null, body: text || '' };
    const fm = {};
    for (const line of m[1].split('\n')) {
      const mm = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line);
      if (mm) fm[mm[1]] = mm[2];
    }
    return { fm, body: text.slice(m[0].length), raw: m[1] };
  }
  function renderMarkdown(md) {
    if (!window.marked || !window.DOMPurify) return el('pre', {}, md);
    const html = DOMPurify.sanitize(marked.parse(md, { gfm: true, breaks: false }));
    const box = el('div', { html });
    $$('a[href]', box).forEach((a) => { if (/^https?:/.test(a.getAttribute('href'))) { a.target = '_blank'; a.rel = 'noopener'; } });
    return box;
  }
  function metaBar(fm, meta = {}) {
    if (!fm && !meta.last_updated) return el('div');
    const f = fm || {};
    const items = [];
    if (f.domain) items.push(el('span', {}, 'Lĩnh vực: ', el('b', {}, f.domain)));
    if (f.last_updated) items.push(el('span', {}, 'Cập nhật: ', el('b', {}, f.last_updated), meta.stale ? el('span', { class: 'tag stale', style: 'margin-left:6px' }, 'cũ') : null));
    if (f.confidence) items.push(el('span', {}, 'Độ chắc chắn: ', el('span', { class: 'dot ' + confClass(f.confidence), style: 'margin-right:4px' }), el('b', {}, f.confidence)));
    if (f.status) items.push(el('span', {}, 'Trạng thái: ', el('b', {}, f.status)));
    if (f.name) items.push(el('span', {}, 'Tên: ', el('b', {}, f.name)));
    if (f.tools) items.push(el('span', {}, 'Tools: ', el('b', {}, f.tools)));
    return el('div', { class: 'meta' }, items);
  }

  // ---------------------------------------------------------------- trạng thái / header
  const state = { status: null, running: false, agents: [], skills: [] };

  async function refreshStatus(refresh = false) {
    try {
      const s = await api('/api/status' + (refresh ? '?refresh=1' : ''));
      state.status = s;
      const b = $('#authBadge');
      if (s.auth.uses_subscription) {
        b.className = 'badge ok';
        b.textContent = `● Đang dùng tài khoản Claude (${s.auth.method}, gói ${s.auth.subscription || '?'})`;
        b.title = 'Không dùng API key. ' + (s.removed_env?.length ? 'Đã gỡ biến: ' + s.removed_env.join(', ') : '');
      } else {
        b.className = 'badge bad';
        b.textContent = s.auth.logged_in ? `● CẢNH BÁO: đăng nhập bằng ${s.auth.method}, không phải tài khoản Claude` : '● Chưa đăng nhập Claude – chạy `claude login`';
        b.title = (s.problems || []).map((p) => `[${p.level}] ${p.message}${p.fix ? '\n  ' + p.fix : ''}`).join('\n');
      }
      if (s.removed_env?.length && s.auth.uses_subscription) {
        b.className = 'badge bad'; b.textContent = '● Phát hiện API key trong môi trường (đã gỡ): ' + s.removed_env.join(', ');
      }
      const pc = $('#pendingCount'); pc.textContent = s.pending_proposals; pc.hidden = !s.pending_proposals;
      notifyPending(s.pending_proposals || 0);
      setBusy(s.busy, s.current);
      if (!$('#maxTurns').value) $('#maxTurns').placeholder = s.settings.max_turns;
    } catch (e) {
      const b = $('#authBadge'); b.className = 'badge bad'; b.textContent = '● Không gọi được /api/status'; b.title = e.message;
    }
  }
  function setBusy(busy, current) {
    state.running = busy;
    const bb = $('#busyBadge'); bb.hidden = !busy;
    bb.textContent = busy ? `● Đang chạy: ${current?.kind || ''} ${current?.prompt || current?.skill || current?.proposal || ''}`.slice(0, 80) : '';
    $$('button[data-run]').forEach((btn) => (btn.disabled = busy));
    $('#runBtn').disabled = busy; $('#updateBtn').disabled = busy; $('#newDomainBtn').disabled = busy;
  }

  // ---------------------------------------------------------------- khung log sự kiện
  function makeLog(container) {
    container.innerHTML = '';
    let stickBottom = true;
    container.addEventListener('scroll', () => {
      stickBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 40;
    });
    const push = (node) => { container.append(node); if (stickBottom) container.scrollTop = container.scrollHeight; };
    const toolLine = (d) => {
      const i = d.input || {}; const n = d.name;
      const map = {
        WebSearch: ['🔎 Tìm', i.query], WebFetch: ['🌐 Đọc trang', i.url], Read: ['📄 Đọc', i.file_path],
        Glob: ['📁 Liệt kê', i.pattern], Grep: ['🔍 Grep', i.pattern], Write: ['✍️ Ghi', i.file_path],
        Edit: ['✏️ Sửa', i.file_path], MultiEdit: ['✏️ Sửa', i.file_path], Skill: ['🧩 Skill', `${i.skill || i.command || ''} ${i.args || ''}`],
        Task: ['🤖 Subagent', `${i.subagent_type || ''}: ${i.description || ''}`], Agent: ['🤖 Subagent', `${i.subagent_type || ''}: ${i.description || ''}`],
      };
      const [label, val] = map[n] || [n, JSON.stringify(i).slice(0, 200)];
      return el('div', { class: 'ev tool' + (d.parent_tool_use_id ? ' sub' : '') }, el('span', { class: 'tn' }, label), val || '');
    };
    return {
      event(ev) {
        const d = ev.data || {};
        switch (ev.type) {
          case 'text':
            if (d.kind === 'init') {
              push(el('div', { class: 'ev init' }, `Phiên ${d.sdk_session_id || ''} · model ${d.model || '?'} · xác thực: ${d.uses_subscription ? 'tài khoản Claude (không dùng API key)' : 'API KEY – kiểm tra lại!'}`));
            } else if (d.text?.trim()) {
              push(el('div', { class: 'ev text' + (d.parent_tool_use_id ? ' sub' : '') }, renderMarkdown(d.text)));
            }
            break;
          case 'tool_use': push(toolLine(d)); break;
          case 'tool_result':
            if (d.is_error) push(el('div', { class: 'ev err' + (d.parent_tool_use_id ? ' sub' : '') }, '✖ ', d.content || 'lỗi tool'));
            break;
          case 'done': push(doneCard(d)); break;
          case 'error':
            push(el('div', { class: 'ev err' }, '✖ ', d.message || 'Lỗi', d.details ? el('pre', {}, d.details) : null,
              d.domains ? el('div', {}, 'Lĩnh vực hợp lệ: ' + d.domains.join(', ')) : null,
              d.skills ? el('div', {}, 'Skill hợp lệ: ' + d.skills.join(', ')) : null));
            break;
          default: push(el('div', { class: 'ev' }, JSON.stringify(ev).slice(0, 300)));
        }
      },
      note(text, cls = 'note') { push(el('div', { class: 'ev ' + cls }, text)); },
    };
  }
  function fileChips(files, bad = false, emptyBlank = false) {
    if (!files?.length) return emptyBlank ? [] : 'không có';
    return files.map((f) => el('span', { class: 'chip' + (bad ? ' bad' : ''), title: f.reason || f.action },
      bad ? f.path : el('a', { href: '#kho?path=' + encodeURIComponent(f.path) }, f.path)));
  }
  function doneCard(d) {
    const dl = el('dl', {},
      el('dt', {}, 'Trạng thái'), el('dd', {}, `${d.subtype}${d.is_error ? ' (lỗi)' : ''}`),
      el('dt', {}, 'Số lượt'), el('dd', {}, d.num_turns),
      el('dt', {}, 'Thời gian'), el('dd', {}, fmtMs(d.duration_ms)),
      el('dt', {}, 'Chi phí ước tính'), el('dd', {}, `${fmtCost(d.cost_usd)} `, el('span', { class: 'muted' }, '– ước tính của SDK, không tính tiền vì dùng gói đăng ký')),
      el('dt', {}, 'Xác thực'), el('dd', { class: d.uses_subscription ? '' : 'bad' }, d.uses_subscription ? 'tài khoản Claude, không dùng API key' : 'API KEY – kiểm tra lại môi trường!'),
      el('dt', {}, 'File đã ghi'), el('dd', {}, fileChips(d.files)),
    );
    if (d.denied_files?.length) dl.append(el('dt', {}, 'File bị chặn'), el('dd', {}, fileChips(d.denied_files, true)));
    dl.append(el('dt', {}, 'Đề xuất chờ duyệt'), el('dd', {}, d.pending_proposals ? el('a', { href: '#cho-duyet' }, `${d.pending_proposals} – xem tab Chờ duyệt`) : '0'));
    if (d.errors?.length) dl.append(el('dt', {}, 'Lỗi'), el('dd', { class: 'bad' }, d.errors.join('; ')));
    return el('div', { class: 'ev done' + (d.is_error ? ' bad' : '') }, dl);
  }

  /** Chạy một stream vào khung log, quản lý trạng thái bận và nút Dừng. */
  let current = null;
  async function runStream(path, body, logContainer, { onDone } = {}) {
    if (state.running) { toast('Đang có phiên khác chạy, hãy chờ xong rồi thử lại.'); return; }
    const log = makeLog(logContainer);
    log.note('Đang gửi yêu cầu…');
    setBusy(true, { kind: body.kind || 'research', prompt: body.prompt || body.args || '' });
    $('#stopBtn').hidden = false;
    let last = null;
    current = sse(path, body, (ev) => {
      last = ev; log.event(ev);
      if (ev.type === 'done' || ev.type === 'error') { setBusy(false); $('#stopBtn').hidden = true; }
    });
    try {
      await current.done;
    } catch (e) {
      if (e.name === 'AbortError') log.note('Đã dừng theo yêu cầu. Phiên SDK bị huỷ; phần đã ghi vẫn còn trong kho.', 'err');
      else { log.note('✖ ' + e.message, 'err'); if (e.status === 409) toast(e); }
    } finally {
      current = null; $('#stopBtn').hidden = true; setBusy(false);
      refreshStatus();
      onDone?.(last);
    }
  }
  $('#stopBtn').addEventListener('click', () => current?.abort());

  // ---------------------------------------------------------------- router
  const TABS = ['nghien-cuu', 'kho', 'agent-skill', 'cho-duyet', 'lich-su', 'lich-tu-dong'];
  const loaders = {};
  function route() {
    const hash = location.hash.slice(1) || localStorage.getItem('tab') || 'nghien-cuu';
    const [tab, qs] = hash.split('?');
    const name = TABS.includes(tab) ? tab : 'nghien-cuu';
    $$('.tab').forEach((s) => s.classList.toggle('active', s.id === 'tab-' + name));
    $$('#tabs a').forEach((a) => a.classList.toggle('active', a.dataset.tab === name));
    try { localStorage.setItem('tab', name); } catch {}
    loaders[name]?.(new URLSearchParams(qs || ''));
  }
  window.addEventListener('hashchange', route);

  // ---------------------------------------------------------------- Tab 1: Nghiên cứu
  async function loadAgents() {
    state.agents = await api('/api/agents');
    const sel = $('#domain'); const cur = sel.value;
    sel.innerHTML = '<option value="">Tự chọn theo CLAUDE.md</option>';
    for (const a of state.agents) if (a.domain) sel.append(el('option', { value: a.domain }, `${a.domain} (${a.name})`));
    sel.value = cur;
  }
  $('#researchForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const prompt = $('#prompt').value.trim(); if (!prompt) return;
    const body = { prompt, domain: $('#domain').value || null };
    const mt = parseInt($('#maxTurns').value, 10); if (mt > 0) body.max_turns = mt;
    runStream('/api/research', body, $('#researchLog'), { onDone: () => loaders['lich-su']?.(null, true) });
  });
  loaders['nghien-cuu'] = () => { if (!state.agents.length) loadAgents().catch(toast); };

  // ---------------------------------------------------------------- Tab 2: Kho kiến thức
  const kho = { tree: null, selected: null, searchTimer: null };
  function treeNode(node) {
    if (node.type === 'dir') {
      const kids = (node.children || []).slice().sort((a, b) => (a.system ? 1 : 0) - (b.system ? 1 : 0));
      const li = el('li', { class: 'dir' + (node.system ? ' system' : '') });
      const row = el('div', { class: 'row', onclick: () => { ul.hidden = !ul.hidden; row.firstChild.textContent = ul.hidden ? '▸' : '▾'; } },
        el('span', {}, '▾'), el('span', { class: 'title' }, node.name), el('span', { class: 'date' }, `${kids.filter((k) => k.type === 'file').length}`));
      const ul = el('ul', {}, kids.map(treeNode));
      if (node.system) { ul.hidden = true; row.firstChild.textContent = '▸'; }
      li.append(row, ul);
      if (node.path !== 'knowledge' && !node.system && !node.path.startsWith('knowledge/_')) {
        row.append(el('button', { class: 'small', title: 'Cập nhật cả lĩnh vực (skill update-knowledge)', 'data-run': 1,
          onclick: (ev) => { ev.stopPropagation(); runSkill('update-knowledge', node.path); } }, '↻'));
      }
      return li;
    }
    const m = node.meta || {};
    return el('li', {}, el('div', { class: 'row file', 'data-path': node.path, onclick: () => openFile(node.path) },
      el('span', { class: 'dot ' + confClass(m.confidence), title: 'Độ chắc chắn: ' + (m.confidence || '?') }),
      el('span', { class: 'title', title: node.name }, m.title || node.name),
      m.stale ? el('span', { class: 'tag stale' }, 'cũ') : null,
      el('span', { class: 'date' }, m.last_updated || '')));
  }
  async function loadTree() {
    kho.tree = await api('/api/knowledge');
    const box = $('#tree'); box.innerHTML = '';
    box.append(el('ul', {}, (kho.tree.children || []).slice().sort((a, b) => (a.system ? 1 : 0) - (b.system ? 1 : 0) || (a.type === 'file' ? 1 : 0) - (b.type === 'file' ? 1 : 0)).map(treeNode)));
    highlightSelected();
  }
  function highlightSelected() {
    $$('#tree .row.file').forEach((r) => r.classList.toggle('selected', r.dataset.path === kho.selected));
  }
  async function openFile(path) {
    kho.selected = path; highlightSelected();
    history.replaceState(null, '', '#kho?path=' + encodeURIComponent(path));
    $('#fileEdit').hidden = true; $('#fileView').hidden = false;
    $('#fileView').innerHTML = '<p class="muted">Đang tải…</p>';
    try {
      const f = await api('/api/knowledge/' + path.split('/').map(encodeURIComponent).join('/'));
      const { fm, body } = splitFrontmatter(f.content);
      $('#fileToolbar').hidden = false; $('#filePath').textContent = f.path;
      $('#fileMeta').replaceChildren(metaBar(fm, f.meta));
      $('#fileView').replaceChildren(renderMarkdown(body));
      $('#fileEditor').value = f.content;
    } catch (e) { $('#fileView').innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
  }
  async function doSearch(q) {
    if (!q.trim()) { loadTree(); return; }
    const r = await api('/api/knowledge/search?q=' + encodeURIComponent(q));
    const box = $('#tree'); box.innerHTML = '';
    if (!r.results.length) { box.append(el('p', { class: 'muted' }, 'Không có kết quả.')); return; }
    box.append(el('ul', {}, r.results.map((x) => el('li', { class: 'result' },
      el('div', { class: 'row file', 'data-path': x.path, onclick: () => openFile(x.path) },
        el('span', { class: 'dot ' + confClass(x.meta.confidence) }), el('span', { class: 'title' }, x.meta.title || x.path),
        x.meta.stale ? el('span', { class: 'tag stale' }, 'cũ') : null, el('span', { class: 'date' }, x.meta.last_updated || '')),
      x.snippet ? el('div', { class: 'snippet' }, '…' + x.snippet + '…') : null))));
    highlightSelected();
  }
  $('#searchBox').addEventListener('input', (e) => { clearTimeout(kho.searchTimer); kho.searchTimer = setTimeout(() => doSearch(e.target.value).catch(toast), 300); });
  $('#editBtn').addEventListener('click', () => { $('#fileView').hidden = true; $('#fileEdit').hidden = false; $('#editMsg').textContent = ''; });
  $('#cancelEditBtn').addEventListener('click', () => { $('#fileEdit').hidden = true; $('#fileView').hidden = false; });
  $('#saveFileBtn').addEventListener('click', async () => {
    try {
      await api('/api/files/' + kho.selected, { method: 'PUT', body: { content: $('#fileEditor').value } });
      $('#editMsg').textContent = 'Đã lưu.'; await openFile(kho.selected); await loadTree(); toast('Đã lưu ' + kho.selected, 'info', 2500);
    } catch (e) { $('#editMsg').textContent = e.message; }
  });
  function runSkill(name, args, extra = {}) {
    location.hash = '#nghien-cuu';
    $('#prompt').value = `/${name} ${args}`;
    runStream(`/api/skills/${encodeURIComponent(name)}/run`, { args, kind: 'skill' }, $('#researchLog'), extra);
  }
  $('#updateBtn').addEventListener('click', () => { if (kho.selected) runSkill('update-knowledge', kho.selected, { onDone: () => loadTree() }); });
  loaders['kho'] = (params) => {
    loadTree().then(() => { const p = params?.get('path'); if (p) openFile(p); }).catch(toast);
  };

  // ---------------------------------------------------------------- Tab 3: Agent & Skill
  const as = { selected: null };
  async function loadAgentSkill() {
    const [agents, skills] = await Promise.all([api('/api/agents'), api('/api/skills')]);
    state.agents = agents; state.skills = skills;
    const mk = (x, sub) => el('li', { 'data-file': x.file, onclick: () => openAS(x.file) },
      el('div', { class: 'name' }, x.name, sub ? el('span', { class: 'muted small' }, ` · ${sub}`) : null),
      el('div', { class: 'desc', title: x.description }, x.description));
    $('#agentList').replaceChildren(...agents.map((a) => mk(a, a.domain ? 'lĩnh vực ' + a.domain : null)));
    $('#skillList').replaceChildren(...skills.map((s) => mk(s)));
    $$('#agentList li, #skillList li').forEach((li) => li.classList.toggle('selected', li.dataset.file === as.selected));
  }
  async function openAS(file) {
    as.selected = file;
    $$('#agentList li, #skillList li').forEach((li) => li.classList.toggle('selected', li.dataset.file === file));
    $('#asEdit').hidden = true; $('#asView').hidden = false;
    try {
      const f = await api('/api/files/' + file);
      const { fm, body } = splitFrontmatter(f.content);
      $('#asToolbar').hidden = false; $('#asPath').textContent = f.path;
      $('#asView').replaceChildren(metaBar(fm), el('p', { class: 'muted small' }, fm?.description || ''), renderMarkdown(body));
      $('#asEditor').value = f.content;
    } catch (e) { $('#asView').innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
  }
  $('#asEditBtn').addEventListener('click', () => { $('#asView').hidden = true; $('#asEdit').hidden = false; $('#asMsg').textContent = ''; });
  $('#asCancelBtn').addEventListener('click', () => { $('#asEdit').hidden = true; $('#asView').hidden = false; });
  $('#asSaveBtn').addEventListener('click', async () => {
    try {
      await api('/api/files/' + as.selected, { method: 'PUT', body: { content: $('#asEditor').value } });
      $('#asMsg').textContent = 'Đã lưu.'; await openAS(as.selected); await loadAgentSkill(); await loadAgents(); toast('Đã lưu ' + as.selected, 'info', 2500);
    } catch (e) { $('#asMsg').textContent = e.message; }
  });
  $('#newDomainBtn').addEventListener('click', () => {
    const name = $('#newDomain').value.trim();
    if (!name) { toast('Nhập tên lĩnh vực trước.'); return; }
    runSkill('create-domain-agent', name, { onDone: () => { loadAgentSkill().catch(toast); loadAgents().catch(toast); } });
  });
  loaders['agent-skill'] = () => loadAgentSkill().catch(toast);

  // ---------------------------------------------------------------- Tab 4: Chờ duyệt
  function fieldRow(label, value, cls) {
    if (value == null) return [];
    return [el('dt', {}, label), el('dd', { class: cls || '' }, typeof value === 'string' ? renderMarkdown(value) : value)];
  }
  function parseFields(body) {
    const out = {}; const re = /^- \*\*(.+?):\*\*\s*([\s\S]*?)(?=\n- \*\*|\n*$)/gm; let m;
    while ((m = re.exec(body))) out[m[1].trim()] = m[2].trim();
    return out;
  }
  function proposalCard(p) {
    const checks = [];
    const items = p.items.map((it) => {
      const f = parseFields(it.body);
      const cb = el('input', { type: 'checkbox', checked: true, value: it.index }); checks.push(cb);
      return el('div', { class: 'item' },
        el('label', { class: 'head', style: 'flex-direction:row;color:inherit;font-size:14px' }, p.status === 'cho-duyet' ? cb : null, `Đề xuất ${it.index} – ${it.title}`),
        el('dl', { class: 'fields' },
          fieldRow('Loại', f['Loại']), fieldRow('Vị trí', f['Vị trí']),
          fieldRow('Hiện tại', f['Nội dung hiện tại'], 'cur'), fieldRow('Đề xuất', f['Nội dung đề xuất'], 'new'),
          fieldRow('Nguồn', f['Nguồn']), fieldRow('Lý do chưa chắc chắn', f['Lý do chưa chắc chắn'])));
    });
    const actions = el('div', { class: 'actions' });
    if (p.status === 'cho-duyet') {
      if (p.target_exists) {
        actions.append(el('button', { class: 'primary', 'data-run': 1, disabled: state.running, onclick: async () => {
          const sel = checks.filter((c) => c.checked).map((c) => +c.value);
          if (!sel.length) { toast('Chọn ít nhất một đề xuất.'); return; }
          const all = sel.length === p.items.length;
          const logBox = $('#proposalLog'); logBox.hidden = false;
          await runStream(`/api/proposals/${encodeURIComponent(p.id)}/approve`, { items: all ? null : sel, kind: 'approve' }, logBox,
            { onDone: () => { loadProposals(); loadTree().catch(() => {}); } });
        } }, 'Duyệt (gọi Claude áp dụng)'));
      } else actions.append(el('span', { class: 'bad' }, 'File đích không tồn tại, không thể duyệt.'));
      actions.append(el('button', { class: 'danger', onclick: async () => {
        const note = await modal('Lý do từ chối (tuỳ chọn)', 'Ví dụ: nguồn chưa đủ tin cậy');
        if (note === null) return;
        try { await api(`/api/proposals/${encodeURIComponent(p.id)}/reject`, { method: 'POST', body: { note } }); toast('Đã từ chối.', 'info', 2500); loadProposals(); refreshStatus(); }
        catch (e) { toast(e); }
      } }, 'Từ chối'));
    } else if (p.decided) {
      actions.append(el('span', { class: 'muted' }, `Quyết định ngày ${p.decided}${p.decision_note ? ' – ' + p.decision_note : ''}`));
    }
    return el('div', { class: 'panel proposal' },
      el('header', {}, el('span', { class: 'status-tag ' + p.status }, p.status),
        el('span', {}, 'File đích: ', p.target_exists ? el('a', { href: '#kho?path=' + encodeURIComponent(p.target) }, p.target) : el('span', { class: 'bad' }, p.target)),
        el('span', { class: 'muted' }, `tạo ${p.created} · bởi ${p.proposed_by}`), el('span', { class: 'muted small' }, p.id)),
      items, actions);
  }
  async function loadProposals() {
    const st = $('#proposalStatus').value;
    const list = await api('/api/proposals?status=' + st);
    const box = $('#proposals');
    box.replaceChildren(...(list.length ? list.map(proposalCard) : [el('p', { class: 'muted panel' }, 'Không có đề xuất nào ở trạng thái này.')]));
    refreshStatus();
  }
  $('#proposalStatus').addEventListener('change', () => loadProposals().catch(toast));
  $('#reloadProposals').addEventListener('click', () => loadProposals().catch(toast));
  loaders['cho-duyet'] = () => loadProposals().catch(toast);

  // ---------------------------------------------------------------- Tab 5: Lịch sử
  async function loadHistory(_params, silent) {
    const rows = await api('/api/history?limit=100');
    $('#historySummary').textContent = `${rows.length} phiên gần nhất`;
    const tb = $('#historyTable tbody'); tb.innerHTML = '';
    for (const s of rows) {
      const tr = el('tr', {},
        el('td', {}, fmtTime(s.started_at)), el('td', {}, s.kind), el('td', {}, s.domain || s.skill_name || ''),
        el('td', { class: 'st-' + s.status }, s.status), el('td', { class: 'num' }, s.num_turns ?? '–'),
        el('td', { class: 'num' }, fmtMs(s.duration_ms)), el('td', { class: 'num' }, fmtCost(s.cost_usd)),
        el('td', { class: 'prompt', title: s.prompt }, s.prompt),
        el('td', {}, s.files.length ? [fileChips(s.files.filter((f) => !f.denied), false, true), fileChips(s.files.filter((f) => f.denied), true, true)] : el('span', { class: 'muted' }, '–')));
      tr.addEventListener('click', (ev) => {
        if (ev.target.closest('a')) return;
        const next = tr.nextElementSibling;
        if (next?.classList.contains('detail')) { next.remove(); return; }
        tr.after(el('tr', { class: 'detail' }, el('td', { colspan: 9 }, el('pre', {}, JSON.stringify({ ...s, files: undefined }, null, 2)))));
      });
      tb.append(tr);
    }
    if (!rows.length) tb.append(el('tr', {}, el('td', { colspan: 9, class: 'muted' }, 'Chưa có phiên nào.')));
    if (!silent) refreshStatus();
  }
  $('#reloadHistory').addEventListener('click', () => loadHistory().catch(toast));
  loaders['lich-su'] = (p, silent) => loadHistory(p, silent).catch(toast);

  // ---------------------------------------------------------------- Tab 6: Lịch tự động
  let schedTimer = null;
  async function loadScheduler() {
    const [s, runs] = await Promise.all([api('/api/scheduler'), api('/api/scheduler/runs?limit=50')]);
    const cb = $('#schedEnabled'); cb.checked = s.enabled;
    $('#schedEnabledText').textContent = s.enabled ? 'Lịch tự động: ĐANG BẬT' : 'Lịch tự động: đang tắt';
    $('#schedSummary').textContent = `Hôm nay ${s.today_count}/${s.max_daily_runs} lần · tối đa ${s.max_turns} lượt/phiên · ${s.git_commit ? 'tự commit' : 'không commit'}`
      + (s.timezone ? ` · múi giờ ${s.timezone}` : '') + (s.running ? ` · ĐANG CHẠY ${s.running.domain} (${s.running.step})` : '')
      + (s.scheduler_alive ? '' : ' · bộ lập lịch chưa chạy');
    const w = $('#schedWarnings'); w.replaceChildren(...(s.config_warnings || []).map((t) => el('div', { class: 'warnbox' }, '⚠ ' + t)));
    if (s.last_limit_hit) w.append(el('div', { class: 'warnbox' }, `⚠ Lần gần nhất chạm giới hạn sử dụng gói Claude lúc ${fmtTime(s.last_limit_hit)}; lần chạy kế tiếp sẽ thử lại.`));
    const tb = $('#schedJobs tbody'); tb.innerHTML = '';
    for (const j of s.jobs) {
      const last = j.last_run;
      tb.append(el('tr', { style: 'cursor:default' },
        el('td', {}, el('b', {}, j.domain), j.label ? el('span', { class: 'muted' }, ' ' + j.label) : null),
        el('td', {}, el('code', {}, j.cron)),
        el('td', {}, j.next_run ? fmtTime(j.next_run) : el('span', { class: 'muted' }, s.enabled ? '–' : 'tắt')),
        el('td', {}, last ? fmtTime(last.started_at) : el('span', { class: 'muted' }, 'chưa chạy')),
        el('td', { class: last ? 'st-' + last.status : '' }, last ? `${last.status}${last.commit_hash ? ' · ' + last.commit_hash : ''}` : ''),
        el('td', {}, el('button', { 'data-run': 1, disabled: state.running || !!s.running, onclick: async () => {
          try { await api('/api/scheduler/run/' + encodeURIComponent(j.domain), { method: 'POST' }); toast(`Đã bắt đầu chạy ${j.domain} (2 phiên Claude).`, 'info', 4000); setTimeout(() => loadScheduler().catch(toast), 1500); }
          catch (e) { toast(e); }
        } }, 'Chạy ngay'))));
    }
    if (!s.jobs.length) tb.append(el('tr', {}, el('td', { colspan: 6, class: 'muted' }, 'Không có job nào trong config.yaml.')));
    const rb = $('#schedRuns tbody'); rb.innerHTML = '';
    for (const r of runs) {
      rb.append(el('tr', { style: 'cursor:default' }, el('td', {}, fmtTime(r.started_at)), el('td', {}, r.domain), el('td', {}, r.trigger),
        el('td', { class: 'st-' + r.status }, r.status), el('td', {}, r.step || ''), el('td', {}, r.commit_hash || ''), el('td', { title: r.message || '' }, (r.message || '').slice(0, 160))));
    }
    if (!runs.length) rb.append(el('tr', {}, el('td', { colspan: 7, class: 'muted' }, 'Chưa có lần chạy tự động nào.')));
    refreshStatus();
  }
  $('#schedEnabled').addEventListener('change', async (e) => {
    try { await api('/api/scheduler/toggle', { method: 'POST', body: { enabled: e.target.checked } }); toast(e.target.checked ? 'Đã bật lịch tự động.' : 'Đã tắt lịch tự động.', 'info', 2500); loadScheduler(); }
    catch (err) { toast(err); e.target.checked = !e.target.checked; }
  });
  $('#reloadSched').addEventListener('click', () => loadScheduler().catch(toast));
  loaders['lich-tu-dong'] = () => {
    loadScheduler().catch(toast);
    clearInterval(schedTimer);
    schedTimer = setInterval(() => { if (location.hash.startsWith('#lich-tu-dong')) loadScheduler().catch(() => {}); else clearInterval(schedTimer); }, 20000);
  };

  // ---------------------------------------------------------------- thông báo đề xuất chờ duyệt
  let lastPending = null;
  function notifyPending(n) {
    if (lastPending === null) { lastPending = n; if (n > 0) showBanner(n, false); return; }
    if (n > lastPending) {
      showBanner(n, true);
      toast(`Có ${n - lastPending} đề xuất mới cần bạn duyệt (tổng ${n}). Mở tab Chờ duyệt.`, 'info', 10000);
      if ('Notification' in window && Notification.permission === 'granted') {
        try { new Notification('AIGenProject – cần bạn duyệt', { body: `${n} đề xuất đang chờ duyệt trong knowledge/_cho-duyet/` }); } catch {}
      }
    } else if (n === 0) { $('#pendingBanner').hidden = true; }
    lastPending = n;
  }
  function showBanner(n, fresh) {
    const b = $('#pendingBanner');
    $('#pendingBannerText').textContent = fresh ? `Có đề xuất mới: ${n} đề xuất đang chờ bạn duyệt.` : `${n} đề xuất đang chờ bạn duyệt.`;
    b.hidden = false;
  }
  $('#pendingBannerClose').addEventListener('click', () => ($('#pendingBanner').hidden = true));
  if ('Notification' in window && Notification.permission === 'default') {
    document.addEventListener('click', () => Notification.requestPermission().catch(() => {}), { once: true });
  }

  // ---------------------------------------------------------------- hướng dẫn
  $('#helpBtn').addEventListener('click', () => ($('#helpModal').hidden = false));
  $('#helpClose').addEventListener('click', () => ($('#helpModal').hidden = true));
  $('#helpModal').addEventListener('click', (e) => { if (e.target.id === 'helpModal') $('#helpModal').hidden = true; });
  $$('#helpModal .help-table tr').forEach((tr) => {
    const code = tr.querySelector('code').textContent;
    const acts = tr.querySelector('.acts');
    acts.append(
      el('button', { onclick: () => { $('#prompt').value = code; $('#helpModal').hidden = true; location.hash = '#nghien-cuu'; $('#prompt').focus(); } }, 'Dùng mẫu'),
      el('button', { onclick: async () => { try { await navigator.clipboard.writeText(code); toast('Đã sao chép.', 'info', 1500); } catch { toast('Trình duyệt không cho sao chép; chọn và copy thủ công.'); } } }, 'Sao chép'),
    );
  });

  // ---------------------------------------------------------------- khởi động
  refreshStatus();
  setInterval(() => refreshStatus(), 60000);
  loadAgents().catch(toast);
  route();
})();
