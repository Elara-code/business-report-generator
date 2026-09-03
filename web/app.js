// Report Agent · 商业研究工作站（UI v3 · 项目分组 · 可调列宽 · 默认真实模型）
// 通过 POST /api/generate 调起后端研究流水线，SSE 驱动 7 阶段日志 / 来源面板 / 证据链

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const TYPE_LABEL = { industry: '行业分析', product: '产品拆解', competitor: '竞品对比' };
const STATUS_LABEL = {
  verified:   ['已核实', 'ok'],
  conflicted: ['冲突',   'conf'],
  unverified: ['待确认', 'warn'],
  estimate:   ['估算',   'warn'],
  inference:  ['推断',   'warn'],
};
const PHASES = ['parse', 'search', 'filter', 'extract', 'verify', 'draft', 'render'];

let currentReport = null; // { title, evidence, files, preview, confidence, dir }
let running = false;
let currentProject = ''; // '' = 默认分组；否则为项目名
const DEFAULT_PROJECT = '默认';

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
// 报告资源 URL：路径可能含中文项目名，必须编码（iframe src 未编码中文会 404）
function assetUrl(p) {
  return '/' + encodeURI(String(p ?? ''));
}

// ---------------- 顶栏 / 历史（按项目分组） ----------------
function renderHistoryList(data) {
  const list = $('#historyList');
  const groups = data.groups || [];
  if (!groups.length) {
    list.innerHTML = '<div class="chat-item" style="cursor:default"><span class="t" style="color:var(--navmuted)">还没有历史报告</span></div>';
    return;
  }
  list.innerHTML = groups.map((g) => {
    const itemsHtml = g.items.map((it) => `
      <button class="chat-item" data-title="${escapeHtml(it.title)}"
              data-dir="${escapeHtml(it.dir || '')}"
              data-html="${escapeHtml((it.files && it.files.html) || '')}">
        <i class="dot"></i><span class="t">${escapeHtml(it.title)}</span>
        <span class="st">${escapeHtml(it.type)}</span>
        <span class="del-btn" title="删除这条记录">🗑</span>
      </button>`).join('');
    const collapsed = (g.name !== DEFAULT_PROJECT && currentProject !== g.name) ? '' : '';
    return `<div class="proj-group" data-proj="${escapeHtml(g.name)}">
      <button class="proj-head" data-proj="${escapeHtml(g.name)}">
        <span class="caret">▾</span><span class="nm">${escapeHtml(g.name)}</span><span class="cnt">${g.items.length}</span>
      </button>
      <div class="proj-items">${itemsHtml}</div>
    </div>`;
  }).join('');

  // 高亮当前项目
  $$('.proj-head').forEach((h) => h.classList.toggle('active', h.dataset.proj === (currentProject || DEFAULT_PROJECT)));

  // 项目头：点名字选中（生成归入），点 caret 折叠
  $$('.proj-head').forEach((h) => {
    h.addEventListener('click', (e) => {
      if (e.target.classList.contains('caret')) {
        h.parentElement.classList.toggle('collapsed');
        return;
      }
      currentProject = h.dataset.proj === DEFAULT_PROJECT ? '' : h.dataset.proj;
      $$('.proj-head').forEach((x) => x.classList.toggle('active', x === h));
      flashProjectHint();
    });
  });
  // 记录点击：打开报告；删除按钮：删除该条
  $$('#historyList .chat-item').forEach((btn) => {
    btn.querySelector('.del-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteHistory(btn.dataset.dir, btn.dataset.title);
    });
    btn.addEventListener('click', () => openHistoryReport(btn));
  });
}
function flashProjectHint() {
  const nav = $('.nav-label');
  if (!nav) return;
  const base = '最近分析';
  const proj = currentProject ? ` · 当前：${currentProject}` : '';
  const old = nav.textContent;
  nav.textContent = base + proj;
  setTimeout(() => { nav.textContent = old.replace(/\s*·.*$/, ''); }, 2500);
}

