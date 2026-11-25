/* ITF Talk realtime client.
   Offers the same two calls the chat screen already uses (on / emit) but carries them over
   plain HTTPS requests, so the app runs on Vercel serverless where WebSockets are not available.
   Your own actions get an instant reply; other people's messages arrive within about a second. */
(() => {
  'use strict';
  const FAST = 1000, SLOW = 15000;       // poll gap while the tab is visible / hidden (ms)

  window.io = () => {
    const H = {};
    let uid = null, key = null, timer = 0, dead = false;

    const fire = (ev, d) => (H[ev] || []).forEach(f => { try { f(d); } catch (e) { console.error(e); } });
    const post = async (path, body) => {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (r.status === 401) throw 'gone';
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    };
    const take = o => (o.events || []).forEach(([ev, d]) => {
      if (ev === 'me') { uid = d.id; key = d.key; d = { id: d.id, name: d.name, tag: d.tag }; schedule(); }
      fire(ev, d);
    });
    const lost = () => {                  // the server no longer knows us (tab was away too long): start fresh
      if (dead) return; dead = true; clearTimeout(timer);
      fire('disconnect'); setTimeout(() => fire('connect'), 1500);
    };
    const tick = async () => {
      if (dead || !uid) return;
      try { take(await post('/api/rt/poll', { uid, key })); } catch (e) { if (e === 'gone') return lost(); }
      schedule();
    };
    const schedule = () => { clearTimeout(timer); if (!dead && uid) timer = setTimeout(tick, document.hidden ? SLOW : FAST); };

    document.addEventListener('visibilitychange', () => { if (!document.hidden && uid && !dead) { clearTimeout(timer); tick(); } });
    /* closing or refreshing the tab removes the user, exactly like a dropped socket did */
    addEventListener('pagehide', () => {
      if (uid && !dead) navigator.sendBeacon('/api/rt/bye', new Blob([JSON.stringify({ uid, key })], { type: 'application/json' }));
    });

    const sock = {
      on(ev, f) { (H[ev] = H[ev] || []).push(f); return sock; },
      emit(ev, data) {
        if (dead) return;
        post('/api/rt', { ev, data: data || {}, uid, key }).then(take).catch(e => {
          if (e === 'gone') lost(); else fire('err', 'Network problem. Please check your connection and try again.');
        });
      },
    };
    setTimeout(() => fire('connect'), 0);
    return sock;
  };
})();
