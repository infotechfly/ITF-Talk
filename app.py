"""ITF Talk - private translated chat rooms by Info Tech Fly.

Vercel finds the `app` object in this file. Locally:  python app.py
"""
import os

from itf import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'\n ITF Talk running on http://localhost:{port}\n')
    app.run(host='0.0.0.0', port=port, threaded=True)
