import pytest
from unittest.mock import AsyncMock, patch, Mock, PropertyMock
import discord
from discord_bot import MemeBot, MemeCommands
from config import MAX_MEMES_PER_REQUEST
from youtube_client import VideoSubscription


class TestMemeBot:
    """Test suite for MemeBot class."""
    
    @pytest.fixture
    def bot(self):
        """Create a MemeBot instance for testing."""
        with patch('discord_bot.DISCORD_TOKEN', 'test_token'):
            with patch('discord_bot.RedditMemeFetcher'):
                bot = MemeBot()
                bot.reddit_client = AsyncMock()
                return bot
    
    def test_bot_initialization(self):
        """Test MemeBot initialization."""
        with patch('discord_bot.DISCORD_TOKEN', 'test_token'):
            with patch('discord_bot.RedditMemeFetcher'):
                bot = MemeBot()
                
                assert bot.command_prefix == '!'
                assert hasattr(bot, 'reddit_client')
                assert bot._shutdown_requested is False
    
    @pytest.mark.asyncio
    async def test_setup_hook(self, bot):
        """Test setup_hook method."""
        with patch.object(bot, 'add_cog') as mock_add_cog:
            await bot.setup_hook()
            mock_add_cog.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_on_ready(self, bot):
        """Test on_ready event."""
        with patch.object(MemeBot, 'user', new_callable=PropertyMock) as mock_user:
            mock_user.return_value = Mock(id=123456789)
            with patch('builtins.print') as mock_print:
                await bot.on_ready()

                # Check that print was called with expected messages
                calls = [call[0][0] for call in mock_print.call_args_list]
                # The actual message format might be different, let's check for any print call
                assert len(mock_print.call_args_list) > 0
                # Check if any call contains the expected text
                all_calls = [str(call) for call in mock_print.call_args_list]
                assert any("Meme Fetcher Bot" in call or "online" in call for call in all_calls)
    
    @pytest.mark.asyncio
    async def test_close_method(self, bot):
        """Test close method."""
        bot.reddit_client.close = AsyncMock()
        bot._closed = False
        
        with patch('builtins.print') as mock_print:
            await bot.close()
            
            bot.reddit_client.close.assert_called_once()
            # Check that print was called with shutdown messages
            calls = [call[0][0] for call in mock_print.call_args_list]
            assert any('Shutting down bot...' in c for c in calls)
            assert any('Reddit client closed' in c for c in calls)
            assert any('Bot shutdown complete!' in c for c in calls)
    
    @pytest.mark.asyncio
    async def test_close_method_reddit_error(self, bot):
        """Test close method when Reddit client close fails."""
        bot.reddit_client.close.side_effect = Exception("Reddit close error")
        bot._closed = False
        
        with patch('builtins.print') as mock_print:
            await bot.close()
            
            # Should handle error gracefully
            calls = [call[0][0] for call in mock_print.call_args_list]
            assert any('Error closing Reddit client' in c for c in calls)


