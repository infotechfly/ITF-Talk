"""Tiny Redis-style store.

Vercel runs every request in a fresh, short-lived function, so chat state cannot live in
Python memory. On Vercel (or anywhere) set UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN
(the Vercel Marketplace Upstash integration sets KV_REST_API_URL / KV_REST_API_TOKEN, also
supported) and state goes to Upstash Redis over HTTPS. With nothing set, an in-process store
with the same commands is used, which is perfect for `python app.py` on your own machine.
"""
import json, logging, os, threading, time, urllib.request

log = logging.getLogger('itf.store')


class StoreError(RuntimeError):
    pass


class Mem:
    """In-process store speaking the small Redis subset ITF Talk needs. One process only."""
    kind = 'memory'

    def __init__(self):
        self.d, self.exp, self.lock = {}, {}, threading.RLock()

    def _live(self, k):
        e = self.exp.get(k)
        if e is not None and e <= time.time():
            self.d.pop(k, None); self.exp.pop(k, None)
        return k in self.d

    def _gone(self, k):                      # Redis removes a list or hash once it is empty
        if k in self.d and not self.d[k]:
            self.d.pop(k); self.exp.pop(k, None)

    @staticmethod
    def _span(n, s, e):
        s, e = int(s), int(e)
        s = max(s + n if s < 0 else s, 0); e = e + n if e < 0 else e
        return s, e

    def run(self, cmd):
        op, *a = cmd
        fn = getattr(self, '_' + str(op).lower())
        with self.lock:
            return fn(*[str(x) for x in a])

    def pipe(self, cmds):
        return [self.run(c) for c in cmds]

    def _ping(self): return 'PONG'
    def _get(self, k): return self.d[k] if self._live(k) else None
    def _mget(self, *ks): return [self._get(k) for k in ks]
    def _exists(self, *ks): return sum(1 for k in ks if self._live(k))

    def _set(self, k, v, *o):
        o = [x.upper() for x in o]
        if 'NX' in o and self._live(k): return None
        if 'XX' in o and not self._live(k): return None
        self.d[k] = v; self.exp.pop(k, None)
        if 'EX' in o: self.exp[k] = time.time() + int(o[o.index('EX') + 1])
        return 'OK'

    def _del(self, *ks):
        n = 0
        for k in ks:
            if self._live(k): self.d.pop(k); self.exp.pop(k, None); n += 1
        return n

    def _expire(self, k, s, *o):
        if not self._live(k): return 0
        self.exp[k] = time.time() + int(s); return 1

    def _incr(self, k):
        n = int(self._get(k) or 0) + 1; self.d[k] = str(n)
        return n

    def _rpush(self, k, *vs):
        self._live(k); self.d.setdefault(k, []).extend(vs); return len(self.d[k])

    def _llen(self, k): return len(self.d[k]) if self._live(k) else 0

    def _lrange(self, k, s, e):
        if not self._live(k): return []
        s, e = self._span(len(self.d[k]), s, e); return self.d[k][s:e + 1]

    def _ltrim(self, k, s, e):
        if self._live(k):
            s, e = self._span(len(self.d[k]), s, e); self.d[k] = self.d[k][s:e + 1]; self._gone(k)
        return 'OK'

    def _lrem(self, k, count, v):
        if not self._live(k): return 0
        n, c, out = 0, int(count) or 10 ** 9, []
        for x in self.d[k]:
            if x == v and n < c: n += 1
            else: out.append(x)
        self.d[k] = out; self._gone(k); return n

    def _lpop(self, k, count=None):
        if not self._live(k): return None
        l = self.d[k]
        if count is None: v = l.pop(0)
        else: v = l[:int(count)]; del l[:int(count)]
        self._gone(k); return v

    def _hset(self, k, *kv):
        self._live(k); h = self.d.setdefault(k, {}); new = 0
        for f, v in zip(kv[::2], kv[1::2]):
            new += f not in h; h[f] = v
        return new

    def _hget(self, k, f): return self.d[k].get(f) if self._live(k) else None

    def _hgetall(self, k):
        if not self._live(k): return []
        return [x for f, v in self.d[k].items() for x in (f, v)]


class Upstash:
    """Upstash Redis over its REST API: plain HTTPS, so it works from serverless functions."""
    kind = 'upstash'

    def __init__(self, url, token):
        self.url = url.rstrip('/')
        self.h = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}

    def _post(self, path, body):
        req = urllib.request.Request(self.url + path, json.dumps(body).encode(), self.h, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=8) as r: return json.loads(r.read())
        except Exception as e:
            raise StoreError('store unreachable: %s' % e) from e

    @staticmethod
    def _val(o):
        if 'error' in o: raise StoreError(o['error'])
        return o.get('result')

    def run(self, cmd): return self._val(self._post('', [str(x) for x in cmd]))

    def pipe(self, cmds):
        if not cmds: return []
        return [self._val(o) for o in self._post('/pipeline', [[str(x) for x in c] for c in cmds])]


def make_store():
    url = os.environ.get('UPSTASH_REDIS_REST_URL') or os.environ.get('KV_REST_API_URL')
    tok = os.environ.get('UPSTASH_REDIS_REST_TOKEN') or os.environ.get('KV_REST_API_TOKEN')
    if url and tok: return Upstash(url, tok)
    if os.environ.get('VERCEL'):
        log.warning('No Redis configured on Vercel: chats will break across function instances. '
                    'Add the Upstash Redis integration (see README).')
    return Mem()


store = make_store()
