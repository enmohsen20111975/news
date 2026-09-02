/* ============================================================
   News Agent Dashboard — Frontend Logic
   Auto-refresh, modular rendering, EGX-aware data display
   Tab system: All News | Telegram | Copy/Paste
   ============================================================ */

const API = {
  status: '/api/status',
  start: '/api/monitor/start',
  stop: '/api/monitor/stop',
  ingest: '/api/ingest',
  recommendations: '/api/recommendations',
  telegramStatus: '/api/telegram/status',
  telegramSendCode: '/api/telegram/send-code',
  telegramVerify: '/api/telegram/verify',
  telegramChannels: '/api/telegram/channels',
};

const REFRESH_INTERVAL = 15000; // 15 seconds
const AUTO_REFRESH = true;

let refreshTimer = null;
let countdownValue = REFRESH_INTERVAL / 1000;
let allNews = [];

const El = {
  total: document.getElementById('total-count'),
  pending: document.getElementById('pending-count'),
  analyzed: document.getElementById('analyzed-count'),
  sent: document.getElementById('sent-count'),
  statusPill: document.getElementById('status-pill'),
  telegramState: document.getElementById('telegram-state'),
  newsList: document.getElementById('news-list'),
  telegramNewsList: document.getElementById('telegram-news-list'),
  copyNewsList: document.getElementById('copy-news-list'),
  logList: document.getElementById('log-list'),
  startBtn: document.getElementById('start-btn'),
  stopBtn: document.getElementById('stop-btn'),
  refreshBtn: document.getElementById('refresh-btn'),
  filterSelect: document.getElementById('filter-select'),
  lastUpdate: document.getElementById('last-update'),
  countdownEl: document.getElementById('countdown'),
  newsCount: document.getElementById('news-count'),
  logCount: document.getElementById('log-count'),
  tabButtons: document.querySelectorAll('.tab-btn'),
  tabContents: document.querySelectorAll('.tab-content'),
  pasteText: document.getElementById('paste-text'),
  pasteSource: document.getElementById('paste-source'),
  pasteSubmit: document.getElementById('paste-submit'),
  toast: document.getElementById('toast'),
  telegramAuthState: document.getElementById('telegram-auth-state'),
  telegramPhone: document.getElementById('telegram-phone'),
  telegramCode: document.getElementById('telegram-code'),
  telegramPassword: document.getElementById('telegram-password'),
  telegramSendCode: document.getElementById('telegram-send-code'),
  telegramVerify: document.getElementById('telegram-verify'),
  telegramLoadChannels: document.getElementById('telegram-load-channels'),
  telegramSaveChannels: document.getElementById('telegram-save-channels'),
  telegramChannelHint: document.getElementById('telegram-channel-hint'),
  telegramChannelList: document.getElementById('telegram-channel-list'),
  recommendationsList: document.getElementById('recommendations-list'),
};

/* ============ Utility Helpers ============ */

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatTimeAgo(isoStr) {
  if (!isoStr) return '';
  const date = new Date(isoStr);
  if (isNaN(date.getTime())) return '';
  const now = new Date();
  const diff = Math.floor((now - date) / 1000);

  if (diff < 60) return `${diff} ثواني`;
  if (diff < 3600) return `${Math.floor(diff / 60)} دقيقة`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ساعة`;
  const days = Math.floor(diff / 86400);
  if (days === 1) return 'أمس';
  return `${days} أيام`;
}

function formatTimestamp(isoStr) {
  if (!isoStr) return '';
  const date = new Date(isoStr);
  if (isNaN(date.getTime())) return '';
  return date.toLocaleString('ar-EG', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function parseLogLevel(line) {
  const match = line.match(/\[(\w+)\]/);
  return match ? match[1] : '';
}

function truncate(text, len) {
  if (!text) return '';
  return text.length > len ? text.slice(0, len) + '…' : text;
}

function getImportanceClass(score) {
  if (score >= 75) return 'high';
  if (score >= 50) return 'medium';
  return 'low';
}

function getSentimentLabel(ar) {
  const labels = { bullish: 'إيجابي', bearish: 'سلبي', neutral: 'محايد' };
  return labels[ar] || ar || 'محايد';
}

function getImpactLabel(ar) {
  const labels = {
    earnings: 'أرباح',
    dividend: 'توزيع',
    ipo: 'طرح',
    acquisition: 'استحواذ',
    macro: 'ماكرو',
    regulation: 'لوائح',
    price_move: 'حركة سعر',
    general: 'عام',
  };
  return labels[ar] || ar || 'عام';
}

function parseTickers(field) {
  if (!field) return [];
  if (Array.isArray(field)) return field;
  try {
    const parsed = JSON.parse(field);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function showToast(message, type = 'success') {
  const toast = El.toast;
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  setTimeout(() => toast.classList.remove('show'), 3000);
}

function setButtonLoading(btn, loading, originalText) {
  if (!btn) return;
  if (loading) {
    btn.disabled = true;
    btn.dataset.original = originalText || btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span> ${originalText || btn.innerHTML}`;
  } else {
    btn.disabled = false;
    btn.innerHTML = btn.dataset.original || btn.innerHTML;
  }
}

