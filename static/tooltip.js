/* Tooltip implementation using position:fixed to escape overflow-hidden/auto containers */
(function () {
  var tip = document.createElement('div');
  tip.setAttribute('aria-hidden', 'true');
  tip.style.cssText =
    'position:fixed;z-index:9999;pointer-events:none;opacity:0;transition:opacity 0.15s ease;' +
    'font-size:11px;font-weight:400;line-height:1.45;white-space:normal;max-width:240px;' +
    'padding:7px 11px;border-radius:5px;box-shadow:0 3px 10px rgba(0,0,0,0.2);color:#f2f2f7;';
  document.body.appendChild(tip);

  function updateColors() {
    var dark = document.documentElement.classList.contains('dark');
    tip.style.background = dark ? '#3a3a3c' : '#1c1c1e';
    tip.style.boxShadow = dark ? '0 3px 10px rgba(0,0,0,0.5)' : '0 3px 10px rgba(0,0,0,0.2)';
  }

  var current = null;

  function show(el) {
    current = el;
    tip.textContent = el.dataset.tooltip;
    updateColors();
    reposition(el);
    tip.style.opacity = '1';
  }

  function hide() {
    current = null;
    tip.style.opacity = '0';
  }

  function reposition(el) {
    var r = el.getBoundingClientRect();
    var tw = tip.offsetWidth || 200;
    var th = tip.offsetHeight || 30;
    var left = r.left + r.width / 2 - tw / 2;
    var top = r.top - th - 10;
    left = Math.max(8, Math.min(left, window.innerWidth - tw - 8));
    if (top < 8) top = r.bottom + 10;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }

  document.addEventListener('mouseover', function (e) {
    var el = e.target.closest('[data-tooltip]');
    if (el) show(el);
    else hide();
  });

  document.addEventListener('scroll', function () {
    if (current) reposition(current);
  }, true);

  document.addEventListener('mouseleave', function () { hide(); }, true);
}());
