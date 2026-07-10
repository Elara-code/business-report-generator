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

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, subject, ai, preset, formats }),
    });
    const data = await res.json();
    if (!data.ok) {
      log('❌ 生成失败: ' + (data.error || '未知错误'), 'err');
      if (data.raw) log('  原始输出片段: ' + data.raw.slice(0, 200), 'err');
      $('#preview-status').textContent = '生成失败';
      return;
    }
    log('✅ 报告已生成', 'ok');
    Object.entries(data.files).forEach(([k, v]) => {
      if (k.endsWith('_error')) log(`  ⚠️  ${k}: ${v}`, 'warn');
      else log(`  • ${k}: ${v}`);
    });
    // 预览 HTML
    const htmlFile = data.files.html;
    if (htmlFile) {
      $('#preview').src = '/' + htmlFile;
      $('#preview-status').textContent = '就绪 · ' + htmlFile;
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
    $('#history-list').innerHTML = data.items.map(it => `
      <div class="history-item" data-html="${it.html}">
        <h4>${escapeHtml(it.title)}</h4>
        <div class="meta">${it.date} · ${escapeHtml(it.type)}</div>
        <div class="actions">
          <a href="/${it.html}" target="_blank">新窗口打开</a>
          <a href="javascript:void(0)" data-preview="/${it.html}">在右侧预览</a>
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