/* ============ Status Fetching ============ */

async function fetchStatus() {
  try {
    const res = await fetch(API.status);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('Status fetch error:', err);
    return null;
  }
}

async function startAgent() {
  setButtonLoading(El.startBtn, true, 'بدء التشغيل...');
  try {
    const res = await fetch(API.start, { method: 'POST' });
    const data = await res.json();
    showToast(data.message || 'تم تشغيل المشروع', data.ok ? 'success' : 'error');
    await loadStatus();
  } catch (err) {
    showToast('خطأ في الاتصال بالخادم', 'error');
  } finally {
    setButtonLoading(El.startBtn, false);
  }
}

async function stopAgent() {
  setButtonLoading(El.stopBtn, true, 'إيقاف...');
  try {
    const res = await fetch(API.stop, { method: 'POST' });
    const data = await res.json();
    showToast(data.message || 'تم إيقاف المشروع', data.ok ? 'success' : 'error');
    await loadStatus();
  } catch (err) {
    showToast('خطأ في الاتصال بالخادم', 'error');
  } finally {
    setButtonLoading(El.stopBtn, false);
  }
}

/* ============ Tab System ============ */

function initTabs() {
  El.tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;

      El.tabButtons.forEach(b => b.classList.remove('active'));
      El.tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const contentEl = document.getElementById(`tab-${tab}-content`);
      if (contentEl) contentEl.classList.add('active');
    });
  });
}

/* ============ Rendering ============ */

function renderStats(stats) {
  El.total.textContent = stats.total ?? 0;
  El.pending.textContent = stats.pending ?? 0;
  El.analyzed.textContent = stats.analyzed ?? 0;
  El.sent.textContent = stats.sent ?? 0;

  El.total.className = 'value';
  El.pending.className = 'value small';
  El.analyzed.className = 'value small';
  El.sent.className = 'value small';

  if (stats.pending > 10) {
    El.pending.classList.add('yellow');
  }
  if (stats.sent > 0) {
    El.sent.classList.add('green');
  }
}

function renderStatusPill(running) {
  El.statusPill.innerHTML = `
    <span class="dot"></span>
    <span>${running ? 'المشروع يعمل الآن' : 'متوقف'}</span>
  `;
  El.statusPill.className = `status-pill ${running ? 'running' : 'stopped'}`;

  const telegramText = running ? 'متصل' : 'غير متصل';
  const telegramColor = running ? 'var(--success)' : 'var(--accent-2)';
  El.telegramState.innerHTML = `<span style="color: ${telegramColor};">${telegramText}</span>`;
}

function renderNews(newsItems, filter = 'all') {
  if (!newsItems || !newsItems.length) {
    El.newsList.innerHTML = `
      <li class="news-item muted">
        <div class="empty-state">
          <div style="font-size: 2.5rem; margin-bottom: 8px;">📭</div>
          <p>لا توجد أخبار بعد — يتم جمعها الأن</p>
        </div>
      </li>
    `;
    if (El.newsCount) El.newsCount.textContent = 0;
    return;
  }

  let filtered = newsItems;
  if (filter === 'important') {
    filtered = newsItems.filter(n => (n.importance || 0) >= 55);
  } else if (filter === 'analyzed') {
    filtered = newsItems.filter(n => n.status === 'analyzed' || n.status === 'sent');
  } else if (filter === 'unsent') {
    filtered = newsItems.filter(n => !n.sent_ok);
  }

  if (!filtered.length) {
    El.newsList.innerHTML = `
      <li class="news-item muted">
        <div class="empty-state">
          <div style="font-size: 2.5rem; margin-bottom: 8px;">📭</div>
          <p>لا توجد أخبار تطابق هذا الفلتر</p>
        </div>
      </li>
    `;
  } else {
    El.newsList.innerHTML = filtered.map(item => createNewsItem(item)).join('');
  }

  if (El.newsCount) {
    El.newsCount.textContent = filtered.length;
  }
}