function loadHistory() {
  fetch('/api/history')
    .then((r) => r.json())
    .then((data) => renderHistoryList(data))
    .catch(() => { $('#historyList').innerHTML = '<div class="chat-item"><span class="t" style="color:var(--navmuted)">历史加载失败</span></div>'; });
}
$('#historyBtn').onclick = () => {
  if (currentReport && currentReport.preview) window.open(assetUrl(currentReport.preview), '_blank');
};

function deleteHistory(dir, title) {
  if (!dir) return;
  if (!window.confirm(`删除这条报告？\n「${title}」\n（对应文件将一并删除，不可恢复）`)) return;
  fetch('/api/history/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dir }),
  }).then((r) => r.json()).then((d) => {
    if (d.ok) {
      loadHistory();
      if (currentReport && currentReport.dir === dir) {
        currentReport = null;
        $('#reportFrame').classList.add('hidden');
        $('#reportEmpty').classList.remove('hidden');
      }
    } else {
      window.alert('删除失败：' + (d.error || '未知错误'));
    }
  }).catch(() => window.alert('删除失败：网络错误'));
}

function createProject() {
  const name = window.prompt('输入新项目名（同一项目的报告会归类在一起）：', '');
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed) return;
  fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: trimmed }),
  }).then((r) => r.json()).then((d) => {
    if (d.ok) {
      currentProject = d.name;
      loadHistory();
    } else {
      window.alert('创建失败：' + (d.error || '未知错误'));
    }
  }).catch(() => window.alert('创建失败：网络错误'));
}
$('#newProjectBtn').onclick = createProject;

function openHistoryReport(btn) {
  const html = btn.dataset.html;
  const dir = btn.dataset.dir;
  const title = btn.dataset.title;
  if (!html) return;
  $$('#historyList .chat-item').forEach((x) => x.classList.remove('active'));
  btn.classList.add('active');
  currentReport = { title, preview: html, files: { html }, evidence: null, dir };
  $('#reportFrame').src = assetUrl(html);
  $('#reportFrame').classList.remove('hidden');
  $('#reportEmpty').classList.add('hidden');
  $('#filePill').textContent = html.split('/').pop();
  $('#chainList').innerHTML = '<div class="report-empty">加载证据链…</div>';
  $('#srcList').innerHTML = '<div class="report-empty">加载来源…</div>';
  $('#srcSummary').textContent = '';
  // 从落盘的 report.json 读取完整证据链
  if (dir) {
    fetch('/reports/' + dir + '/report.json').then((r) => r.json())
      .then((data) => {
        const ev = data.evidence || {};
        currentReport.evidence = ev;
        restoreTraceFromLog(ev.log);
        renderSourceBox(ev);
        renderChain(ev);
        renderSources(ev);
      })
      .catch(() => {
        $('#chainList').innerHTML = '<div class="report-empty">历史报告未包含证据链数据。</div>';
        $('#srcList').innerHTML = '<div class="report-empty">历史报告未包含来源清单。</div>';
      });
  }
}

// 打开历史报告时，用 report.json 中持久化的 evidence.log 恢复「运行日志 · 研究流水线」。
// 新报告 7 步齐全；老报告只有前 5 步，缺失步骤用完成态兜底。
function restoreTraceFromLog(log) {
  const keys = ['parse', 'search', 'filter', 'extract', 'verify', 'draft', 'render'];
  const fallback = ['任务解析完成', '检索完成', '来源筛选完成', '事实抽取完成', '交叉验证完成', '报告已生成', '渲染完成'];
  const steps = (log && log.steps) || [];
  keys.forEach((k, i) => {
    const st = steps[i];
    const msg = st ? (st.message || st.detail || fallback[i]) : fallback[i];
    stepState('step-' + k, 'done');
    setStepMsg('step-' + k, msg);
  });
  $('#runBadge').style.display = 'none';
  if (log) {
    const t = $('#traceTime');
    const start = String(log.started_at || '').replace('T', ' ').slice(0, 16);
    const sec = Math.round((log.elapsed_ms || 0) / 1000);
    t.textContent = (start || '历史') + (sec ? ` · ${sec}s` : '');
  }
}

