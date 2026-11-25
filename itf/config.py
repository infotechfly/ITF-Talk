"""Settings shared by the whole app."""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LANGS = {'en': 'English', 'hi': 'Hindi', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'ar': 'Arabic', 'bn': 'Bengali', 'ta': 'Tamil',
         'te': 'Telugu', 'mr': 'Marathi', 'gu': 'Gujarati', 'pa': 'Punjabi', 'ur': 'Urdu', 'kn': 'Kannada', 'ml': 'Malayalam',
         'zh-CN': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean', 'ru': 'Russian', 'pt': 'Portuguese', 'it': 'Italian', 'tr': 'Turkish', 'id': 'Indonesian'}

MAX_GROUP = 50          # people in a group room (1-to-1 rooms always hold 2)
DATA_TTL = 12 * 3600    # safety net: anything idle this long is wiped by the database itself
PRESENCE_TTL = 90       # seconds without a heartbeat before a tab counts as closed
HISTORY = 80            # messages replayed to someone who picks a language
KEEP_MSGS = 500         # messages kept per room
MAX_BODY = 16 * 1024    # largest request body accepted
