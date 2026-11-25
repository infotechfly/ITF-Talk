"""Translation: Google's public endpoint first, deep-translator as a fallback."""
import json, logging, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

try: from deep_translator import GoogleTranslator
except Exception: GoogleTranslator = None

log = logging.getLogger('itf.translate')


def tr(text, src, dst):
    """Translated text, or None if every provider failed (failures are never cached)."""
    if src == dst or not text.strip(): return text
    try:
        u = 'https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=%s&tl=%s&q=%s' % (src, dst, urllib.parse.quote(text))
        r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=8).read().decode('utf8'))
        out = ''.join(x[0] for x in r[0] if x[0])
        if out: return out
    except Exception as e: log.warning('translate error: %s', e)
    try:
        if GoogleTranslator: return GoogleTranslator(source=src, target=dst).translate(text)
    except Exception as e: log.warning('fallback translate error: %s', e)
    return None


def tr_many(jobs):
    """jobs = [(text, src, dst), ...] translated in parallel, results in the same order."""
    if not jobs: return []
    if len(jobs) == 1: return [tr(*jobs[0])]
    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as ex:
        return list(ex.map(lambda j: tr(*j), jobs))
