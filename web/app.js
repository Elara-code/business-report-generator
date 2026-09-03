// Report Agent · 商业研究工作站（UI v2 落地版）
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

let currentReport = null; // { title, evidence, files, preview, confidence }
let running = false;

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// ---------------- 顶栏 / 历史 ----------------
function loadHistory() {
  fetch('/api/history')
    .then((r) => r.json())
    .then((data) => {
      const list = $('#historyList');
      if (!data.items || !data.items.length) {
        list.innerHTML = '<div class="chat-item" style="cursor:default"><span class="t" style="color:var(--navmuted)">还没有历史报告</span></div>';
        return;
      }
      list.innerHTML = data.items.map((it) => `
        <button class="chat-item" data-title="${escapeHtml(it.title)}"
                data-dir="${escapeHtml(it.dir || '')}"
                data-html="${escapeHtml((it.files && it.files.html) || '')}"
                data-md="${escapeHtml((it.files && it.files.md) || '')}">
          <i class="dot"></i><span class="t">${escapeHtml(it.title)}</span>
          <span class="st">${escapeHtml(it.type)}</span>
        </button>`).join('');
      $$('#historyList .chat-item[data-html]').forEach((btn) => {
        btn.onclick = () => openHistoryReport(btn);
      });
    })
    .catch(() => { $('#historyList').innerHTML = '<div class="chat-item"><span class="t" style="color:var(--navmuted)">历史加载失败</span></div>'; });
}
$('#historyBtn').onclick = () => {
  if (currentReport && currentReport.preview) window.open('/' + currentReport.preview, '_blank');
};

function openHistoryReport(btn) {
  const html = btn.dataset.html || btn.dataset.md;
  const dir = btn.dataset.dir;
  const title = btn.dataset.title;
  if (!html) return;
  $$('#historyList .chat-item').forEach((x) => x.classList.remove('active'));
  btn.classList.add('active');
  currentReport = { title, preview: html, files: { html: html }, evidence: null };
  $('#reportFrame').src = '/' + html;
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
}
function setRunBadge(text, on) {
  $('#runBadge').style.display = on ? '' : 'none';
  $('#runBadgeText').textContent = text;
}

// ---------------- 主流程 ----------------
async function doSubmit() {
  if (running) return;
  const type = $('.choice[data-group="type"].active')?.dataset.type || 'industry';
  const ai = $('.choice[data-group="engine"].active')?.dataset.engine || 'mock';
  const subject = $('#prompt').value.trim();
  const market = $('#marketSel').value;
  const time_range = $('#timeSel').value;
  const audience = $('#audienceSel').value;
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

  addUserBubble(subject, `已按参数：${TYPE_LABEL[type]} · ${market} / ${time_range}（北京时间） / ${audience} · 输出 ${format.toUpperCase()} · ${ai === 'openai' ? '真实模型' : '演示模式'}`);
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
      body: JSON.stringify({ type, subject, ai, preset: null, formats, market, time_range, audience }),
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
                         draft: '正在证据驱动生成（LLM 起草中，约 1-2 分钟）…',
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

  // 冲突横幅（用计数摘要即可提示）
  if (evSummary.conflicted > 0) {
    const b = $('#conflictBanner');
    b.innerHTML = `<b>⚠ 检测到 ${evSummary.conflicted} 处数据口径冲突：</b>相关论断已标注「冲突」，报告中将同时展示不同来源的口径，关键数字请以原始来源为准。`;
    b.style.display = '';
  }

  // 报告预览 iframe
  const preview = final.preview || (final.files && (final.files.html || final.files.md));
  if (preview) {
    $('#reportFrame').src = '/' + preview;
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
  summary.textContent = `${sources.length} 个收集来源 · ${ev.verified || 0} 已核实 · ${ev.conflicted || 0} 冲突 · ${ev.unverified || 0} 待确认`;
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
    if (g === 'engine') updateEngineHint();
  });
});
function updateEngineHint() {
  const e = $('.choice[data-group="engine"].active')?.dataset.engine;
  const h = $('#engineHint');
  if (!h) return;
  h.textContent = e === 'openai'
    ? '真实模型：联网检索 + LLM，需服务端配置 OPENAI_API_KEY'
    : '演示模式：离线语料，无需 Key';
}
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
  $('#prompt').value = '';
  $('#prompt').focus();
};
$('#downloadBtn').onclick = () => {
  if (currentReport && currentReport.preview) window.open('/' + currentReport.preview, '_blank');
};
$('#newWinBtn').onclick = () => {
  if (currentReport && currentReport.preview) window.open('/' + currentReport.preview, '_blank');
};

// ---------------- 启动 ----------------
loadHistory();