function renderTelegramNews(newsItems) {
  const telegramNews = newsItems.filter(n => n.source_type === 'telegram');

  if (!telegramNews.length) {
    El.telegramNewsList.innerHTML = `
      <li class="news-item muted">
        <div class="empty-state">
          <div style="font-size: 2.5rem; margin-bottom: 8px;">📱</div>
          <p>لا توجد أخبار من تيليجرام بعد</p>
        </div>
      </li>
    `;
    return;
  }

  El.telegramNewsList.innerHTML = telegramNews
    .slice(0, 10)
    .map(item => createNewsItem(item))
    .join('');
}

function renderCopyNews(newsItems) {
  const copyNews = newsItems.filter(n => n.source_type === 'copy');

  if (!copyNews.length) {
    El.copyNewsList.innerHTML = `
      <li class="news-item muted">
        <div class="empty-state">
          <div style="font-size: 2.5rem; margin-bottom: 8px;">📋</div>
          <p>أرسل أخباراً يدوياً باستخدام النموذج أعلاه</p>
        </div>
      </li>
    `;
    return;
  }

  El.copyNewsList.innerHTML = copyNews
    .slice(0, 10)
    .map(item => createNewsItem(item))
    .join('');
}

async function fetchRecommendations() {
  try {
    const res = await fetch(API.recommendations);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    console.log('Recommendations API response:', data);
    return data;
  } catch (err) {
    console.error('Recommendations fetch error:', err);
    return null;
  }
}

function getActionLabel(action) {
  const labels = {
    BUY: 'شراء',
    SELL: 'بيع',
    HOLD: 'احتفاظ',
  };
  return labels[action] || action || 'شراء';
}

function getActionClass(action) {
  if (action === 'BUY') return 'text-success';
  if (action === 'SELL') return 'text-danger';
  return 'text-warning';
}

function getRecTypeLabel(type) {
  const labels = {
    'شراء واحتفاظ': 'شراء واحتفاظ',
    'دعم/ارتداد': 'دعم/ارتداد',
    'T+1/مضاربة': 'مضاربة',
    'detailed': 'تحليل مفصل',
    'brief': 'موجز',
  };
  return labels[type] || type || 'عام';
}

function renderRecommendations(data, isRunning) {
  if (!data || !El.recommendationsList) return;

  const groups = data.groups || [];
  const total = data.total || 0;
  const groupCount = data.group_count || 0;

  if (!groups.length) {
    const message = !isRunning
      ? 'المشروع متوقف حالياً — اضغط "تشغيل المشروع" لتشغيل الـ Local AI وجمع التوصيات'
      : 'لا توجد توصيات بعد — يتم جمعها من الأخبار المحللة';
    El.recommendationsList.innerHTML = `
      <li class="news-item muted">
        <div class="empty-state">
          <div style="font-size: 2.5rem; margin-bottom: 8px;">📊</div>
          <p>${message}</p>
        </div>
      </li>
    `;
    return;
  }

  let html = '';
  for (const group of groups) {
    const symbol = group.symbol || 'غير معروف';
    const nameAr = group.name_ar || '';
    const count = group.count || 0;
    const recs = group.recommendations || [];

    html += `
      <li class="rec-group">
        <div class="rec-group-header">
          <div>
            <span class="ticker-badge">${escapeHtml(symbol)}</span>
            ${nameAr ? `<span class="rec-name">${escapeHtml(nameAr)}</span>` : ''}
          </div>
          <span class="rec-count-badge">${count} توصية</span>
        </div>
        <div class="rec-group-items">
          ${recs.map(rec => `
            <div class="rec-item">
              <div class="rec-top">
                <span class="tag ${getActionClass(rec.action)}">${getActionLabel(rec.action)}</span>
                <span class="tag">${escapeHtml(getRecTypeLabel(rec.recommendation_type))}</span>
                <span class="tag status-${rec.status === 'PENDING' ? 'pending' : rec.status === 'SENT' ? 'sent' : 'analyzed'}">${rec.status === 'PENDING' ? 'قيد الانتظار' : rec.status === 'SENT' ? 'تم الإرسال' : rec.status || ''}</span>
                ${rec.sent_ok ? '<span class="tag text-success">✓ مرسل</span>' : ''}
              </div>
              <div class="rec-meta">
                ${rec.entry_price != null ? `<span class="rec-price">سعر الدخول: <strong>${rec.entry_price}</strong></span>` : ''}
                ${rec.target_price != null ? `<span class="rec-price">الهدف: <strong>${rec.target_price}</strong></span>` : ''}
                ${rec.stop_loss != null ? `<span class="rec-price stop">وقف الخسارة: <strong>${rec.stop_loss}</strong></span>` : ''}
              </div>
              ${rec.recommendation_reason ? `<div class="rec-summary">${escapeHtml(truncate(rec.recommendation_reason, 200))}</div>` : ''}
              <div class="rec-footer">
                <span class="source">👤 ${escapeHtml(rec.expert_name || 'محلل محلي')}</span>
                <span class="time">📅 ${rec.session_date || ''} · 🕒 ${formatTimeAgo(rec.created_at) || '-'}</span>
              </div>
            </div>
          `).join('')}
        </div>
      </li>
    `;
  }

  El.recommendationsList.innerHTML = html;
}