// ---------------- 中栏：聊天 + 流水线 ----------------
function addUserBubble(text, meta) {
  const wrap = document.createElement('div');
  wrap.className = 'chat-user';
  wrap.innerHTML = `<div><div class="bubble">${escapeHtml(text)}</div><div class="meta">${escapeHtml(meta)}</div></div>`;
  $('#chatArea').appendChild(wrap);
}
function addAgentMessage(text) {
  const now = new Date().toLocaleTimeString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' });
  const el = document.createElement('div');
  el.className = 'agent-message';
  el.innerHTML = `<div class="head"><span class="agent-icon">R</span><b>Report Agent</b><span>${now} · 北京时间</span></div><p>${escapeHtml(text)}</p>`;
  $('#chatArea').appendChild(el);
}
function setStepMsg(stepId, msg) {
  const p = $(`#${stepId} .msg`);
  if (p) p.textContent = msg || '';
}
function stepState(stepId, state) {
  const el = $(`#${stepId}`);
  if (!el) return;
  el.classList.remove('done', 'current', 'issue', 'error');
  if (state) el.classList.add(state);
  const icon = el.querySelector('.step-icon');
  if (icon) icon.textContent = state === 'done' ? '✓' : state === 'current' ? '↻' : state === 'error' ? '✕' : icon.dataset.n || icon.textContent;
  if (!icon.dataset.n) icon.dataset.n = icon.textContent;
}
function resetTrace() {
  PHASES.forEach((p) => stepState('step-' + p, ''));
  $('#traceTime').textContent = '等待开始';
  $('#verifyChips').style.display = 'none';
  $('#verifyChips').innerHTML = '';
  $('#conflictBanner').style.display = 'none';
  $('#sourceBox').style.display = 'none';
  $('#chatArea').innerHTML = '';
  // 清空流水线各步日志与「证据驱动生成」骨架（outline 秒开留下的章节占位）
  document.querySelectorAll('.step .msg').forEach((p) => { p.textContent = ''; });
  const dob = $('#draftOutline');
  if (dob) { dob.innerHTML = ''; dob.style.display = 'none'; }
}
// 新建分析：完整重置工作台（输入框 + 对话/流水线 + 报告预览）
function resetWorkspace() {
  resetTrace();
  $('#prompt').value = '';
  setRunBadge('等待任务…', false);
  currentReport = null;
  $('#reportFrame').src = '';
  $('#reportFrame').classList.add('hidden');
  $('#reportEmpty').classList.remove('hidden');
  $('#filePill').textContent = 'report.html';
  $('#chainList').innerHTML = '<div class="report-empty">暂无数据</div>';
  $('#srcList').innerHTML = '<div class="report-empty">暂无数据</div>';
  $('#srcSummary').textContent = '';
  $$('#historyList .chat-item').forEach((x) => x.classList.remove('active'));
}
function setRunBadge(text, on) {
  $('#runBadge').style.display = on ? '' : 'none';
  $('#runBadgeText').textContent = text;
}

// 参数：输入框为空时用 placeholder 中的默认值
function paramVal(id) {
  const el = $(id);
  return (el.value.trim()) || (el.dataset.default || '');
}

