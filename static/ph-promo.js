/**
 * PH-CHAIN / PH-Shop promo — sticky, rewel, self-healing.
 * Do not remove: re-injected by watchdog + MutationObserver.
 */
(function () {
  'use strict';
  if (window.__PH_PROMO_BOOTED__) return;
  window.__PH_PROMO_BOOTED__ = true;

  var ROOT_ID = 'ph-promo-root-v1';
  var STYLE_ID = 'ph-promo-style-v1';
  var HUB = 'https://parhan.dpdns.org/';
  var SHOP = 'https://parhan.dpdns.org/shop/';
  var COLLAPSE_KEY = 'ph_promo_collapse_until';
  var COLLAPSE_MS = 45 * 1000; // rewel: max 45s hide, then back

  function now() { return Date.now(); }

  function isCollapsed() {
    try {
      var t = Number(localStorage.getItem(COLLAPSE_KEY) || 0);
      return t > now();
    } catch (e) {
      return false;
    }
  }

  function collapseTemp() {
    try {
      localStorage.setItem(COLLAPSE_KEY, String(now() + COLLAPSE_MS));
    } catch (e) {}
    paint();
    setTimeout(paint, COLLAPSE_MS + 50);
  }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = [
      '#' + ROOT_ID + '{',
      '  all: initial;',
      '  position: fixed !important;',
      '  left: 0 !important; right: 0 !important; bottom: 0 !important;',
      '  z-index: 2147483000 !important;',
      '  font-family: system-ui,-apple-system,"Segoe UI",Roboto,sans-serif !important;',
      '  pointer-events: none !important;',
      '}',
      '#' + ROOT_ID + ' *{ box-sizing: border-box !important; font-family: inherit !important; }',
      '#' + ROOT_ID + ' .ph-shell{',
      '  pointer-events: auto !important;',
      '  margin: 0 10px 10px !important;',
      '  border: 2px solid #111 !important;',
      '  border-radius: 16px !important;',
      '  background: #111 !important;',
      '  color: #fff !important;',
      '  box-shadow: 4px 4px 0 #ABF600, 0 12px 40px rgba(0,0,0,.45) !important;',
      '  overflow: hidden !important;',
      '}',
      '#' + ROOT_ID + ' .ph-top{',
      '  display:flex !important; align-items:center !important; justify-content:space-between !important;',
      '  gap:8px !important; padding:8px 10px 0 !important;',
      '}',
      '#' + ROOT_ID + ' .ph-badge{',
      '  display:inline-flex !important; align-items:center !important; gap:6px !important;',
      '  font-size:11px !important; font-weight:800 !important; letter-spacing:.04em !important;',
      '  text-transform:uppercase !important; color:#ABF600 !important;',
      '}',
      '#' + ROOT_ID + ' .ph-x{',
      '  border:0 !important; background:transparent !important; color:#aaa !important;',
      '  font-size:18px !important; line-height:1 !important; cursor:pointer !important;',
      '  padding:4px 8px !important;',
      '}',
      '#' + ROOT_ID + ' .ph-x:hover{ color:#fff !important; }',
      '#' + ROOT_ID + ' .ph-grid{',
      '  display:grid !important; grid-template-columns:1fr 1fr !important; gap:8px !important;',
      '  padding:8px 10px 10px !important;',
      '}',
      '@media (max-width:560px){ #' + ROOT_ID + ' .ph-grid{ grid-template-columns:1fr !important; } }',
      '#' + ROOT_ID + ' a.ph-card{',
      '  display:block !important; text-decoration:none !important; color:#111 !important;',
      '  background:#ABF600 !important; border:2px solid #111 !important; border-radius:12px !important;',
      '  padding:10px 12px !important; box-shadow:2px 2px 0 #fff !important;',
      '  transition: transform .12s ease, box-shadow .12s ease !important;',
      '}',
      '#' + ROOT_ID + ' a.ph-card:hover{ transform: translate(-1px,-1px) !important; box-shadow:3px 3px 0 #fff !important; }',
      '#' + ROOT_ID + ' a.ph-card.ph-shop{ background:#fff !important; }',
      '#' + ROOT_ID + ' .ph-kicker{',
      '  display:block !important; font-size:10px !important; font-weight:800 !important;',
      '  letter-spacing:.06em !important; text-transform:uppercase !important; opacity:.75 !important;',
      '  margin-bottom:3px !important;',
      '}',
      '#' + ROOT_ID + ' .ph-title{',
      '  display:block !important; font-size:13px !important; font-weight:800 !important;',
      '  line-height:1.25 !important; letter-spacing:-.01em !important;',
      '}',
      '#' + ROOT_ID + ' .ph-sub{',
      '  display:block !important; font-size:11px !important; font-weight:600 !important;',
      '  margin-top:3px !important; opacity:.8 !important;',
      '}',
      '#' + ROOT_ID + ' .ph-pill{',
      '  pointer-events:auto !important; position:fixed !important; right:12px !important; bottom:12px !important;',
      '  z-index:2147483001 !important; border:2px solid #111 !important; border-radius:999px !important;',
      '  background:#ABF600 !important; color:#111 !important; font-weight:900 !important; font-size:12px !important;',
      '  padding:10px 14px !important; box-shadow:3px 3px 0 #111 !important; cursor:pointer !important;',
      '  font-family:system-ui,-apple-system,sans-serif !important;',
      '}',
      'body{ padding-bottom: max(12px, env(safe-area-inset-bottom)) !important; }',
    ].join('\n');
    (document.head || document.documentElement).appendChild(s);
  }

  function buildFull() {
    var root = document.createElement('div');
    root.id = ROOT_ID;
    root.setAttribute('data-ph-locked', '1');
    root.innerHTML =
      '<div class="ph-shell" role="complementary" aria-label="PH-CHAIN promo">' +
        '<div class="ph-top">' +
          '<span class="ph-badge">● LIVE · PH NETWORK</span>' +
          '<button type="button" class="ph-x" aria-label="Sembunyikan sebentar" title="Cuma ilang 45 detik">×</button>' +
        '</div>' +
        '<div class="ph-grid">' +
          '<a class="ph-card" href="' + HUB + '" target="_blank" rel="noopener noreferrer">' +
            '<span class="ph-kicker">PH-Chain</span>' +
            '<span class="ph-title">Coding apapun · budget berapa pun</span>' +
            '<span class="ph-sub">Custom app, automation, install — order di PH-Chain →</span>' +
          '</a>' +
          '<a class="ph-card ph-shop" href="' + SHOP + '" target="_blank" rel="noopener noreferrer">' +
            '<span class="ph-kicker">PH-Shop</span>' +
            '<span class="ph-title">Belanja barang eksklusif cuma di sini</span>' +
            '<span class="ph-sub">Merch & produk PH — jangan cari di tempat lain →</span>' +
          '</a>' +
        '</div>' +
      '</div>';
    root.querySelector('.ph-x').addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      collapseTemp();
    });
    return root;
  }

  function buildPill() {
    var b = document.createElement('button');
    b.id = ROOT_ID;
    b.type = 'button';
    b.className = 'ph-pill';
    b.setAttribute('data-ph-locked', '1');
    b.textContent = 'PH · buka promo';
    b.addEventListener('click', function () {
      try { localStorage.removeItem(COLLAPSE_KEY); } catch (e) {}
      paint();
    });
    return b;
  }

  function paint() {
    ensureStyle();
    var old = document.getElementById(ROOT_ID);
    if (old && old.parentNode) old.parentNode.removeChild(old);
    var node = isCollapsed() ? buildPill() : buildFull();
    (document.body || document.documentElement).appendChild(node);
  }

  function guardRemovals() {
    var obs = new MutationObserver(function () {
      if (!document.getElementById(ROOT_ID) || !document.getElementById(STYLE_ID)) {
        paint();
      }
    });
    obs.observe(document.documentElement, { childList: true, subtree: true });
    setInterval(function () {
      if (!document.getElementById(ROOT_ID) || !document.getElementById(STYLE_ID)) paint();
    }, 1200);
  }

  function boot() {
    paint();
    guardRemovals();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