function renderLogs(logLines) {
  El.logList.innerHTML = '';
  if (!logLines || !logLines.length) {
    El.logList.innerHTML = '<li class="log-item muted">لا يوجد سجل بعد</li>';
    if (El.logCount) El.logCount.textContent = 0;
    return;
  }

  El.logList.innerHTML = logLines.slice().reverse().map(line => {
    const level = parseLogLevel(line);
    const levelClass = level ? level.toLowerCase() : 'info';
    const safeLine = escapeHtml(line);
    const timeMatch = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
    const timeStr = timeMatch ? timeMatch[1] : '';
    const message = timeMatch ? line.slice(timeMatch[0].length + 1).trim() : line;
    return `<li class="log-item">
      <span class="log-time">${escapeHtml(timeStr)}</span>
      <span class="log-level ${levelClass}">${escapeHtml(message)}</span>
    </li>`;
  }).join('');

  if (El.logCount) {
    El.logCount.textContent = logLines.length;
  }
}

function parseImagePaths(field) {
  if (!field) return [];
  if (Array.isArray(field)) return field;
  try {
    const parsed = JSON.parse(field);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function parsePublishedLinks(field) {
  if (!field) return {};
  if (typeof field === 'object') return field;
  try {
    return JSON.parse(field);
  } catch {
    return {};
  }
}

function createNewsItem(item) {
  const sentiment = item.sentiment || 'neutral';
  const importance = item.importance || 0;
  const impactType = item.impact_type || 'general';
  const impClass = getImportanceClass(importance);
  const sentLabel = getSentimentLabel(sentiment);
  const impactLabel = getImpactLabel(impactType);
  const tickers = parseTickers(item.tickers);
  const imagePaths = parseImagePaths(item.image_paths);
  const imageUrls = parseImagePaths(item.image_urls);
  const sourceTypeLabel = item.source_type === 'telegram' ? 'تيليجرام'
    : item.source_type === 'rss' ? 'RSS'
    : item.source_type === 'web' ? 'ويب'
    : item.source_type === 'copy' ? 'نسخ يدوي'
    : item.source_type || '';

  const tickerHtml = tickers.length
    ? `<div class="news-meta" style="margin-top:6px;">
         ${tickers.map(t => `<span class="ticker-badge">${escapeHtml(t)}</span>`).join('')}
       </div>`
    : '';

  const images = [...imageUrls, ...imagePaths];
  const imagesHtml = images.length
    ? `<div class="news-images">
         ${images.slice(0, 4).map(src => {
           const isLocal = src.startsWith('/') || src.startsWith('data/') || src.startsWith('telegram_images/');
           const displaySrc = isLocal ? `/images/${Path(src).name}` : src;
           return `<img src="${escapeHtml(displaySrc)}" alt="صورة الخبر" loading="lazy" onerror="this.style.display='none'" />`;
         }).join('')}
       </div>`
    : '';

  const publishedLinks = parsePublishedLinks(item.published_links);
  const linksHtml = Object.entries(publishedLinks).filter(([_, v]) => v).length
    ? `<div class="published-links">
         ${Object.entries(publishedLinks).filter(([_, v]) => v).map(([platform, link]) => 
           `<a href="${escapeHtml(link)}" target="_blank" rel="noopener">🔗 ${escapeHtml(platform)}</a>`
         ).join('')}
       </div>`
    : '';

  const statusLabel = item.status === 'pending' ? 'في الانتظار'
    : item.status === 'analyzed' ? 'محلل'
    : item.status === 'sent' ? 'مرسل'
    : item.status || '';

  return `
    <li class="news-item">
      <div class="news-top">
        <strong class="title">${escapeHtml(truncate(item.title || item.summary_ar || 'بدون عنوان', 100))}</strong>
        <span class="tag sentiment-${sentiment}">${sentLabel}</span>
      </div>

      <div class="news-meta">
        <span class="importance-badge ${impClass}">أهمية ${importance}/100</span>
        <span class="tag impact-${impactType}">${impactLabel}</span>
        <span class="tag status-${item.status || 'pending'}">${statusLabel}</span>
        <span class="tag">${sourceTypeLabel}</span>
      </div>

      ${tickerHtml}

      <div class="importance-bar">
        <div class="fill ${impClass}" style="width: ${Math.min(100, importance)}%"></div>
      </div>

      <div class="news-summary">${escapeHtml(truncate(item.news_text || item.summary_ar || '', 180)) || 'لا يوجد ملخص'}</div>

      ${!item.is_valid_news && item.importance === 0 ? `
        <div class="news-reasoning" style="background: rgba(255,107,107,0.08); border-color: rgba(255,107,107,0.25);">
          <strong>⚠️ تنبيه:</strong> هذا الخبر غير صالح — تم تجاهله من الإرسال للموقع
        </div>
      ` : ''}

      ${imagesHtml}

      ${linksHtml}

      <div class="news-footer">
        <span class="source">📡 ${escapeHtml(item.source || '-')}</span>
        <span class="time">🕒 ${formatTimeAgo(item.collected_at) || formatTimestamp(item.collected_at) || '-'}</span>
      </div>
    </li>
  `;
}

/* ============ Paste-to-Analyze ============ */

async function submitPastedNews() {
  const text = (El.pasteText?.value || '').trim();
  const source = El.pasteSource?.value || 'manual_copy';

  if (!text) {
    showToast('الرجاء إلصاق نص الخبر أولاً', 'error');
    return;
  }

  setButtonLoading(El.pasteSubmit, true, 'جارٍ الإرسال...');
  try {
    const res = await fetch(API.ingest, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, source }),
    });
    const data = await res.json();

    if (data.ok) {
      showToast(data.message || 'تم إرسال الخبر للتحليل', 'success');
      El.pasteText.value = '';
      El.pasteSource.value = '';
      await loadStatus();
    } else {
      showToast(data.message || 'فشل الإرسال', 'error');
    }
  } catch (err) {
    showToast('خطأ في الاتصال بالخادم', 'error');
  } finally {
    setButtonLoading(El.pasteSubmit, false);
  }
}