// ---------------- 主流程 ----------------
async function doSubmit() {
  if (running) return;
  const type = $('.choice[data-group="type"].active')?.dataset.type || 'industry';
  const subject = $('#prompt').value.trim();
  const market = paramVal('#marketInput');
  const time_range = paramVal('#timeInput');
  const audience = paramVal('#audienceInput');
  const fmt = ($('#formatLabel').textContent || 'html').toLowerCase();
  const format = fmt === 'markdown' ? 'md' : fmt;
  const formats = [format];
  if (!subject) { $('#prompt').focus(); return; }

  running = true;
  resetTrace();
  setRunBadge('正在解析意图…', true);
  $('#sendBtn').disabled = true;
  $('#prompt').value = '';
  currentReport = null;

  const projTxt = currentProject ? ` · 项目：${currentProject}` : '';
  addUserBubble(subject, `已按参数：${TYPE_LABEL[type]} · ${market} / ${time_range}（北京时间） / ${audience} · 输出 ${format.toUpperCase()} · 真实模型${projTxt}`);
  addAgentMessage('收到。我会先解析分析意图，再搜索公开网络信息，抽取关键事实并进行多源交叉验证，最后只基于已核实的证据生成带来源引用的报告。未经确认的内容会单独标注。');
  $('#traceTime').textContent = '0s';
  const t0 = Date.now();
  const timer = setInterval(() => {
    $('#traceTime').textContent = Math.round((Date.now() - t0) / 1000) + 's';
  }, 1000);

  const PHASE_STEP = { parse: 'step-parse', search: 'step-search', filter: 'step-filter',
                       extract: 'step-extract', verify: 'step-verify', draft: 'step-draft',
                       render: 'step-render' };
  let lastIdx = -1;

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, subject, ai: 'openai', preset: null, formats, market, time_range, audience, project: currentProject }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || ('HTTP ' + res.status));
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let final = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';
      for (const chunk of lines) {
        const m = chunk.match(/^data:\s*(.+)$/m);
        if (!m) continue;
        let evt;
        try { evt = JSON.parse(m[1]); } catch { continue; }
        const phase = evt.phase;
        if (phase === 'error') {
          setRunBadge('失败', false);
          stepState('step-parse', 'error');
          addAgentMessage('生成失败：' + (evt.message || evt.error || '未知错误'));
          break;
        }
        if (phase === 'complete') { final = evt; break; }
        if (phase === 'outline') {
          // 报告骨架秒回：渲染章节占位（每节"生成中"）
          const sections = evt.sections || [];
          const box = $('#draftOutline');
          box.innerHTML = sections.map((t, i) =>
            `<div class="draft-sec" id="draft-sec-${i}"><span class="draft-sec-dot dot-wait"></span><span class="draft-sec-no">${String(i + 1).padStart(2, '0')}</span><b>${escapeHtml(t)}</b><span class="draft-sec-state">生成中…</span></div>`).join('');
          box.style.display = 'block';
          setRunBadge('正在生成报告（骨架已就绪，正在撰写全部章节，约 2-3 分钟）…', true);
          addAgentMessage(`报告骨架已生成，共 ${sections.length} 节，正在撰写全部章节…`);
          continue;
        }
        if (phase === 'section') {
          // 单节完成：更新骨架状态 + 展示该节要点
          const i = evt.index;
          const sec = evt.section || {};
          const kps = (sec.key_points || []).slice(0, 4);
          const node = $('#draft-sec-' + i);
          if (node) {
            node.classList.add('done');
            node.querySelector('.draft-sec-dot').className = 'draft-sec-dot dot-ok';
            node.querySelector('.draft-sec-state').textContent = '✓ 已完成';
            const tips = kps.length
              ? `<div class="draft-sec-tips">${kps.map((k) => `<span>${escapeHtml(k)}</span>`).join('')}</div>` : '';
            const chartType = (sec.chart && sec.chart.type && sec.chart.type !== 'null') ? sec.chart.type : null;
            node.insertAdjacentHTML('beforeend',
              `<div class="draft-sec-sum"><em>${escapeHtml(sec.content || '').slice(0, 90)}</em>${chartType ? `<span class="draft-chart-tag">配图 · ${chartType}</span>` : ''}</div>${tips}`);
          }
          setStepMsg('step-draft', `第 ${i + 1} 节《${sec.title || ''}》已生成`);
          setRunBadge(`正在生成报告（已生成 ${i + 1} 节…）`, true);
          continue;
        }
        if (PHASE_STEP[phase]) {
          const idx = PHASES.indexOf(phase);
          if (idx > lastIdx) {
            for (let i = 0; i < idx; i++) stepState('step-' + PHASES[i], 'done');
            stepState('step-' + phase, 'current');
            lastIdx = idx;
          }
          setStepMsg(PHASE_STEP[phase], evt.message || '');
          setRunBadge(({ parse: '正在解析任务…', search: '正在检索公开信息…', filter: '正在筛选来源…',
                         extract: '正在抽取事实（LLM 处理中，约 1-2 分钟）…', verify: '正在交叉验证…',
                         draft: '正在生成报告（LLM 起草中，约 2-4 分钟，请耐心等待）…',
                         render: '正在渲染导出…' })[phase] || phase, true);
        }
      }
    }
    if (!final) throw new Error('未收到完成事件');
    if (!final.ok) throw new Error(final.error || '生成失败');
    onComplete(final, type);
  } catch (e) {
    setRunBadge('失败', false);
    addAgentMessage('出错：' + e.message);
  } finally {
    clearInterval(timer);
    running = false;
    $('#sendBtn').disabled = false;
  }
}

