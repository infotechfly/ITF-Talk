(() => {
  const r = document.documentElement;
  document.addEventListener('DOMContentLoaded', () => {
    const b = document.getElementById('theme');
    if (b) b.onclick = () => { const t = r.dataset.theme === 'dark' ? 'light' : 'dark'; r.dataset.theme = t; try { localStorage.setItem('theme', t); } catch (e) {} };
  });
  let h;
  window.toast = (m, bad) => { const t = document.getElementById('toast'); t.textContent = m; t.className = 'on' + (bad ? ' bad' : ''); clearTimeout(h); h = setTimeout(() => (t.className = ''), 3800); };
})();
