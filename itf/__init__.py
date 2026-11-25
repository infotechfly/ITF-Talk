"""ITF Talk - private translated chat rooms by Info Tech Fly."""
import logging, os

from flask import Flask, jsonify, redirect, request

from .config import BASE, MAX_BODY
from .routes import api_bp, pages


def create_app():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    app = Flask(__name__, template_folder=os.path.join(BASE, 'templates'),
                static_folder=os.path.join(BASE, 'public', 'static'), static_url_path='/static')
    app.config.update(MAX_CONTENT_LENGTH=MAX_BODY, JSON_AS_ASCII=False, TEMPLATES_AUTO_RELOAD=False)
    app.register_blueprint(pages)
    app.register_blueprint(api_bp)

    @app.after_request
    def headers(r):
        r.headers.setdefault('X-Content-Type-Options', 'nosniff')
        r.headers.setdefault('X-Frame-Options', 'DENY')
        r.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        if request.path.startswith('/api/'): r.headers['Cache-Control'] = 'no-store'
        if request.path.startswith('/r/'): r.headers['X-Robots-Tag'] = 'noindex, nofollow'   # private room links
        return r

    @app.errorhandler(404)
    def not_found(e): return (jsonify(error='Not found'), 404) if request.path.startswith('/api/') else redirect('/')

    @app.errorhandler(413)
    def too_big(e): return jsonify(error='Request too large'), 413

    @app.errorhandler(500)
    def broken(e): return jsonify(error='Something went wrong'), 500

    return app