// ---------------- 完成态 ----------------
async function onComplete(final, type) {
  PHASES.forEach((p) => stepState('step-' + p, 'done'));
  setRunBadge('已完成', false);
  setStepMsg('step-render', (final.message || '✅ 报告已生成'));
  // 流式骨架全部标记完成
  document.querySelectorAll('#draftOutline .draft-sec').forEach((n) => {
    n.classList.add('done');
    const dot = n.querySelector('.draft-sec-dot');
    const st = n.querySelector('.draft-sec-state');
    if (dot) dot.className = 'draft-sec-dot dot-ok';
    if (st) st.textContent = '✓ 已完成';
  });
  const evSummary = final.evidence || {};
  currentReport = { title: final.title, evidence: null, files: final.files || {}, preview: final.preview, confidence: final.confidence, dir: final.dir };

  // 验证 chips（complete 事件带计数摘要）
  const chips = $('#verifyChips');
  const chipMap = [['verified', '已核实'], ['conflicted', '冲突'], ['unverified', '待确认'], ['estimate', '估算']];
  let chipHtml = '';
  chipMap.forEach(([k, label]) => {
    const n = evSummary[k] || 0;
    if (n > 0) chipHtml += `<span class="fact-badge ${k}">${n} ${label}</span>`;
  });
  if (chipHtml) { chips.innerHTML = chipHtml; chips.style.display = 'flex'; }

  // 冲突横幅
  if (evSummary.conflicted > 0) {
    const b = $('#conflictBanner');
    b.innerHTML = `<b>⚠ 检测到 ${evSummary.conflicted} 处数据口径冲突：</b>相关论断已标注「冲突」，报告中将同时展示不同来源的口径，关键数字请以原始来源为准。`;
    b.style.display = '';
  }

  // 报告预览 iframe
  const preview = final.preview || (final.files && (final.files.html || final.files.md));
  if (preview) {
    $('#reportFrame').src = assetUrl(preview);
    $('#reportFrame').classList.remove('hidden');
    $('#reportEmpty').classList.add('hidden');
    $('#filePill').textContent = preview.split('/').pop();
  }
  // 证据链 / 来源清单 / 来源面板：从落盘的 report.json 拉取完整证据链
  if (final.dir) {
    $('#chainList').innerHTML = '<div class="report-empty">加载证据链…</div>';
    try {
      const res = await fetch('/' + final.dir + '/report.json');
      const data = await res.json();
      const ev = data.evidence || {};
      currentReport.evidence = ev;
      renderSourceBox(ev);
      renderChain(ev);
      renderSources(ev);
    } catch (e) {
      $('#chainList').innerHTML = '<div class="report-empty">证据链加载失败。</div>';
    }
  }
  addAgentMessage(final.title ? `报告已生成：${final.title}` : '报告已生成。');
  loadHistory();
}