async function sendTelegramCode() {
  const phone = (El.telegramPhone?.value || '').trim();
  setButtonLoading(El.telegramSendCode, true, 'جارٍ الإرسال...');
  try {
    const res = await fetch(API.telegramSendCode, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone }),
    });
    const data = await res.json();
    showToast(data.message || 'تعذر إرسال الكود', data.ok ? 'success' : 'error');
    if (data.authorized) updateTelegramAuth(true);
  } catch { showToast('تعذر الاتصال بخدمة Telegram', 'error'); }
  finally { setButtonLoading(El.telegramSendCode, false); }
}

async function verifyTelegram() {
  setButtonLoading(El.telegramVerify, true, 'جارٍ التحقق...');
  try {
    const res = await fetch(API.telegramVerify, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: El.telegramCode?.value.trim(),
        password: El.telegramPassword?.value || '',
      }),
    });
    const data = await res.json();
    showToast(data.message || 'تعذر تسجيل الدخول', data.ok ? 'success' : 'error');
    if (data.ok) { updateTelegramAuth(true); await loadTelegramChannels(); }
  } catch { showToast('تعذر الاتصال بخدمة Telegram', 'error'); }
  finally { setButtonLoading(El.telegramVerify, false); }
}

function updateTelegramAuth(authorized) {
  if (El.telegramAuthState) El.telegramAuthState.textContent = authorized ? 'متصل' : 'غير مسجل';
  if (El.telegramState) El.telegramState.textContent = authorized ? 'متصل' : 'غير متصل';
}

