"""ITF Talk chat logic.

Same rules as before: users, rooms and messages are private and short-lived; the admin leaving
closes the room; closing or refreshing a tab removes the user. State lives in the store
(Redis on Vercel), and events reach each person through their own queue, which the browser
drains with a quick poll (see static/js/rt.js).

Keys (all prefixed itf:):  u:<uid> user json   s:<uid> presence   q:<uid> event queue
                           r:<tok> room json   rm:<tok> member ids   m:<tok> messages   t:<tok> translations
"""
import hashlib, hmac, json, logging, re, secrets, time

from .config import DATA_TTL, HISTORY, KEEP_MSGS, LANGS, MAX_GROUP, PRESENCE_TTL
from .store import store
from .translate import tr_many

log = logging.getLogger('itf.rt')

TOKEN_RE, UID_RE = re.compile(r'[0-9a-f]{32}'), re.compile(r'u_[0-9a-f]{12}')
sha = lambda s: hashlib.sha256(s.encode('utf8')).hexdigest()
dumps = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':'))
K = lambda *p: 'itf:' + ':'.join(map(str, p))
run = lambda *c: store.run(c)
pipe = lambda cmds: store.pipe(cmds) if cmds else []


def clean(s, n, keep=False):
    s = str(s or '').strip()
    return s[:n] if keep else ' '.join(s.split())[:n]


# ---------- storage helpers ----------
def load_user(uid):
    v = run('GET', K('u', uid)); return json.loads(v) if v else None
def save_user(u, new=False):
    run('SET', K('u', u['id']), dumps(u), 'EX', DATA_TTL, *(() if new else ('XX',)))
def load_room(tok):
    if not isinstance(tok, str) or not TOKEN_RE.fullmatch(tok): return None
    v = run('GET', K('r', tok)); return json.loads(v) if v else None
def cap(r): return 2 if r['kind'] == 'one' else MAX_GROUP

def members(r):
    ids = run('LRANGE', K('rm', r['token']), 0, -1)
    us = run('MGET', *[K('u', i) for i in ids]) if ids else []
    out = [dict(id=u['id'], name=u['name'], tag=u['tag'], lang=u['lang'], admin=u['id'] == r['admin']) for u in map(json.loads, filter(None, us))]
    return ids, out

def pay(m, text): return dict(id=m['id'], uid=m['uid'], name=m['name'], tag=m['tag'], x=m['x'], text=text, ts=m['ts'])


class Ctx:
    """One request. Events are batched and sent in a single round trip at the end."""
    def __init__(self, user=None):
        self.u, self.cmds, self.direct = user, [], []

    def to_user(self, uid, ev, data):
        self.cmds += [['RPUSH', K('q', uid), dumps([ev, data])], ['EXPIRE', K('q', uid), 600]]

    def me(self, ev, data=None):
        if self.u: self.to_user(self.u['id'], ev, data)
        else: self.direct.append([ev, data])

    def to_room(self, tok, ev, data, ids=None):
        for i in (run('LRANGE', K('rm', tok), 0, -1) if ids is None else ids): self.to_user(i, ev, data)

    def flush(self, drain=False):
        """Send batched events; with drain=True also return this user's pending events."""
        cmds = list(self.cmds)
        if drain and self.u: cmds.append(['LPOP', K('q', self.u['id']), 200])
        res = pipe(cmds); self.cmds = []
        out = [json.loads(x) for x in (res[-1] if drain and self.u and res else None) or []]
        return out + self.direct


# ---------- room lifecycle ----------
def push_members(c, r, ids=None, ms=None):
    if ms is None: ids, ms = members(r)
    c.to_room(r['token'], 'members', ms, ids)

def close_room(c, r, by):
    tok = r['token']; ids = run('LRANGE', K('rm', tok), 0, -1)
    c.to_room(tok, 'closed', {'by': by}, ids)
    for raw in run('MGET', *[K('u', i) for i in ids]) if ids else []:
        if raw:
            u = json.loads(raw); u['room'] = u['lang'] = None; save_user(u)
    pipe([['DEL', K(p, tok)] for p in ('r', 'rm', 'm', 't')])

