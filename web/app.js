// 商业分析报告生成器 - 前端逻辑
// 通过 POST /api/generate 调起后端（generate.py serve）

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const TYPE_HINTS = {
  industry: '输入一个行业或领域，如「咖啡」「新能源汽车」「SaaS」',
  product: '输入一个产品名，如「Notion」「飞书」「瑞幸咖啡」',
  competitor: '输入要对比的产品，2-3 个，如「Notion vs Obsidian」「美团 vs 饿了么」',
};

// ---- 日志 ----
function log(msg, cls = '') {
  const el = $('#log');
  const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  const line = document.createElement('div');
  line.className = cls;
  line.textContent = `[${ts}] ${msg}`;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}
$('#clear-log').onclick = () => { $('#log').innerHTML = ''; };

// ---- 类型切换更新提示 ----
$$('input[name="type"]').forEach(r => {
  r.addEventListener('change', () => {
    $('#type-hint').textContent = TYPE_HINTS[r.value];
  });
});

// ---- AI 提供商切换：是否显示 preset ----
$('#ai').addEventListener('change', (e) => {
  const v = e.target.value;
  $('#preset-field').style.display = v === 'mock' ? '' : 'none';
});

// ---- 示范按钮 ----
$$('.examples button, #quick-coffee').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    const preset = btn.dataset.preset;
    if (!preset) return;
    const type = btn.dataset.type;
    const subject = btn.dataset.subject || $('#subject').value;
    $('#preset').value = preset;
    if (type) $$(`input[name="type"]`).forEach(r => r.checked = (r.value === type));
    if (subject) $('#subject').value = subject;
    $('#ai').value = 'mock';
    $('#preset-field').style.display = '';
    doSubmit();
  });
});

// ---- 提交 ----
$('#form').addEventListener('submit', (e) => {
  e.preventDefault();
  doSubmit();
});

async function doSubmit() {
  const type = $('input[name="type"]:checked').value;
  const subject = $('#subject').value.trim();
  const ai = $('#ai').value;
  const preset = $('#preset').value;
  const formats = [...$$('input[name="formats"]:checked')].map(c => c.value);

  if (!subject) {
    log('请输入主题', 'warn');
    return;
  }
  if (!formats.length) {
    log('至少选择一种输出格式', 'warn');
    return;
  }

  $('#submit').disabled = true;
  $('#preview-status').textContent = '生成中…';
  log(`开始生成：${type} / ${subject} / ${ai}${preset ? ' / preset=' + preset : ''}`, 'info');

  // v0.3: 用 fetch + ReadableStream 解析 SSE
  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, subject, ai, preset, formats }),
    });
    if (!res.ok && res.headers.get('content-type')?.includes('application/json')) {
      // 走老路径（错误响应是 JSON）
      const data = await res.json();
      log('❌ 生成失败: ' + (data.error || '未知错误'), 'err');
      $('#preview-status').textContent = '生成失败';
      return;
    }
    // SSE 流式
    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let finalData = null;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // 解析 SSE event (data: ...\n\n)
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';
      for (const chunk of lines) {
        const m = chunk.match(/^data:\s*(.+)$/m);
        if (!m) continue;
        try {
          const evt = JSON.parse(m[1]);
          log(`  ${evt.message || ''}`, evt.phase === 'error' ? 'err' : (evt.phase === 'llm' || evt.phase === 'render' ? 'info' : ''));
          if (evt.done) {
            finalData = evt;
          }
        } catch (e) {
          log('  [SSE 解析失败] ' + chunk.slice(0, 100), 'err');
        }
      }
    }
    if (!finalData) {
      log('❌ 未收到完成事件', 'err');
      $('#preview-status').textContent = '生成失败';
      return;
    }
    if (!finalData.ok) {
      log('❌ 生成失败: ' + (finalData.error || '未知错误'), 'err');
      $('#preview-status').textContent = '生成失败';
      return;
    }
    log('✅ 报告已生成', 'ok');
    if (finalData.title) log(`  📄 ${finalData.title}`);
    // 置信度
    const conf = finalData.confidence;
    if (conf) {
      const tag = {high: '高', medium: '中', low: '低', unknown: '未评估'}[conf.level] || conf.level;
      log(`  📊 置信度：${tag} (${(conf.score * 100).toFixed(0)}%) — ${conf.reasoning || ''}`,
          conf.level === 'low' ? 'warn' : '');
    }
    Object.entries(finalData.files || {}).forEach(([k, v]) => {
      if (k.endsWith('_error')) log(`  ⚠️  ${k}: ${v}`, 'warn');
      else log(`  • ${k}: ${v}`);
    });
    // 预览 HTML
    const htmlFile = finalData.preview || (finalData.files && finalData.files.html);
    if (htmlFile) {
      $('#preview').src = '/' + htmlFile;
      $('#preview-status').textContent = '就绪 · ' + htmlFile;
    } else if (finalData.files && finalData.files.md) {
      $('#preview').src = '/' + finalData.files.md;
      $('#preview-status').textContent = '就绪（仅 Markdown）· ' + finalData.files.md;
    }
  } catch (e) {
    log('❌ 网络错误: ' + e.message, 'err');
    $('#preview-status').textContent = '网络错误';
  } finally {
    $('#submit').disabled = false;
  }
}

// ---- 历史报告 ----
$('#link-history').onclick = (e) => { e.preventDefault(); openHistory(); };
$('#close-drawer').onclick = () => $('#drawer').hidden = true;
$('.drawer-mask').onclick = () => $('#drawer').hidden = true;

async function openHistory() {
  $('#drawer').hidden = false;
  $('#history-list').innerHTML = '加载中…';
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    if (!data.items || !data.items.length) {
      $('#history-list').innerHTML = '<p class="muted">还没有历史报告</p>';
      return;
    }
    const fileEntries = Object.entries(it.files || {});
    const primary = (it.files && it.files.html) || (it.files && it.files.md) || '';
    const otherLinks = fileEntries
      .filter(([k]) => k !== (primary.includes('html') ? 'html' : 'md'))
      .map(([k, v]) => `<a href="/${v}" target="_blank">${k.toUpperCase()}</a>`)
      .join(' · ');
    $('#history-list').innerHTML = data.items.map(it => `
      <div class="history-item" data-html="${primary}">
        <h4>${escapeHtml(it.title)}</h4>
        <div class="meta">${it.date} · ${escapeHtml(it.type)} · ${escapeHtml(it.subject)}</div>
        <div class="actions">
          ${primary ? `<a href="javascript:void(0)" data-preview="/${primary}">在右侧预览</a>` : ''}
          ${primary ? `<a href="/${primary}" target="_blank">新窗口</a>` : ''}
          ${otherLinks}
        </div>
      </div>
    `).join('');
    $$('.history-item [data-preview]').forEach(a => {
      a.onclick = (e) => {
        e.stopPropagation();
        $('#preview').src = a.dataset.preview;
        $('#preview-status').textContent = '历史报告 · ' + a.dataset.preview;
        $('#drawer').hidden = true;
      };
    });
  } catch (e) {
    $('#history-list').innerHTML = '加载失败: ' + e.message;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