function renderSourceBox(ev) {
  const sources = ev.sources || [];
  const facts = ev.facts || [];
  if (!sources.length) { $('#sourceBox').style.display = 'none'; return; }
  const nV = facts.filter((f) => f.status === 'verified').length;
  const nC = facts.filter((f) => f.status === 'conflicted').length;
  const nU = facts.filter((f) => f.status === 'unverified' || f.status === 'estimate').length;
  $('#sourceCount').textContent = `${sources.length} 个来源 · ${nV} 已核实 · ${nC} 冲突 · ${nU} 待确认`;
  const srcFacts = (id) => facts.filter((f) => (f.evidence || []).includes(id));
  $('#sourceList').innerHTML = sources.slice(0, 8).map((s, i) => {
    const fs = srcFacts(`s${i + 1}`);
    const verdict = fs.some((f) => f.status === 'conflicted') ? ['冲突', 'conf']
      : fs.length && fs.every((f) => f.status === 'verified') ? ['已核实', 'ok'] : ['待确认', 'warn'];
    const factHtml = fs.slice(0, 3).map((f) => {
      const [label, cls] = STATUS_LABEL[f.status] || ['待确认', 'warn'];
      return `<div class="fact"><span class="fact-badge ${cls}">${label}</span>${escapeHtml(f.claim)}</div>`;
    }).join('');
    return `<div class="source">
      <div class="row"><b>${escapeHtml(s.title)}</b><span class="tag ${verdict[1]}">${verdict[0]}</span></div>
      <small>${escapeHtml(s.domain || '')} · ${escapeHtml(s.published_at || '')} · ${escapeHtml(s.source_type || '')}</small>
      ${factHtml}
    </div>`;
  }).join('');
  $('#sourceBox').style.display = '';
}

function renderChain(ev) {
  const facts = ev.facts || [];
  const sources = ev.sources || [];
  const list = $('#chainList');
  if (!facts.length) { list.innerHTML = '<div class="report-empty">暂无事实数据</div>'; return; }
  list.innerHTML = facts.map((f) => {
    const [label, cls] = STATUS_LABEL[f.status] || ['待确认', 'warn'];
    const evRows = (f.evidence || []).map((eid) => {
      const n = parseInt(String(eid).replace(/\D/g, ''), 10);
      const s = sources[n - 1];
      const mark = f.status === 'conflicted' ? '✕' : f.status === 'verified' ? '✓' : '◐';
      return `<div class="ev-row">${mark} <span>${s ? `${escapeHtml(s.title)} [${n}] · ${escapeHtml(s.published_at || '')}` : `来源 ${eid}`}</span></div>`;
    }).join('');
    return `<div class="claim-card">
      <div class="q"><span class="tag ${cls}">${label}</span><b>${escapeHtml(f.claim)}</b></div>
      <div class="ev">${evRows || '<div class="ev-row">无直接来源</div>'}</div>
    </div>`;
  }).join('');
}

function renderSources(ev) {
  const sources = ev.sources || [];
  const facts = ev.facts || [];
  const list = $('#srcList');
  const summary = $('#srcSummary');
  if (!sources.length) { list.innerHTML = '<div class="report-empty">暂无来源数据</div>'; summary.textContent = ''; return; }
  const nV = facts.filter((f) => f.status === 'verified').length;
  const nC = facts.filter((f) => f.status === 'conflicted').length;
  const nU = facts.filter((f) => f.status === 'unverified' || f.status === 'estimate').length;
  summary.textContent = `${sources.length} 个收集来源 · ${nV} 已核实 · ${nC} 冲突 · ${nU} 待确认`;
  list.innerHTML = sources.map((s, i) => {
    const fs = facts.filter((f) => (f.evidence || []).includes(`s${i + 1}`));
    const verdict = fs.some((f) => f.status === 'conflicted') ? ['冲突', 'conf']
      : fs.length && fs.every((f) => f.status === 'verified') ? ['已核实', 'ok'] : ['待确认', 'warn'];
    const chips = fs.slice(0, 5).map((f) => `<span class="fact-chip">${escapeHtml((f.category || '事实'))}</span>`).join('');
    const url = s.url ? `<small>${escapeHtml(s.url)}</small>` : '';
    return `<div class="src-card"><div class="nm"><b>${escapeHtml(s.title)}</b><small>${escapeHtml(s.domain || '')} · ${escapeHtml(s.published_at || '')} · ${escapeHtml(s.source_type || '')}</small>${url}<div class="facts">${chips}</div></div><span class="verdict ${verdict[1]}">${verdict[0]}</span></div>`;
  }).join('');
}

