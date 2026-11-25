document.addEventListener('DOMContentLoaded', () => {
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  $('#yr').textContent = new Date().getFullYear();
  const tabs = $$('.lw-tabs button');
  tabs.forEach(b => (b.onclick = () => {
    tabs.forEach(x => { x.classList.toggle('on', x === b); x.setAttribute('aria-selected', x === b); });
    $$('.lw-pane').forEach(p => (p.hidden = p.dataset.pane !== b.dataset.tab));
    const l = $('.cbot-log'); if (b.dataset.tab === 'bot' && l) l.scrollTop = l.scrollHeight;
  }));
  const phoneOk = p => { const n = p.replace(/\D/g, '').length; return n >= 7 && n <= 15; };
  const form = $('form.lead'), btns = $$('button[data-via]', form); let busy = false, opened = Date.now();
  form.elements.phone.addEventListener('input', e => { e.target.value = e.target.value.replace(/[^0-9+\s()\-]/g, ''); });
  form.addEventListener('submit', e => e.preventDefault());
  const send = async (via, btn) => {
    if (busy) return;
    const d = Object.fromEntries(new FormData(form)); if (d.website) return;
    const name = (d.name || '').trim(), phone = (d.phone || '').trim(), email = (d.email || '').trim(), message = (d.message || '').trim();
    if (name.length < 2) return toast('Please enter your full name.', 1);
    if (!phoneOk(phone)) return toast('Please enter a valid phone number.', 1);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return toast('Please enter a valid email.', 1);
    if (message.length < 5) return toast('Please write a short message.', 1);
    const api = typeof CFG !== 'undefined' ? CFG.SHEET_API : '';
    if (!api.startsWith('http')) return toast('Form is not connected yet. Add the Web App URL in static/js/config.js.', 1);
    const wa = via === 'whatsapp', num = ((typeof CFG !== 'undefined' && CFG.WHATSAPP) || '917225880469').replace(/\D/g, '');
    const url = `https://wa.me/${num}?text=` + encodeURIComponent(`Hello Info Tech Fly,\n\n*Name:* ${name}\n*Phone:* ${phone}\n*Email:* ${email}\n\n*Message:*\n${message}`);
    const win = wa ? window.open('', '_blank') : null;           /* open inside the click so browsers do not block it */
    busy = true; btns.forEach(b => (b.disabled = true)); const old = btn.innerHTML; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sending...';
    const ctrl = new AbortController(), timer = setTimeout(() => ctrl.abort(), wa ? 10000 : 20000); let saved = true, err = '';
    try {
      const res = await fetch(api, { method: 'POST', signal: ctrl.signal, body: new URLSearchParams({ name, phone, email, message, via: wa ? 'WhatsApp' : 'Team', website: '', t: Date.now() - opened }) });
      const o = await res.json(); if (o.status !== 'success') throw new Error(o.message || 'Could not send. Please try again.');
    } catch (x) { saved = false; err = x.name === 'AbortError' || x instanceof TypeError ? 'Could not send. Please check your connection and try again.' : x.message; }
    clearTimeout(timer);
    if (wa) { if (win && !win.closed) win.location.href = url; else location.href = url; }
    if (saved || wa) { form.reset(); opened = Date.now(); }
    if (saved) toast(wa ? 'Thank you! Opening WhatsApp...' : 'Thank you! Your message was sent to our team.');
    else toast(wa ? 'WhatsApp opened, but we could not save to our sheet. ' + err : err, 1);
    busy = false; btns.forEach(b => (b.disabled = false)); btn.innerHTML = old;
  };
  btns.forEach(b => b.addEventListener('click', () => send(b.dataset.via, b)));
});
