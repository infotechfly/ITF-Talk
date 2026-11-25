"""HTTP layer: the three pages (as before) plus a small JSON API, like the Vercel Flask starter."""
import time

from flask import Blueprint, jsonify, render_template, request

from . import realtime as rt
from .config import LANGS
from .store import StoreError, store

pages = Blueprint('pages', __name__)
api_bp = Blueprint('api', __name__, url_prefix='/api')


# ---------- pages ----------
@pages.get('/')
def index(): return render_template('index.html', langs=LANGS, token='')

@pages.get('/r/<token>')
def room_page(token): return render_template('index.html', langs=LANGS, token=token if rt.TOKEN_RE.fullmatch(token) else '')

@pages.get('/contact')
def contact(): return render_template('contact.html')


# ---------- api ----------
def client_ip():
    return (request.headers.get('x-real-ip') or request.headers.get('x-forwarded-for', '').split(',')[0].strip() or request.remote_addr or '?')[:64]

@api_bp.get('/health')
def health():
    try: store.run(('PING',)); ok = True
    except StoreError: ok = False
    return jsonify(ok=ok, store=store.kind, time=int(time.time())), (200 if ok else 503)

@api_bp.get('/room/<token>')
def room_info(token):
    r = rt.load_room(token)
    if r: rt.reap(token); r = rt.load_room(token)
    if not r: return jsonify(ok=False)
    return jsonify(ok=True, name=r['name'], kind=r['kind'], full=store.run(('LLEN', rt.K('rm', token))) >= rt.cap(r))

@api_bp.post('/rt')
def rt_event():
    """Browser -> server event. The reply carries the events waiting for that person."""
    b = request.get_json(silent=True) or {}
    ev = b.get('ev')
    if ev not in rt.HANDLERS: return jsonify(events=[]), 400
    user = rt.auth(b.get('uid'), b.get('key')) if b.get('uid') else None
    if b.get('uid') and not user: return jsonify(gone=True), 401
    return jsonify(events=rt.dispatch(ev, b.get('data'), user, client_ip()))

@api_bp.post('/rt/poll')
def rt_poll():
    b = request.get_json(silent=True) or {}
    user = rt.auth(b.get('uid'), b.get('key'))
    if not user: return jsonify(gone=True), 401
    return jsonify(events=rt.poll(user))

@api_bp.post('/rt/bye')
def rt_bye():
    """Sent by the browser (sendBeacon) when the tab closes or refreshes."""
    b = request.get_json(silent=True, force=True) or {}
    user = rt.auth(b.get('uid'), b.get('key'))
    if user: rt.bye(user)
    return '', 204


@api_bp.errorhandler(StoreError)
def store_down(e): return jsonify(error='Service is busy. Please try again.'), 503