// ---------------- 交互控件 ----------------
$$('.choice').forEach((b) => {
  b.addEventListener('click', () => {
    const g = b.dataset.group;
    $$(`.choice[data-group="${g}"]`).forEach((x) => x.classList.remove('active'));
    b.classList.add('active');
  });
});
const fmtMenu = $('#formatMenu'), fmtLabel = $('#formatLabel');
$('#formatTrigger').addEventListener('click', (e) => { e.stopPropagation(); fmtMenu.classList.toggle('show'); });
$$('.format-option').forEach((b) => b.addEventListener('click', () => {
  $$('.format-option').forEach((x) => x.classList.remove('selected'));
  b.classList.add('selected');
  fmtLabel.textContent = b.dataset.format.toUpperCase();
  fmtMenu.classList.remove('show');
}));
document.addEventListener('click', (e) => { if (!e.target.closest('.format-select')) fmtMenu.classList.remove('show'); });

// 视图切换
$$('.view-tab').forEach((t) => t.addEventListener('click', () => {
  $$('.view-tab').forEach((x) => x.classList.remove('active'));
  t.classList.add('active');
  ['report', 'chain', 'sources'].forEach((v) => {
    $('#view-' + v).classList.toggle('hidden', v !== t.dataset.view);
  });
}));

$('#sendBtn').addEventListener('click', doSubmit);
$('#prompt').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSubmit(); }
});
$('#newChat').onclick = () => {
  if (running) return;
  resetWorkspace();
  $('#prompt').focus();
};
$('#downloadBtn').onclick = () => {
  if (currentReport && currentReport.preview) window.open(assetUrl(currentReport.preview), '_blank');
};
$('#newWinBtn').onclick = () => {
  if (currentReport && currentReport.preview) window.open(assetUrl(currentReport.preview), '_blank');
};

// ---------------- 三栏列宽拖拽 ----------------
function setupDrag() {
  const shell = $('.shell');
  let active = null; // {type: 'l'|'r', startX, startL, startR, cols}

  const onMove = (e) => {
    if (!active) return;
    const dx = e.clientX - active.startX;
    let left = active.startL;
    let right = active.startR;
    if (active.type === 'l') {
      left = Math.min(460, Math.max(190, active.startL + dx));
    } else {
      right = Math.min(960, Math.max(400, active.startR - dx));
    }
    shell.style.gridTemplateColumns = `${left}px 10px minmax(380px,1fr) 10px ${right}px`;
  };
  const onUp = () => {
    if (!active) return;
    active.split.classList.remove('dragging');
    active = null;
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };
  $$('.col-split').forEach((split) => {
    split.addEventListener('mousedown', (e) => {
      const cs = getComputedStyle(shell);
      const cols = cs.gridTemplateColumns.split(' ').map((x) => parseFloat(x) || 0);
      active = {
        type: split.classList.contains('split-l') ? 'l' : 'r',
        startX: e.clientX,
        startL: cols[0] || 280,
        startR: cols[4] || 620,
        split,
      };
      split.classList.add('dragging');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      e.preventDefault();
    });
  });
}

// ---------------- 启动 ----------------
setupDrag();
loadHistory();
