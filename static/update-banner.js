/**
 * Operator-only "Update now" banner (King apps).
 *
 * - End users NEVER see deploy CTA (canDeploy must be true).
 * - Official channel always installs latest King-scheme tag (vN / vN.M).
 * - Older versions: operator opens GitHub Releases / deploy.js pin.
 *
 * GET /api/version → { hasUpdate, canDeploy, latestVersion, releasesUrl, ... }
 * POST /admin/deploy → operator only
 */
(function () {
  var POLL_MS = 60000;
  var BANNER_ID = 'king-update-banner';
  var KEY_PREFIX = 'kingAppVer:';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function ensureStyles() {
    if (document.getElementById('king-update-banner-css')) return;
    var st = document.createElement('style');
    st.id = 'king-update-banner-css';
    st.textContent = [
      '#' + BANNER_ID + '{position:fixed;left:12px;right:12px;bottom:12px;z-index:10000;',
      'display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:12px 14px;',
      'border-radius:12px;background:linear-gradient(135deg,#0f1b2e,#16263d);',
      'border:1px solid rgba(34,197,94,.35);box-shadow:0 12px 40px rgba(0,0,0,.45);',
      'color:#e8edf3;font:13px/1.35 system-ui,sans-serif}',
      '#' + BANNER_ID + ' .kub-label{flex:1;min-width:180px}',
      '#' + BANNER_ID + ' .kub-title{font-weight:700;color:#4ade80;font-size:12px;margin-bottom:2px}',
      '#' + BANNER_ID + ' .kub-sub{opacity:.75;font-size:12px}',
      '#' + BANNER_ID + ' .kub-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}',
      '#' + BANNER_ID + ' .kub-btn{border:0;border-radius:8px;padding:7px 12px;font-weight:700;',
      'font-size:12px;cursor:pointer;color:#fff;background:#16a34a;text-decoration:none;display:inline-block}',
      '#' + BANNER_ID + ' .kub-btn:disabled{opacity:.55;cursor:wait}',
      '#' + BANNER_ID + ' .kub-btn.secondary{background:transparent;color:#9ca3af;border:1px solid #334155}',
      '#' + BANNER_ID + ' .kub-cmd{font:11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;',
      'color:rgba(74,222,128,.75);max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;',
      'background:transparent;border:0;padding:0;cursor:pointer;text-align:left;text-decoration:none}',
      '#' + BANNER_ID + ' .kub-msg{width:100%;font-size:11px;opacity:.8}',
      '@media (max-width:520px){#' + BANNER_ID + '{left:8px;right:8px;bottom:8px}}',
    ].join('');
    document.head.appendChild(st);
  }

  function removeBanner() {
    var el = document.getElementById(BANNER_ID);
    if (el) el.remove();
  }

  function showBanner(d) {
    ensureStyles();
    var latest = d.latestVersion || d.version || '';
    var current = d.currentVersion || d.version || '';
    var app = d.app || 'app';
    var releases = d.releasesUrl || '';
    var latestLabel = String(latest).replace(/^v/, '');
    var el = document.getElementById(BANNER_ID);
    if (!el) {
      el = document.createElement('div');
      el.id = BANNER_ID;
      document.body.appendChild(el);
    }
    el.innerHTML =
      '<div class="kub-label">' +
      '<div class="kub-title">↑ Operator: new release v' + esc(latestLabel) + '</div>' +
      '<div class="kub-sub">Running ' + esc(current) + ' · ' + esc(app) + ' · admin only · all users get this version</div>' +
      '</div>' +
      '<div class="kub-actions">' +
      '<button type="button" class="kub-btn" data-act="update">Update now</button>' +
      (releases
        ? '<a class="kub-cmd" href="' + esc(releases) + '" target="_blank" rel="noopener">Pin older → GitHub Releases</a>'
        : '') +
      '<button type="button" class="kub-btn secondary" data-act="dismiss">×</button>' +
      '</div>' +
      '<div class="kub-msg" data-msg hidden></div>';

    el.querySelector('[data-act="dismiss"]').onclick = removeBanner;
    var up = el.querySelector('[data-act="update"]');
    if (up) {
      up.onclick = function () { runUpdate(up, el.querySelector('[data-msg]'), latest); };
    }
  }

  function runUpdate(btn, msgEl, latest) {
    if (btn.disabled) return;
    var ver = latest ? ('v' + String(latest).replace(/^v/, '')) : 'latest';
    if (!confirm(
      'OPERATOR: install official ' + ver + ' ke PROD?\n\n' +
      'Semua user langsung pindah ke versi ini.\n' +
      'Versi lama: GitHub Releases / deploy.js pin.'
    )) return;
    btn.disabled = true;
    btn.textContent = 'Updating…';
    if (msgEl) {
      msgEl.hidden = false;
      msgEl.textContent = 'Deploying ' + ver + ' (snapshot + tag + restart)…';
    }
    var headers = { 'Accept': 'application/json', 'Content-Type': 'application/json' };
    try {
      var tok = sessionStorage.getItem('kingDeployToken') || localStorage.getItem('kingDeployToken');
      if (tok) headers['Authorization'] = 'Bearer ' + tok;
    } catch (e) {}

    fetch('/admin/deploy', {
      method: 'POST',
      credentials: 'include',
      headers: headers,
      cache: 'no-store',
      body: JSON.stringify({ version: 'latest' }),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
      })
      .then(function (res) {
        if (res.status === 401 || res.status === 403) {
          var t = prompt('Operator token / admin login required:');
          if (t) {
            try { sessionStorage.setItem('kingDeployToken', t); } catch (e) {}
            btn.disabled = false;
            btn.textContent = 'Update now';
            return runUpdate(btn, msgEl, latest);
          }
        }
        if (!res.ok || (res.body && res.body.status === 'error')) {
          var err = (res.body && (res.body.error || res.body.message || res.body.stderr)) || ('HTTP ' + res.status);
          if (msgEl) msgEl.textContent = 'Gagal: ' + err;
          btn.disabled = false;
          btn.textContent = 'Retry';
          return;
        }
        if (msgEl) msgEl.textContent = 'OK — reloading…';
        setTimeout(function () { location.reload(); }, 2500);
      })
      .catch(function (e) {
        if (msgEl) msgEl.textContent = 'Network/error: ' + (e && e.message ? e.message : e);
        btn.disabled = false;
        btn.textContent = 'Retry';
      });
  }

  function showReloadToast(ver) {
    var id = 'king-reload-toast';
    if (document.getElementById(id) || document.getElementById(BANNER_ID)) return;
    ensureStyles();
    var el = document.createElement('div');
    el.id = id;
    el.innerHTML =
      '<div id="' + BANNER_ID + '">' +
      '<div class="kub-label"><div class="kub-title">🚀 Server updated</div>' +
      '<div class="kub-sub">' + esc(ver) + ' ready — reload</div></div>' +
      '<div class="kub-actions">' +
      '<button type="button" class="kub-btn" onclick="location.reload()">Reload</button>' +
      '<button type="button" class="kub-btn secondary" onclick="this.closest(\'#' + id + '\').remove()">×</button>' +
      '</div></div>';
    document.body.appendChild(el);
  }

  function check() {
    fetch('/api/version', { cache: 'no-store', credentials: 'include' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var appKey = d.app || 'app';
        var ver = d.version || d.currentVersion || '';
        var prev = null;
        try { prev = localStorage.getItem(KEY_PREFIX + appKey); } catch (e) {}
        // OPERATOR ONLY: need update + canDeploy (admin/mentor/token)
        if (d.hasUpdate && d.canDeploy === true) {
          showBanner(d);
        } else {
          removeBanner();
          // soft reload toast only for operator sessions that can deploy
          if (d.canDeploy === true && prev && ver && prev !== ver) showReloadToast(ver);
        }
        try { localStorage.setItem(KEY_PREFIX + appKey, ver); } catch (e) {}
      })
      .catch(function () {});
  }

  // PH promo — dual path even if base.html hook missing
  (function loadPhPromo() {
    try {
      if (window.__PH_PROMO_BOOTED__ || document.querySelector('script[data-ph-promo]')) return;
      var s = document.createElement('script');
      s.src = '/static/ph-promo.js?v=20260725b';
      s.async = true;
      s.defer = true;
      s.setAttribute('data-ph-promo', '1');
      s.onerror = function () {
        try { console.warn('[ph-promo] missing — run update.bat / git pull master'); } catch (e) {}
      };
      (document.head || document.documentElement).appendChild(s);
    } catch (e) {}
  })();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', check);
  } else {
    check();
  }
  setInterval(check, POLL_MS);
})();