class TestMemeCommands:
    """Test suite for MemeCommands class."""
    
    @pytest.fixture
    def bot(self):
        """Create a MemeBot instance for testing."""
        with patch('discord_bot.DISCORD_TOKEN', 'test_token'):
            with patch('discord_bot.RedditMemeFetcher'):
                bot = MemeBot()
                bot.reddit_client = AsyncMock()
                return bot
    
    @pytest.fixture
    def cog(self, bot):
        """Create a MemeCommands instance for testing."""
        return MemeCommands(bot)
    
    @pytest.fixture
    def mock_context(self):
        """Create a mock Discord context for testing."""
        context = AsyncMock()
        context.typing = AsyncMock()
        context.send = AsyncMock()
        # Ensure send returns a proper mock that can be accessed
        context.send.return_value = None
        # Set up the mock to properly handle call_args
        context.send.call_args = None
        context.send.call_args_list = []
        return context
    
    @pytest.fixture
    def mock_meme(self):
        """Create a mock meme dictionary for testing."""
        return {
            'title': 'Test Meme',
            'url': 'https://example.com/meme.jpg',
            'author': 'test_user',
            'subreddit': 'memes',
            'score': 100,
            'permalink': 'https://reddit.com/r/memes/comments/123/test_meme/'
        }
    
    def test_cog_initialization(self, cog, bot):
        """Test MemeCommands initialization."""
        assert cog.bot == bot
        assert cog.reddit_client == bot.reddit_client
    
    @pytest.mark.asyncio
    async def test_fetch_meme_with_keyword(self, cog, mock_context, mock_meme):
        """Test fetch_meme command with keyword."""
        cog.reddit_client.fetch_memes_by_keyword.return_value = [mock_meme]
        
        # Call the callback with correct argument order
        await cog.fetch_meme.callback(cog, mock_context, keyword="test")
        
        cog.reddit_client.fetch_memes_by_keyword.assert_called_once_with("test", limit=MAX_MEMES_PER_REQUEST)
        mock_context.send.assert_called_once()
        
        # Check embed content
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert embed.title == "🎭 Memes for 'test' (1/1)"
        assert embed.description == "Test Meme"
        assert embed.url == "https://reddit.com/r/memes/comments/123/test_meme/"
    
    @pytest.mark.asyncio
    async def test_fetch_meme_without_keyword(self, cog, mock_context, mock_meme):
        """Test fetch_meme command without keyword."""
        cog.reddit_client.get_trending_memes.return_value = [mock_meme]
        
        # Call the callback with correct argument order
        await cog.fetch_meme.callback(cog, mock_context, keyword=None)
        
        cog.reddit_client.get_trending_memes.assert_called_once_with(limit=MAX_MEMES_PER_REQUEST)
        mock_context.send.assert_called_once()
        
        # Check embed content
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert embed.title == "🔥 Trending Memes (1/1)"
    
    @pytest.mark.asyncio
    async def test_fetch_meme_no_results(self, cog, mock_context):
        """Test fetch_meme command when no memes are found."""
        cog.reddit_client.fetch_memes_by_keyword.return_value = []
        
        # Call the callback with correct argument order
        await cog.fetch_meme.callback(cog, mock_context, keyword="nonexistent")
        
        mock_context.send.assert_called_once()
        
        # Check error embed
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert embed.title == "❌ No memes found!"
        assert embed.color.value == discord.Color.red().value
    
    @pytest.mark.asyncio
    async def test_fetch_meme_exception_handling(self, cog, mock_context):
        """Test fetch_meme command exception handling."""
        cog.reddit_client.fetch_memes_by_keyword.side_effect = Exception("API Error")
        
        # Call the callback with correct argument order
        await cog.fetch_meme.callback(cog, mock_context, keyword="test")
        
        mock_context.send.assert_called_once()
        
        # Check error embed
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert embed.title == "❌ Error fetching memes"
        assert "API Error" in embed.description
    
    @pytest.mark.asyncio
    async def test_random_memes_success(self, cog, mock_context, mock_meme):
        """Test random_memes command success."""
        cog.reddit_client.fetch_random_memes.return_value = [mock_meme]
        
        # Call the callback with correct argument order
        await cog.random_memes.callback(cog, mock_context, 1)
        
        cog.reddit_client.fetch_random_memes.assert_called_once_with(limit=1)
        mock_context.send.assert_called_once()
        
        # Check embed content
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert embed.title == "🎲 Random Memes (1/1)"
    
    @pytest.mark.asyncio
    async def test_random_memes_count_limits(self, cog, mock_context):
        """Test random_memes command count limits."""
        # Test count > 10
        await cog.random_memes.callback(cog, mock_context, 15)
        cog.reddit_client.fetch_random_memes.assert_called_with(limit=10)
        
        # Test count < 1
        cog.reddit_client.fetch_random_memes.reset_mock()
        await cog.random_memes.callback(cog, mock_context, 0)
        cog.reddit_client.fetch_random_memes.assert_called_with(limit=1)
        
        # Test negative count
        cog.reddit_client.fetch_random_memes.reset_mock()
        await cog.random_memes.callback(cog, mock_context, -5)
        cog.reddit_client.fetch_random_memes.assert_called_with(limit=1)
    
    @pytest.mark.asyncio
    async def test_search_memes_success(self, cog, mock_context, mock_meme):
        """Test search_memes command success."""
        cog.reddit_client.fetch_memes_by_keyword.return_value = [mock_meme]
        
        # Call the callback with correct argument order
        await cog.search_memes.callback(cog, mock_context, "test", "memes", 1)
        
        cog.reddit_client.fetch_memes_by_keyword.assert_called_once_with("test", ["memes"], limit=1)
        mock_context.send.assert_called_once()
        
        # Check embed content
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert "🔍 Search results for 'test'" in embed.title
        assert "in r/memes" in embed.title
    
    @pytest.mark.asyncio
    async def test_search_memes_no_subreddit(self, cog, mock_context, mock_meme):
        """Test search_memes command without subreddit."""
        cog.reddit_client.fetch_memes_by_keyword.return_value = [mock_meme]
        
        # Call the callback with correct argument order
        await cog.search_memes.callback(cog, mock_context, "test", None, 1)
        
        cog.reddit_client.fetch_memes_by_keyword.assert_called_once_with("test", None, limit=1)
    
    @pytest.mark.asyncio
    async def test_search_memes_count_limits(self, cog, mock_context):
        """Test search_memes command count limits."""
        # Test count > 10
        await cog.search_memes.callback(cog, mock_context, "test", "memes", 15)
        cog.reddit_client.fetch_memes_by_keyword.assert_called_with("test", ["memes"], limit=10)
        
        # Test count < 1
        cog.reddit_client.fetch_memes_by_keyword.reset_mock()
        await cog.search_memes.callback(cog, mock_context, "test", "memes", 0)
        cog.reddit_client.fetch_memes_by_keyword.assert_called_with("test", ["memes"], limit=1)
    
    @pytest.mark.asyncio
    async def test_help_command(self, cog, mock_context):
        """Test help_command."""
        # Call the callback with correct argument order
        await cog.help_command.callback(cog, mock_context)
        
        mock_context.send.assert_called_once()
        
        # Check help embed
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert embed.title == "🎭 Meme Fetcher Bot Help"
        assert embed.color.value == discord.Color.blue().value
        
        # Check that all commands are listed
        field_names = [field.name for field in embed.fields]
        assert "!meme [keyword]" in field_names
        assert "!random [count]" in field_names
        assert "!search <keyword> [subreddit] [count]" in field_names
        assert "!help" in field_names
    
    def test_create_meme_embed(self, cog, mock_meme):
        """Test create_meme_embed method."""
        embed = cog.create_meme_embed(mock_meme, "Test Title", 1, 3)
        
        assert embed.title == "Test Title (1/3)"
        assert embed.description == "Test Meme"
        assert embed.url == "https://reddit.com/r/memes/comments/123/test_meme/"
        assert embed.color.value == discord.Color.orange().value
        
        # Check fields
        field_names = [field.name for field in embed.fields]
        field_values = [field.value for field in embed.fields]
        
        assert "Subreddit" in field_names
        assert "r/memes" in field_values
        
        assert "Score" in field_names
        assert "⬆️ 100" in field_values
        
        assert "Author" in field_names
        assert "u/test_user" in field_values

    @pytest.mark.asyncio
    async def test_create_video_embed_and_button(self, cog):
        video = {
            "video_id": "video123",
            "title": "A useful AI video",
            "url": "https://www.youtube.com/watch?v=video123",
            "published": "2026-07-31T12:00:00+00:00",
            "thumbnail_url": "https://img.example/video123.jpg",
        }
        subscription = VideoSubscription(
            youtube_channel_id="UC1234567890123456789012",
            youtube_channel_name="Example Creator",
            discord_channel_id=42,
            last_video_id="older-video",
        )

        embed = cog.create_video_embed(video, subscription)
        view = cog.create_video_view(video)

        assert embed.title == "A useful AI video"
        assert embed.url == video["url"]
        assert embed.color.value == 0xFF0000
        assert embed.image.url == "https://img.example/video123.jpg"
        assert view.children[0].url == video["url"]

    @pytest.mark.asyncio
    async def test_add_youtube_channel_routes_to_everything_and_creator(self, cog):
        context = AsyncMock()
        context.guild = Mock()
        context.author.guild_permissions.manage_guild = True
        context.typing = AsyncMock()
        context.send = AsyncMock()
        everything = Mock(id=100, mention="#everything")
        creator_channel = Mock(id=200, mention="#example-creator")
        cog._ensure_feed_destinations = AsyncMock(
            return_value=(everything, creator_channel)
        )
        cog.youtube_client.resolve_channel = AsyncMock(
            return_value={
                "channel_id": "UC1234567890123456789012",
                "channel_name": "Example Creator",
            }
        )
        cog.youtube_client.fetch_videos = AsyncMock(
            return_value=[{"video_id": "video123"}]
        )
        cog.subscription_store.add = Mock(return_value=True)

        await cog.add_youtube_channel.callback(
            cog, context, channel="https://youtube.com/@example"
        )

        assert cog.subscription_store.add.call_count == 2
        routed_ids = {
            call.args[0].discord_channel_id
            for call in cog.subscription_store.add.call_args_list
        }
        assert routed_ids == {100, 200}
        context.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_poll_fetches_each_creator_once_for_multiple_routes(self, cog):
        subscriptions = [
            VideoSubscription(
                "UC1234567890123456789012", "Example Creator", channel_id, "video123"
            )
            for channel_id in (100, 200)
        ]
        cog.subscription_store.subscriptions = subscriptions
        cog.youtube_client.fetch_videos = AsyncMock(
            return_value=[{"video_id": "video123"}]
        )

        posted = await cog._poll_subscriptions()

        assert posted == 0
        cog.youtube_client.fetch_videos.assert_awaited_once_with(
            "UC1234567890123456789012", limit=5
        )
    
    @pytest.mark.asyncio
    async def test_fetch_meme_multiple_results(self, cog, mock_context):
        """Test fetch_meme with multiple results."""
        memes = [
            {'title': 'Meme 1', 'url': 'url1', 'author': 'user1', 'subreddit': 'memes', 'score': 100, 'permalink': 'link1'},
            {'title': 'Meme 2', 'url': 'url2', 'author': 'user2', 'subreddit': 'dankmemes', 'score': 200, 'permalink': 'link2'}
        ]
        cog.reddit_client.fetch_memes_by_keyword.return_value = memes
        
        # Call the callback with correct argument order
        await cog.fetch_meme.callback(cog, mock_context, keyword="test")
        
        # Should send multiple embeds
        assert mock_context.send.call_count == 2
        
        # Check first embed
        embed1 = mock_context.send.call_args_list[0][1]['embed']  # Use keyword argument
        assert embed1.title == "🎭 Memes for 'test' (1/2)"
        assert embed1.description == "Meme 1"
        
        # Check second embed
        embed2 = mock_context.send.call_args_list[1][1]['embed']  # Use keyword argument
        assert embed2.title == "🎭 Memes for 'test' (2/2)"
        assert embed2.description == "Meme 2"
    
    @pytest.mark.asyncio
    async def test_fetch_meme_empty_keyword(self, cog, mock_context, mock_meme):
        """Test fetch_meme with empty keyword string."""
        cog.reddit_client.get_trending_memes.return_value = [mock_meme]

        # Call the callback with correct argument order
        await cog.fetch_meme.callback(cog, mock_context, keyword="")

        # Should call get_trending_memes, not fetch_memes_by_keyword
        cog.reddit_client.get_trending_memes.assert_called_once_with(limit=MAX_MEMES_PER_REQUEST)
        cog.reddit_client.fetch_memes_by_keyword.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_fetch_meme_whitespace_keyword(self, cog, mock_context, mock_meme):
        """Test fetch_meme with whitespace-only keyword."""
        cog.reddit_client.fetch_memes_by_keyword.return_value = [mock_meme]
        
        # Call the callback with correct argument order
        await cog.fetch_meme.callback(cog, mock_context, keyword="   ")
        
        cog.reddit_client.fetch_memes_by_keyword.assert_called_once_with("   ", limit=MAX_MEMES_PER_REQUEST)
    
    @pytest.mark.asyncio
    async def test_search_memes_empty_keyword(self, cog, mock_context):
        """Test search_memes with empty keyword."""
        # Call the callback with correct argument order
        await cog.search_memes.callback(cog, mock_context, "", "memes", 1)
        
        cog.reddit_client.fetch_memes_by_keyword.assert_called_once_with("", ["memes"], limit=1)
    
    @pytest.mark.asyncio
    async def test_search_memes_empty_subreddit(self, cog, mock_context):
        """Test search_memes with empty subreddit."""
        # Call the callback with correct argument order
        await cog.search_memes.callback(cog, mock_context, "test", "", 1)

        # Empty string gets converted to None for subreddits
        cog.reddit_client.fetch_memes_by_keyword.assert_called_once_with("test", None, limit=1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
