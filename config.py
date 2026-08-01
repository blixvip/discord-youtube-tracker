import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv(encoding='utf-8-sig')

def get_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with whitespace stripping and validation."""
    value = os.getenv(key, default)
    if value is not None:
        value = value.strip()
        # Return None if the value is empty after stripping
        if value == '':
            return None
    return value

# Discord Bot Configuration
DISCORD_TOKEN = get_env_var('DISCORD_TOKEN')
DISCORD_PREFIX = '!'

# Reddit API Configuration
REDDIT_CLIENT_ID = get_env_var('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = get_env_var('REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = 'MemeFetcherBot/1.0'

# Bot Settings
MAX_MEMES_PER_REQUEST = 5
YOUTUBE_POLL_MINUTES = 5
SUBSCRIPTIONS_FILE = get_env_var(
    'SUBSCRIPTIONS_FILE',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'subscriptions.json'),
)
SUBSCRIPTIONS_SEED_B64 = get_env_var('SUBSCRIPTIONS_SEED_B64')
DEFAULT_SUBREDDITS = ['memes', 'dankmemes', 'funny', 'me_irl', 'wholesomememes']
SUPPORTED_IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.gif']

# Image detection patterns for more robust detection
IMAGE_URL_PATTERNS = [
    # Standard image extensions
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff',
    # Common image hosting domains
    'imgur.com', 'i.imgur.com', 'media.giphy.com', 'gfycat.com',
    'reddit.com/media', 'preview.redd.it', 'i.redd.it',
    # Generic image patterns
    '/image/', '/img/', '/media/'
]
