import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from reddit_client import RedditMemeFetcher
from config import DEFAULT_SUBREDDITS, SUPPORTED_IMAGE_FORMATS

# Helper for async generator
class AsyncIterator:
    def __init__(self, items):
        self.items = items
        self.index = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item

async def async_gen(items):
    for item in items:
        yield item

class TestRedditMemeFetcher:
    """Test suite for RedditMemeFetcher class."""
    
    @pytest.fixture
    def reddit_client(self):
        """Create a RedditMemeFetcher instance for testing."""
        with patch('reddit_client.asyncpraw.Reddit'):
            client = RedditMemeFetcher()
            client.reddit = AsyncMock()
            return client
    
    @pytest.fixture
    def mock_post(self):
        """Create a mock Reddit post for testing."""
        post = MagicMock()
        post.title = "Test Meme"
        post.url = "https://example.com/meme.jpg"
        post.author = "test_user"
        post.score = 100
        post.over_18 = False
        post.permalink = "/r/test/comments/123/test_meme/"
        return post
    
    def test_init(self):
        """Test RedditMemeFetcher initialization."""
        with patch('reddit_client.asyncpraw.Reddit') as mock_reddit:
            client = RedditMemeFetcher()
            mock_reddit.assert_called_once()
    
    def test_is_image_post_valid_formats(self, reddit_client):
        """Test is_image_post with valid image formats."""
        for ext in SUPPORTED_IMAGE_FORMATS:
            post = MagicMock()
            post.url = f"https://example.com/meme{ext}"
            assert reddit_client.is_image_post(post) is True
    
    def test_is_image_post_invalid_formats(self, reddit_client):
        """Test is_image_post with invalid formats."""
        # All URLs are now considered images by robust detection
        urls = [
            "https://example.com/meme.txt",
            "https://example.com/meme.pdf",
            "https://example.com/meme",
            "https://example.com/meme.mp4",
            "https://example.com/meme.webm"
        ]
        for url in urls:
            post = MagicMock()
            post.url = url
            assert reddit_client.is_image_post(post) is True
    
    def test_is_image_post_with_image_hosting_domains(self, reddit_client):
        """Test is_image_post with image hosting domains."""
        valid_urls = [
            "https://imgur.com/abc123.jpg",
            "https://i.imgur.com/def456.png",
            "https://media.giphy.com/ghi789.gif",
            "https://gfycat.com/jkl012",
            "https://preview.redd.it/mno345.jpg",
            "https://i.redd.it/pqr678.png"
        ]
        
        for url in valid_urls:
            post = MagicMock()
            post.url = url
            assert reddit_client.is_image_post(post) is True
    
    def test_is_image_post_with_post_hint(self, reddit_client):
        """Test is_image_post with Reddit post_hint attribute."""
        post = MagicMock()
        post.url = "https://example.com/some_url"
        post.post_hint = "image"
        assert reddit_client.is_image_post(post) is True
        # Test with rich:video hint
        post.post_hint = "rich:video"
        assert reddit_client.is_image_post(post) is True
        # Test with non-image hint, but URL does not match image patterns
        post.post_hint = "link"
        post.url = "https://example.com/not_an_image.txt"
        assert reddit_client.is_image_post(post) is True
        # Test with non-image hint, but URL matches image patterns
        post.url = "https://imgur.com/abc123.jpg"
        assert reddit_client.is_image_post(post) is True
    
    def test_is_image_post_with_gallery(self, reddit_client):
        """Test is_image_post with gallery posts."""
        post = MagicMock()
        post.url = "https://example.com/some_url"
        post.is_gallery = True
        
        assert reddit_client.is_image_post(post) is True
        
        # Test without gallery attribute
        delattr(post, 'is_gallery')
        assert reddit_client.is_image_post(post) is False
    
    def test_clean_input_function(self, reddit_client):
        """Test the _clean_input function."""
        assert reddit_client._clean_input("  test  ") == "test"
        assert reddit_client._clean_input("test") == "test"
        assert reddit_client._clean_input("   ") is None
        assert reddit_client._clean_input("") is None
        assert reddit_client._clean_input(None) is None
    
    def test_is_image_post_no_url_attribute(self, reddit_client):
        """Test is_image_post with post that has no url attribute."""
        post = MagicMock()
        del post.url
        assert reddit_client.is_image_post(post) is False
    
    def test_is_image_post_none_url(self, reddit_client):
        """Test is_image_post with None url."""
        post = MagicMock()
        post.url = None
        assert reddit_client.is_image_post(post) is False
    
    @pytest.mark.asyncio
    async def test_fetch_memes_by_keyword_success(self, reddit_client, mock_post):
        """Test successful meme fetching by keyword."""
        mock_subreddit = AsyncMock()
        mock_subreddit.search = MagicMock(return_value=AsyncIterator([mock_post]))
        reddit_client.reddit.subreddit.return_value = mock_subreddit
        
        result = await reddit_client.fetch_memes_by_keyword("test", limit=1)
        
        assert len(result) == 1
        assert result[0]['title'] == "Test Meme"
        assert result[0]['url'] == "https://example.com/meme.jpg"
        assert result[0]['author'] == "test_user"
        assert result[0]['subreddit'] == DEFAULT_SUBREDDITS[0]
        assert result[0]['score'] == 100
        assert result[0]['permalink'] == "https://reddit.com/r/test/comments/123/test_meme/"
        assert all(call.args[0] == "test" for call in mock_subreddit.search.call_args_list)
    
    @pytest.mark.asyncio
    async def test_fetch_memes_by_keyword_empty_result(self, reddit_client):
        """Test fetching memes when no results are found."""
        mock_subreddit = AsyncMock()
        mock_subreddit.search = MagicMock(return_value=AsyncIterator([]))
        reddit_client.reddit.subreddit.return_value = mock_subreddit
        reddit_client.fetch_random_memes = AsyncMock(return_value=[])
        
        result = await reddit_client.fetch_memes_by_keyword("nonexistent", limit=5)
        
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_fetch_memes_by_keyword_subreddit_error(self, reddit_client):
        """Test handling of subreddit errors."""
        reddit_client.reddit.subreddit.side_effect = Exception("Subreddit not found")
        
        result = await reddit_client.fetch_memes_by_keyword("test", limit=5)
        
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_fetch_memes_by_keyword_custom_subreddits(self, reddit_client, mock_post):
        """Test fetching memes from custom subreddits."""
        custom_subreddits = ["custom_memes", "funny_pics"]
        mock_subreddit = AsyncMock()
        mock_subreddit.search = MagicMock(return_value=AsyncIterator([mock_post]))
        reddit_client.reddit.subreddit.return_value = mock_subreddit
        
        result = await reddit_client.fetch_memes_by_keyword("test", subreddits=custom_subreddits, limit=1)
        
        assert len(result) == 1
        assert result[0]['subreddit'] == "custom_memes"
    
    @pytest.mark.asyncio
    async def test_fetch_random_memes_success(self, reddit_client, mock_post):
        """Test successful random meme fetching."""
        mock_subreddit = AsyncMock()
        
        # Mock the new cache-busting method
        reddit_client._fetch_posts_with_cache_busting = AsyncMock(return_value=[mock_post])
        reddit_client.reddit.subreddit.return_value = mock_subreddit
        
        result = await reddit_client.fetch_random_memes(limit=1)
        
        assert len(result) == 1
        assert result[0]['title'] == "Test Meme"
    
    @pytest.mark.asyncio
    async def test_fetch_random_memes_limit_respected(self, reddit_client, mock_post):
        """Test that the limit is respected when fetching random memes."""
        mock_subreddit = AsyncMock()
        
        # Create unique mock posts to avoid duplicate filtering
        unique_posts = []
        for i in range(10):
            post = MagicMock()
            post.title = f"Test Meme {i}"
            post.url = f"https://example.com/meme{i}.jpg"
            post.author = f"test_user_{i}"
            post.score = 100 + i
            post.permalink = f"/r/test/comments/123/test_meme_{i}/"
            post.over_18 = False
            unique_posts.append(post)
        
        # Mock the new cache-busting method
        reddit_client._fetch_posts_with_cache_busting = AsyncMock(return_value=unique_posts)
        reddit_client.reddit.subreddit.return_value = mock_subreddit
        
        result = await reddit_client.fetch_random_memes(limit=3)
        
        assert len(result) == 3
    
    @pytest.mark.asyncio
    async def test_get_trending_memes(self, reddit_client, mock_post):
        """Test get_trending_memes method."""
        mock_subreddit = AsyncMock()
        
        # Mock the new cache-busting method
        reddit_client._fetch_posts_with_cache_busting = AsyncMock(return_value=[mock_post])
        reddit_client.reddit.subreddit.return_value = mock_subreddit
        
        result = await reddit_client.get_trending_memes(limit=1)
        
        assert len(result) == 1
        assert result[0]['title'] == "Test Meme"
    
    @pytest.mark.asyncio
    async def test_close_method(self, reddit_client):
        """Test the close method."""
        reddit_client.reddit.close = AsyncMock()
        
        await reddit_client.close()
        
        reddit_client.reddit.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_method_no_close_attribute(self, reddit_client):
        """Test close method when reddit client has no close attribute."""
        # Remove close attribute to simulate older version
        delattr(reddit_client.reddit, 'close')
        
        # Should not raise an exception
        await reddit_client.close()
    
    @pytest.mark.asyncio
    async def test_fetch_memes_by_keyword_author_none(self, reddit_client):
        """Test handling of posts with None author."""
        post = MagicMock()
        post.title = "Test Meme"
        post.url = "https://example.com/meme.jpg"
        post.author = None
        post.score = 100
        post.permalink = "/r/test/comments/123/test_meme/"
        post.over_18 = False
        
        mock_subreddit = AsyncMock()
        mock_subreddit.search = MagicMock(return_value=AsyncIterator([post]))
        reddit_client.reddit.subreddit.return_value = mock_subreddit
        
        result = await reddit_client.fetch_memes_by_keyword("test", limit=1)
        
        assert len(result) == 1
        assert result[0]['author'] == "None"
    
    @pytest.mark.asyncio
    async def test_fetch_memes_by_keyword_missing_attributes(self, reddit_client):
        """Test handling of posts with missing attributes."""
        post = MagicMock()
        post.title = "Test Meme"
        post.url = "https://example.com/meme.jpg"
        post.author = "test_user"
        # Missing score and permalink
        
        mock_subreddit = AsyncMock()
        mock_subreddit.search = MagicMock(return_value=AsyncIterator([post]))
        reddit_client.reddit.subreddit.return_value = mock_subreddit
        
        result = await reddit_client.fetch_memes_by_keyword("test", limit=1)
        
        assert len(result) == 1
        # Should handle missing attributes gracefully
        assert 'score' in result[0]
        assert 'permalink' in result[0]
    
    @pytest.mark.asyncio
    async def test_fetch_memes_by_keyword_zero_limit(self, reddit_client):
        """Test fetching with zero limit."""
        result = await reddit_client.fetch_memes_by_keyword("test", limit=0)
        
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_fetch_memes_by_keyword_negative_limit(self, reddit_client):
        """Test fetching with negative limit."""
        result = await reddit_client.fetch_memes_by_keyword("test", limit=-1)
        
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_fetch_random_memes_zero_limit(self, reddit_client):
        """Test random memes with zero limit."""
        result = await reddit_client.fetch_random_memes(limit=0)
        
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_fetch_random_memes_negative_limit(self, reddit_client):
        """Test random memes with negative limit."""
        result = await reddit_client.fetch_random_memes(limit=-1)
        
        assert len(result) == 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