def exit_room(c, u):
    r = load_room(u.get('room'))
    if not r:
        u['room'] = u['lang'] = None; save_user(u); return
    if r['admin'] == u['id']: return close_room(c, r, u['name'])    # admin leaves -> room and chat are deleted
    run('LREM', K('rm', r['token']), 0, u['id'])
    u['room'] = u['lang'] = None; save_user(u)
    ids, ms = members(r)
    c.to_room(r['token'], 'sys', u['name'] + ' left', ids); push_members(c, r, ids, ms)

def drop(c, uid, tok=None):
    """A tab went away: same as the old socket 'disconnect'."""
    u = load_user(uid) or dict(id=uid, name='Someone', room=tok, lang=None)
    if u.get('room'): exit_room(c, u)
    c.flush(); pipe([['DEL', K(p, uid)] for p in ('u', 's', 'q')])

def reap(tok):
    """Remove people whose tab stopped answering. At most one sweep per room every 5 seconds."""
    if not run('SET', K('reap', tok), 1, 'EX', 5, 'NX'): return
    ids = run('LRANGE', K('rm', tok), 0, -1)
    if not ids: return
    alive = pipe([['EXISTS', K('s', i)] for i in ids])
    dead = [i for i, a in zip(ids, alive) if not a]
    if dead:
        c = Ctx()
        for i in dead: drop(c, i, tok)
        c.flush()
    pipe([['EXPIRE', K(p, tok), DATA_TTL] for p in ('r', 'rm', 'm', 't')])

def enter(c, r):
    u, tok = c.u, r['token']
    n = run('RPUSH', K('rm', tok), u['id'])
    if n > cap(r):                                                  # atomic: two people can never take the last seat
        run('LREM', K('rm', tok), 1, u['id']); return c.me('err', 'This room is full.')
    run('EXPIRE', K('rm', tok), DATA_TTL)
    u['room'] = tok; u['lang'] = None; save_user(u)
    ids, ms = members(r)
    c.me('joined', {'room': {'token': tok, 'name': r['name'], 'kind': r['kind']}, 'admin': r['admin'] == u['id'], 'members': ms})
    c.to_room(tok, 'sys', u['name'] + ' joined', ids); push_members(c, r, ids, ms)


# ---------- events from the browser ----------
def h_hello(c, d):
    n = clean(d.get('name'), 30)
    if c.u: return
    if len(n) < 2: return c.me('err', 'Enter your name (2 or more characters).')
    uid, key = 'u_' + sha(secrets.token_hex(16) + n)[:12], secrets.token_urlsafe(24)
    c.u = dict(id=uid, name=n, tag=uid[-4:], kh=sha(key), lang=None, room=None, t=time.time())
    save_user(c.u, new=True); run('SET', K('s', uid), 1, 'EX', PRESENCE_TTL)
    c.me('me', {'id': uid, 'name': n, 'tag': uid[-4:], 'key': key})

def h_create(c, d):
    u, n = c.u, clean(d.get('name'), 40)
    if not u or u['room']: return
    if len(n) < 2: return c.me('err', 'Enter a room name (2 or more characters).')
    tok = sha(secrets.token_hex(32) + n + u['id'])[:32]
    r = dict(token=tok, name=n, kind='one' if d.get('kind') == 'one' else 'group', admin=u['id'], created=time.time())
    run('SET', K('r', tok), dumps(r), 'EX', DATA_TTL); enter(c, r)

def h_enter(c, d):
    u, tok = c.u, d.get('token')
    if not u or u['room']: return
    if not load_room(tok): return c.me('err', 'This room is closed or does not exist.')
    reap(tok); r = load_room(tok)                                   # clear ghosts first so a dead tab never blocks a seat
    if not r: return c.me('err', 'This room is closed or does not exist.')
    enter(c, r)

