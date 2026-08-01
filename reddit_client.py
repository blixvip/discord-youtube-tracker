import asyncpraw
import random
import hashlib
import asyncio
from typing import List, Dict, Optional
from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, DEFAULT_SUBREDDITS, SUPPORTED_IMAGE_FORMATS, IMAGE_URL_PATTERNS

class RedditMemeFetcher:
    def __init__(self):
        """Initialize Reddit client for meme fetching."""
        reddit_options = {
            "client_id": REDDIT_CLIENT_ID,
            "user_agent": REDDIT_USER_AGENT,
        }
        reddit_options["client_secret"] = REDDIT_CLIENT_SECRET
        self.reddit = asyncpraw.Reddit(**reddit_options)
        # Track used posts to avoid duplicates within a session
        self._used_post_ids = set()
    
    async def close(self):
        """Properly close the Reddit client session."""
        if hasattr(self.reddit, 'close'):
            await self.reddit.close()
    
    def _get_post_id(self, post) -> str:
        """Generate a unique ID for a post to track duplicates."""
        title = getattr(post, 'title', '')
        url = getattr(post, 'url', '')
        author = str(getattr(post, 'author', ''))
        return hashlib.md5(f"{title}{url}{author}".encode()).hexdigest()
    
    def is_image_post(self, post) -> bool:
        """Check if a Reddit post contains an image using robust detection."""
        url = getattr(post, 'url', None)
        if not url or not isinstance(url, str):
            return False
        
        url_lower = url.lower()
        
        # Check for standard image extensions
        if any(url_lower.endswith(ext) for ext in SUPPORTED_IMAGE_FORMATS):
            return True
        
        # Check for image hosting domains and patterns
        if any(pattern in url_lower for pattern in IMAGE_URL_PATTERNS):
            return True
        
        # Check post hint attribute (Reddit's own classification)
        post_hint = getattr(post, 'post_hint', None)
        if post_hint in ['image', 'rich:video']:
            return True
        
        # Check if it's a gallery post
        if hasattr(post, 'is_gallery') and post.is_gallery:
            return True
        
        return False
    
    def _clean_input(self, text: Optional[str]) -> Optional[str]:
        """Clean and validate input text by stripping whitespace."""
        if text is None:
            return None
        cleaned = text.strip()
        return cleaned if cleaned else None
    
    async def _fetch_posts_with_cache_busting(self, subreddit, sort_method: str, limit: int, 
                                            time_filter: Optional[str] = None) -> List:
        """Fetch posts with cache busting strategies."""
        posts = []
        
        # Strategy 1: Use different limits to get different result sets
        base_limit = limit
        fetch_limit = base_limit + random.randint(5, 20)
        
        # Strategy 2: Add small random delays to avoid rate limiting while getting fresh data
        await asyncio.sleep(random.uniform(0.1, 0.5))
        
        try:
            if sort_method == 'top':
                posts_iter = subreddit.top(time_filter=time_filter, limit=fetch_limit)
            elif sort_method == 'hot':
                posts_iter = subreddit.hot(limit=fetch_limit)
            elif sort_method == 'new':
                posts_iter = subreddit.new(limit=fetch_limit)
            elif sort_method == 'rising':
                posts_iter = subreddit.rising(limit=fetch_limit)
            else:
                posts_iter = subreddit.hot(limit=fetch_limit)
            
            async for post in posts_iter:
                posts.append(post)
                if len(posts) >= fetch_limit:
                    break
                    
        except Exception as e:
            print(f"Error fetching posts with {sort_method}: {e}")
        
        return posts
    
    async def fetch_memes_by_keyword(self, keyword: str, subreddits: Optional[List[str]] = None, limit: int = 5) -> List[Dict]:
        """
        Fetch memes from Reddit based on a keyword with cache busting.
        
        Args:
            keyword: Search keyword
            subreddits: List of subreddits to search in
            limit: Maximum number of memes to return
            
        Returns:
            List of meme dictionaries with title, url, author, subreddit, and score
        """
        # Clean inputs
        keyword = self._clean_input(keyword) or ""
        
        if subreddits is None:
            subreddits = DEFAULT_SUBREDDITS
        else:
            # Clean subreddit names and filter out None values
            cleaned_subreddits = []
            for sub in subreddits:
                cleaned = self._clean_input(sub)
                if cleaned:
                    cleaned_subreddits.append(cleaned)
            subreddits = cleaned_subreddits if cleaned_subreddits else DEFAULT_SUBREDDITS
        
        memes = []
        
        # Strategy: Use multiple search methods and combine results
        search_methods = ['relevance', 'hot', 'new', 'top']
        
        for subreddit_name in subreddits:
            try:
                subreddit = await self.reddit.subreddit(subreddit_name)
                
                # Try different search methods for variety
                for search_method in search_methods:
                    if len(memes) >= limit * 2:  # Get more than needed for variety
                        break
                    
                    try:
                        search_results = subreddit.search(keyword, sort=search_method, limit=limit * 2)
                        
                        async for post in search_results:
                            if len(memes) >= limit * 2:
                                break
                            
                            post_id = self._get_post_id(post)
                            
                            # Skip if we've seen this post recently
                            if post_id in self._used_post_ids:
                                continue
                            
                            if self.is_image_post(post):
                                meme = {
                                    'title': getattr(post, 'title', ''),
                                    'url': getattr(post, 'url', ''),
                                    'author': str(getattr(post, 'author', 'None')),
                                    'subreddit': subreddit_name,
                                    'score': getattr(post, 'score', 0),
                                    'permalink': f"https://reddit.com{getattr(post, 'permalink', '')}",
                                    'search_method': search_method
                                }
                                memes.append(meme)
                                self._used_post_ids.add(post_id)
                        
                        # Small delay between search methods
                        await asyncio.sleep(0.2)
                        
                    except Exception as e:
                        print(f"Error with search method {search_method} in r/{subreddit_name}: {e}")
                        continue
                
            except Exception as e:
                print(f"Error fetching from r/{subreddit_name}: {e}")
                continue
        
        # Shuffle results for randomness
        random.shuffle(memes)
        
        # If we don't have enough memes from keyword search, get random posts
        if len(memes) < limit:
            additional_memes = await self.fetch_random_memes(limit - len(memes), subreddits)
            memes.extend(additional_memes)
        
        return memes[:limit]
    
    async def fetch_random_memes(self, limit: int = 5, subreddits: Optional[List[str]] = None) -> List[Dict]:
        """
        Fetch random memes from specified subreddits using multiple cache-busting strategies.
        
        Args:
            limit: Maximum number of memes to return
            subreddits: List of subreddits to fetch from
            
        Returns:
            List of meme dictionaries
        """
        if subreddits is None:
            subreddits = DEFAULT_SUBREDDITS
        else:
            # Clean subreddit names and filter out None values
            cleaned_subreddits = []
            for sub in subreddits:
                cleaned = self._clean_input(sub)
                if cleaned:
                    cleaned_subreddits.append(cleaned)
            subreddits = cleaned_subreddits if cleaned_subreddits else DEFAULT_SUBREDDITS
        
        all_memes = []
        
        # Strategy 1: Use multiple sorting methods
        sort_methods = ['hot', 'new', 'top', 'rising']
        
        # Strategy 2: Use different time filters for top posts
        time_filters = ['day', 'week', 'month', 'year', 'all']
        
        # Strategy 3: Shuffle subreddits to get different order
        shuffled_subreddits = list(subreddits)
        random.shuffle(shuffled_subreddits)
        
        for subreddit_name in shuffled_subreddits:
            try:
                subreddit = await self.reddit.subreddit(subreddit_name)
                
                # Strategy 4: Randomly select multiple sorting methods per subreddit
                selected_methods = random.sample(sort_methods, random.randint(2, len(sort_methods)))
                
                for sort_method in selected_methods:
                    if len(all_memes) >= limit * 4:  # Get more than needed for variety
                        break
                    
                    # Strategy 5: Use different time filters for top posts
                    if sort_method == 'top':
                        time_filter = random.choice(time_filters)
                    else:
                        time_filter = None
                    
                    posts = await self._fetch_posts_with_cache_busting(
                        subreddit, sort_method, limit * 2, time_filter
                    )
                    
                    for post in posts:
                        if len(all_memes) >= limit * 4:
                            break
                        
                        post_id = self._get_post_id(post)
                        
                        # Strategy 6: Skip recently used posts
                        if post_id in self._used_post_ids:
                            continue
                        
                        if self.is_image_post(post):
                            meme = {
                                'title': getattr(post, 'title', ''),
                                'url': getattr(post, 'url', ''),
                                'author': str(getattr(post, 'author', 'None')),
                                'subreddit': subreddit_name,
                                'score': getattr(post, 'score', 0),
                                'permalink': f"https://reddit.com{getattr(post, 'permalink', '')}",
                                'sort_method': sort_method
                            }
                            
                            # Add time filter info for top posts
                            if sort_method == 'top':
                                meme['time_filter'] = time_filter
                            
                            all_memes.append(meme)
                            self._used_post_ids.add(post_id)
                    
                    # Strategy 7: Small delay between different sorting methods
                    await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"Error fetching from r/{subreddit_name}: {e}")
                continue
        
        # Strategy 8: Shuffle all collected memes for true randomness
        random.shuffle(all_memes)
        
        # Strategy 9: Clear old used post IDs to prevent memory buildup
        if len(self._used_post_ids) > 1000:
            self._used_post_ids.clear()
        
        # Return the requested number of memes
        return all_memes[:limit]
    
    async def get_trending_memes(self, limit: int = 5) -> List[Dict]:
        """
        Get trending memes from popular meme subreddits with cache busting.
        
        Args:
            limit: Maximum number of memes to return
            
        Returns:
            List of trending meme dictionaries
        """
        return await self.fetch_random_memes(limit, DEFAULT_SUBREDDITS)

    async def async_gen(self, items):
        for item in items:
            yield item
