(() => {
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const S = { me: null, room: null, admin: false, lang: null, members: [] };
  const TOKEN = document.body.dataset.token;
  const sock = io();
  const show = id => $$('.screen').forEach(e => (e.hidden = e.id !== id));
  const opts = Object.entries(window.LANGS).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join('');
  $('#gl').innerHTML = $('#ml').innerHTML = opts;
  const KIND = { one: '1 to 1 chat', group: 'Group chat' };
  let invite = null, kind = 'group', wasIn = false;

  /* invite link: /r/<hash> */
  (async () => {
    if (!TOKEN) return;
    let r = { ok: false };
    try { r = await (await fetch('/api/room/' + TOKEN)).json(); } catch (e) {}
    const n = $('#invite'); n.hidden = false;
    if (r.ok && !r.full) { invite = r; n.innerHTML = `You are invited to <b>${esc(r.name)}</b> (${KIND[r.kind]}). Enter your name to join.`; $('#nt').textContent = 'Join this room'; $('#go').innerHTML = '<i class="fa-solid fa-arrow-right-to-bracket"></i> Join room'; }
    else n.textContent = r.ok ? 'This room is full. You can start your own room instead.' : 'This room is closed or does not exist. You can start a new one instead.';
  })();

  $('#nf').onsubmit = e => { e.preventDefault(); const n = $('#nm').value.trim(); if (n.length < 2) return toast('Enter your name (2 or more characters).', 1); sock.emit('hello', { name: n }); };
  sock.on('me', m => { S.me = m; wasIn = true; $('#hi').textContent = m.name; if (invite) sock.emit('enter', { token: TOKEN }); else show('choose'); });
  $$('[data-kind]').forEach(b => (b.onclick = () => { kind = b.dataset.kind; $('#mt').textContent = 'Name your ' + (kind === 'one' ? '1 to 1' : 'group') + ' room'; show('make'); $('#rm').focus(); }));
  $('#mb').onclick = () => show('choose');
  $('#mf').onsubmit = e => { e.preventDefault(); sock.emit('create', { kind, name: $('#rm').value }); };

  sock.on('joined', d => {
    S.room = d.room; S.admin = d.admin; S.lang = null; invite = null;
    $('#rn').textContent = d.room.name; $('#rk').textContent = KIND[d.room.kind] + (d.admin ? ' · you are the admin' : '');
    $('#link').value = location.origin + '/r/' + d.room.token;
    $('#leave').innerHTML = d.admin ? '<i class="fa-solid fa-power-off"></i> Close room' : '<i class="fa-solid fa-right-from-bracket"></i> Leave';
    $('#msgs').innerHTML = ''; people(d.members); $('#rm').value = ''; show('room'); $('#gate').hidden = false;
  });
  const people = l => {
    S.members = l; $('#pc').textContent = l.length + (S.room.kind === 'one' ? '/2' : '');
    $('#people').innerHTML = `<h4>People (${l.length}${S.room.kind === 'one' ? ' of 2' : ''})</h4>` + l.map(m => `<div class="pp"><span class="av">${esc(m.name[0]).toUpperCase()}</span><div><b>${esc(m.name)}</b> <i>#${m.tag}</i>${m.admin ? ' <span class="adm">admin</span>' : ''}<small>${m.lang ? esc(window.LANGS[m.lang]) : 'choosing language…'}</small></div></div>`).join('');
  };
  sock.on('members', l => S.room && people(l));

  /* language comes AFTER entering the room */
  $('#gb').onclick = () => sock.emit('lang', { lang: $('#gl').value });
  $('#ml').onchange = () => sock.emit('lang', { lang: $('#ml').value });
  sock.on('langok', d => { S.lang = d.lang; $('#ml').value = d.lang; $('#gate').hidden = true; $('#ct').focus(); });

  const add = el => { const m = $('#msgs'); m.append(el); m.scrollTop = m.scrollHeight; };
  const bub = m => {
    const mine = m.uid === S.me.id, d = document.createElement('div'), tr = !mine && m.text !== m.x;
    d.className = 'b' + (mine ? ' o' : '') + (tr ? ' t' : '');
    d.innerHTML = (mine ? '' : `<span class="who">${esc(m.name)} <i>#${m.tag}</i></span>`) + `<p>${esc(m.text)}</p>` + (tr ? `<em class="orig">Original: ${esc(m.x)}</em>` : '') + `<small>${new Date(m.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}${tr ? ' · tap for original' : ''}</small>`;
    if (tr) d.onclick = () => d.classList.toggle('show');
    add(d);
  };
  const sys = t => { const d = document.createElement('div'); d.className = 'sys'; d.textContent = t; add(d); };
  sock.on('history', l => { $('#msgs').innerHTML = ''; l.forEach(bub); });
  sock.on('msg', bub); sock.on('sys', t => S.lang && sys(t));
  $('#cf').onsubmit = e => { e.preventDefault(); const t = $('#ct').value.trim(); if (t) { sock.emit('msg', { text: t }); $('#ct').value = ''; } };
  $$('.soonb').forEach(b => (b.onclick = () => toast(b.dataset.s + ' is coming soon.')));

  /* share, leave, close */
  $('#cp').onclick = async () => { try { await navigator.clipboard.writeText($('#link').value); } catch (e) { $('#link').select(); document.execCommand('copy'); } toast('Link copied. Send it to the person you want to chat with.'); };
  if (navigator.share) { $('#sh').hidden = false; $('#sh').onclick = () => navigator.share({ title: 'Join my ITF Talk room', url: $('#link').value }).catch(() => {}); }
  $('#pb').onclick = () => $('#rb').classList.toggle('pop');
  $('#leave').onclick = () => { if (S.admin && !confirm('Closing the room deletes it and the whole chat for everyone. Close it?')) return; sock.emit('leave'); };
  const out = msg => { S.room = null; S.admin = false; $('#gate').hidden = true; show('choose'); if (msg) toast(msg); };
  sock.on('left', () => out()); sock.on('closed', d => out('The room was closed by ' + d.by + '. The chat is deleted.'));
  sock.on('err', m => { toast(m, 1); if (S.me && !S.room && !$('#name').hidden) { invite = null; show('choose'); } });
  addEventListener('beforeunload', e => { if (S.admin && S.room) { e.preventDefault(); e.returnValue = ''; } });

  $('#brand').onclick = e => { if (S.me && !confirm('Leaving this page removes you from the chat. Leave?')) e.preventDefault(); };

  /* a dropped connection removes the user on the server, so start fresh */
  sock.on('disconnect', () => { if (S.me) toast('Connection lost. You were removed from the room.', 1); });
  sock.on('connect', () => { if (wasIn && S.me) location.reload(); });
})();