def h_lang(c, d):
    u, l = c.u, d.get('lang')
    if not u or not u['room'] or l not in LANGS: return
    r = load_room(u['room'])
    if not r: return
    u['lang'] = l; save_user(u); tok = r['token']
    msgs = [json.loads(x) for x in run('LRANGE', K('m', tok), -HISTORY, -1)]
    raw = run('HGETALL', K('t', tok)); cache = dict(zip(raw[::2], raw[1::2]))
    need = [m for m in msgs if m['uid'] != u['id'] and m['l'] != l and '%s|%s' % (m['id'], l) not in cache]
    for m, t in zip(need, tr_many([(m['x'], m['l'], l) for m in need])):
        if t is not None: cache['%s|%s' % (m['id'], l)] = t
    fresh = [x for m in need if '%s|%s' % (m['id'], l) in cache for x in ('%s|%s' % (m['id'], l), cache['%s|%s' % (m['id'], l)])]
    if fresh: run('HSET', K('t', tok), *fresh); run('EXPIRE', K('t', tok), DATA_TTL)
    out = [pay(m, m['x'] if m['uid'] == u['id'] or m['l'] == l else cache.get('%s|%s' % (m['id'], l), m['x'])) for m in msgs]
    c.me('langok', {'lang': l}); c.me('history', out); push_members(c, r)

def h_msg(c, d):
    u, t = c.u, clean(d.get('text'), 1000, True)
    r = load_room(u['room']) if u and u['room'] else None
    if not r or not u['lang'] or not t: return
    n = run('INCR', K('rl', u['id']))
    if n == 1: run('EXPIRE', K('rl', u['id']), 10)
    if n > 20: return c.me('err', 'You are sending messages too fast. Please slow down.')
    tok = r['token']; m = dict(id=secrets.token_hex(4), uid=u['id'], name=u['name'], tag=u['tag'], x=t, l=u['lang'], ts=time.time())
    ids, ms = members(r)
    mem = [(i, x) for i, x in ((i, next((y for y in ms if y['id'] == i), None)) for i in ids) if x and x['lang']]
    langs = sorted({x['lang'] for _, x in mem if x['lang'] != m['l']})
    got = {l: v for l, v in zip(langs, tr_many([(t, m['l'], l) for l in langs])) if v is not None}
    if not run('EXISTS', K('r', tok)): return                       # room was closed while translating
    cmds = [['RPUSH', K('m', tok), dumps(m)], ['LTRIM', K('m', tok), -KEEP_MSGS, -1], ['EXPIRE', K('m', tok), DATA_TTL]]
    if got: cmds += [['HSET', K('t', tok)] + [x for l, v in got.items() for x in ('%s|%s' % (m['id'], l), v)], ['EXPIRE', K('t', tok), DATA_TTL]]
    pipe(cmds)
    for i, x in mem: c.to_user(i, 'msg', pay(m, m['x'] if x['lang'] == m['l'] or i == u['id'] else got.get(x['lang'], m['x'])))
    if len(got) < len(langs): c.me('err', 'Translation failed for some people. Please try again in a moment.')

def h_leave(c, d):
    if c.u and c.u['room']: exit_room(c, c.u); c.me('left')

HANDLERS = {'hello': h_hello, 'create': h_create, 'enter': h_enter, 'lang': h_lang, 'msg': h_msg, 'leave': h_leave}


# ---------- entry points used by the HTTP layer ----------
def auth(uid, key):
    if not isinstance(uid, str) or not isinstance(key, str) or not UID_RE.fullmatch(uid): return None
    u = load_user(uid)
    return u if u and hmac.compare_digest(u.get('kh', ''), sha(key)) else None

def dispatch(ev, data, user, ip=''):
    """Handle one event from the browser; returns the events to send back right away."""
    c = Ctx(user)
    if not user:
        n = run('INCR', K('rl', 'ip', ip))
        if n == 1: run('EXPIRE', K('rl', 'ip', ip), 60)
        if n > 30: return [['err', 'Too many requests. Please wait a minute and try again.']]
    else:
        c.cmds.append(['SET', K('s', user['id']), 1, 'EX', PRESENCE_TTL])
    try:
        HANDLERS[ev](c, data if isinstance(data, dict) else {})
    except Exception:
        log.exception('event %s failed', ev); c.me('err', 'Something went wrong. Please try again.')
    return c.flush(drain=True)

def poll(user):
    """Heartbeat + collect events. Also removes anyone in the room whose tab has gone quiet."""
    uid = user['id']; tok = user.get('room')
    res = pipe([['SET', K('s', uid), 1, 'EX', PRESENCE_TTL], ['EXPIRE', K('u', uid), DATA_TTL], ['LPOP', K('q', uid), 200]])
    if tok: reap(tok)
    return [json.loads(x) for x in res[-1] or []]

def bye(user):
    drop(Ctx(user), user['id'])