async function loadTelegramChannels() {
  try {
    const res = await fetch(API.telegramChannels);
    const data = await res.json();
    if (!data.ok) { showToast(data.message || 'سجل الدخول أولاً', 'error'); return; }
    El.telegramChannelList.innerHTML = data.channels.map(channel => `
      <label class="channel-option">
        <input type="checkbox" value="${escapeHtml(channel.value)}" />
        <span><strong>${escapeHtml(channel.title)}</strong><small>${escapeHtml(channel.username || channel.id)}</small></span>
      </label>
    `).join('') || '<span class="hint">لم يتم العثور على قنوات أو مجموعات</span>';
    El.telegramChannelHint.textContent = `${data.channels.length} قناة متاحة للاختيار`;
  } catch { showToast('تعذر تحميل القنوات', 'error'); }
}

async function saveTelegramChannels() {
  const channels = [...El.telegramChannelList.querySelectorAll('input:checked')].map(input => input.value);
  try {
    const res = await fetch(API.telegramChannels, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channels }),
    });
    const data = await res.json();
    showToast(data.message || 'تعذر حفظ القنوات', data.ok ? 'success' : 'error');
  } catch { showToast('تعذر حفظ القنوات', 'error'); }
}

async function loadTelegramAuth() {
  try {
    const res = await fetch(API.telegramStatus);
    const data = await res.json();
    updateTelegramAuth(Boolean(data.authorized));
  } catch { updateTelegramAuth(false); }
}

/* ============ Main Load ============ */

async function loadStatus() {
  const data = await fetchStatus();
  if (!data) {
    El.statusPill.textContent = 'خطأ في الاتصال';
    El.statusPill.className = 'status-pill error';
    return;
  }

  allNews = data.latest || [];

  renderStats(data.stats || {});
  renderStatusPill(data.running);

  const currentFilter = El.filterSelect?.value || 'all';
  renderNews(allNews, currentFilter);
  renderTelegramNews(allNews);
  renderCopyNews(allNews);
  renderLogs(data.last_log || []);

  const recData = await fetchRecommendations();
  renderRecommendations(recData, Boolean(data.running));

  if (El.lastUpdate) {
    El.lastUpdate.textContent = `آخر تحديث: ${formatTimestamp(data.timestamp)}`;
  }
}

/* ============ Countdown Timer ============ */

function startCountdown() {
  if (!AUTO_REFRESH) return;
  countdownValue = Math.floor(REFRESH_INTERVAL / 1000);

  if (refreshTimer) clearInterval(refreshTimer);

  refreshTimer = setInterval(() => {
    countdownValue--;
    if (countdownValue <= 0) {
      countdownValue = Math.floor(REFRESH_INTERVAL / 1000);
      loadStatus();
    }
    if (El.countdownEl) {
      El.countdownEl.textContent = countdownValue;
    }
  }, 1000);
}

/* ============ Event Listeners ============ */

document.addEventListener('DOMContentLoaded', function() {
  El.startBtn?.addEventListener('click', startAgent);
  El.stopBtn?.addEventListener('click', stopAgent);
  El.refreshBtn?.addEventListener('click', loadStatus);
  El.filterSelect?.addEventListener('change', loadStatus);
  El.pasteSubmit?.addEventListener('click', submitPastedNews);
  El.telegramSendCode?.addEventListener('click', sendTelegramCode);
  El.telegramVerify?.addEventListener('click', verifyTelegram);
  El.telegramLoadChannels?.addEventListener('click', loadTelegramChannels);
  El.telegramSaveChannels?.addEventListener('click', saveTelegramChannels);

  initTabs();
  loadStatus();
  loadTelegramAuth();
  startCountdown();
});
