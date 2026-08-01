import pytest
import asyncio
from unittest.mock import AsyncMock, patch
import discord

from discord_bot import MemeBot, MemeCommands
from reddit_client import RedditMemeFetcher
from config import MAX_MEMES_PER_REQUEST


class TestIntegration:
    """Integration tests for the Discord Meme Fetcher Bot."""
    
    @pytest.fixture
    def mock_reddit_client(self):
        """Create a mock Reddit client for integration testing."""
        client = AsyncMock(spec=RedditMemeFetcher)
        return client
    
    @pytest.fixture
    def bot_with_mock_reddit(self, mock_reddit_client):
        """Create a bot instance with mocked Reddit client."""
        with patch('discord_bot.DISCORD_TOKEN', 'test_token'):
            with patch('discord_bot.REDDIT_CLIENT_ID', 'test_client_id'):
                with patch('discord_bot.REDDIT_CLIENT_SECRET', 'test_client_secret'):
                    with patch('discord_bot.RedditMemeFetcher', return_value=mock_reddit_client):
                        bot = MemeBot()
                        return bot
    
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
    def sample_memes(self):
        """Create sample meme data for testing."""
        return [
            {
                'title': 'Funny Cat Meme',
                'url': 'https://example.com/cat.jpg',
                'author': 'cat_lover',
                'subreddit': 'memes',
                'score': 1500,
                'permalink': 'https://reddit.com/r/memes/comments/123/funny_cat/'
            },
            {
                'title': 'Programming Humor',
                'url': 'https://example.com/code.png',
                'author': 'dev_user',
                'subreddit': 'ProgrammerHumor',
                'score': 800,
                'permalink': 'https://reddit.com/r/ProgrammerHumor/comments/456/programming_humor/'
            }
        ]
    
    @pytest.mark.asyncio
    async def test_bot_reddit_client_integration(self, bot_with_mock_reddit, mock_reddit_client):
        """Test that bot properly integrates with Reddit client."""
        assert bot_with_mock_reddit.reddit_client == mock_reddit_client
        assert isinstance(bot_with_mock_reddit.reddit_client, AsyncMock)
    
    @pytest.mark.asyncio
    async def test_meme_command_full_flow(self, bot_with_mock_reddit, mock_context, sample_memes):
        """Test complete flow of meme command with Reddit integration."""
        # Setup mock Reddit client to return sample memes
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.return_value = sample_memes
        
        # Create cog and execute command
        cog = MemeCommands(bot_with_mock_reddit)
        await cog.fetch_meme.callback(cog, mock_context, keyword="cat")
        
        # Verify Reddit client was called correctly
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.assert_called_once_with(
            "cat", limit=MAX_MEMES_PER_REQUEST
        )
        
        # Verify Discord context methods were called
        mock_context.typing.assert_called_once()
        assert mock_context.send.call_count == 2  # Two memes sent
        
        # Verify first embed content
        first_embed = mock_context.send.call_args_list[0][1]['embed']  # Use keyword argument
        assert "🎭 Memes for 'cat' (1/2)" in first_embed.title
        assert first_embed.description == "Funny Cat Meme"
        assert first_embed.url == "https://reddit.com/r/memes/comments/123/funny_cat/"
        
        # Verify second embed content
        second_embed = mock_context.send.call_args_list[1][1]['embed']  # Use keyword argument
        assert "🎭 Memes for 'cat' (2/2)" in second_embed.title
        assert second_embed.description == "Programming Humor"
    
    @pytest.mark.asyncio
    async def test_random_command_full_flow(self, bot_with_mock_reddit, mock_context, sample_memes):
        """Test complete flow of random command with Reddit integration."""
        bot_with_mock_reddit.reddit_client.fetch_random_memes.return_value = sample_memes[:1]
        
        cog = MemeCommands(bot_with_mock_reddit)
        await cog.random_memes.callback(cog, mock_context, 1)
        
        bot_with_mock_reddit.reddit_client.fetch_random_memes.assert_called_once_with(limit=1)
        mock_context.typing.assert_called_once()
        mock_context.send.assert_called_once()
        
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert "🎲 Random Memes (1/1)" in embed.title
    
    @pytest.mark.asyncio
    async def test_search_command_full_flow(self, bot_with_mock_reddit, mock_context, sample_memes):
        """Test complete flow of search command with Reddit integration."""
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.return_value = sample_memes[:1]
        
        cog = MemeCommands(bot_with_mock_reddit)
        await cog.search_memes.callback(cog, mock_context, "programming", "ProgrammerHumor", 1)
        
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.assert_called_once_with(
            "programming", ["ProgrammerHumor"], limit=1
        )
        
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert "🔍 Search results for 'programming'" in embed.title
        assert "in r/ProgrammerHumor" in embed.title
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self, bot_with_mock_reddit, mock_context):
        """Test error handling integration between bot and Reddit client."""
        # Simulate Reddit API error
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.side_effect = Exception("Reddit API Error")
        
        cog = MemeCommands(bot_with_mock_reddit)
        await cog.fetch_meme.callback(cog, mock_context, keyword="test")
        
        # Should handle error gracefully and send error embed
        mock_context.send.assert_called_once()
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert embed.title == "❌ Error fetching memes"
        assert "Reddit API Error" in embed.description
    
    @pytest.mark.asyncio
    async def test_no_results_integration(self, bot_with_mock_reddit, mock_context):
        """Test integration when Reddit returns no results."""
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.return_value = []
        
        cog = MemeCommands(bot_with_mock_reddit)
        await cog.fetch_meme.callback(cog, mock_context, keyword="nonexistent")
        
        mock_context.send.assert_called_once()
        embed = mock_context.send.call_args[1]['embed']  # Use keyword argument
        assert embed.title == "❌ No memes found!"
    
    @pytest.mark.asyncio
    async def test_bot_shutdown_integration(self, bot_with_mock_reddit):
        """Test bot shutdown integration with Reddit client."""
        bot_with_mock_reddit.reddit_client.close = AsyncMock()
        
        with patch('builtins.print') as mock_print:
            await bot_with_mock_reddit.close()
            
            bot_with_mock_reddit.reddit_client.close.assert_called_once()
            calls = [call[0][0] for call in mock_print.call_args_list]
            assert any('Shutting down bot...' in c for c in calls)
            assert any('Reddit client closed' in c for c in calls)
    
    @pytest.mark.asyncio
    async def test_command_limits_integration(self, bot_with_mock_reddit, mock_context):
        """Test that command limits are properly enforced in integration."""
        cog = MemeCommands(bot_with_mock_reddit)
        
        # Test count > 10 gets capped
        await cog.random_memes.callback(cog, mock_context, 15)
        bot_with_mock_reddit.reddit_client.fetch_random_memes.assert_called_with(limit=10)
        
        # Test count < 1 gets set to 1
        bot_with_mock_reddit.reddit_client.fetch_random_memes.reset_mock()
        await cog.random_memes.callback(cog, mock_context, 0)
        bot_with_mock_reddit.reddit_client.fetch_random_memes.assert_called_with(limit=1)
    
    @pytest.mark.asyncio
    async def test_embed_creation_integration(self, bot_with_mock_reddit, sample_memes):
        """Test that embeds are created correctly with real meme data."""
        cog = MemeCommands(bot_with_mock_reddit)
        meme = sample_memes[0]
        
        embed = cog.create_meme_embed(meme, "Test Title", 1, 2)
        
        assert embed is not None
        assert embed.title == "Test Title (1/2)"
        assert embed.description == "Funny Cat Meme"
        assert embed.url == "https://reddit.com/r/memes/comments/123/funny_cat/"
        assert embed.color is not None
        assert embed.color.value == discord.Color.orange().value
        
        # Check fields
        field_names = [field.name for field in embed.fields]
        field_values = [field.value for field in embed.fields]
        
        assert "Subreddit" in field_names
        assert "r/memes" in field_values
        
        assert "Score" in field_names
        assert "⬆️ 1500" in field_values
        
        assert "Author" in field_names
        assert "u/cat_lover" in field_values
    
    @pytest.mark.asyncio
    async def test_multiple_commands_integration(self, bot_with_mock_reddit, mock_context, sample_memes):
        """Test that multiple commands work together without interference."""
        cog = MemeCommands(bot_with_mock_reddit)
        
        # Setup mocks
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.return_value = sample_memes[:1]
        bot_with_mock_reddit.reddit_client.fetch_random_memes.return_value = sample_memes[1:2]
        bot_with_mock_reddit.reddit_client.get_trending_memes.return_value = sample_memes[:1]
        
        # Execute multiple commands
        await cog.fetch_meme.callback(cog, mock_context, keyword="test")
        await cog.random_memes.callback(cog, mock_context, 1)
        await cog.fetch_meme.callback(cog, mock_context, keyword=None)  # Trending memes
        
        # Verify all Reddit client methods were called
        assert bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.call_count == 1
        assert bot_with_mock_reddit.reddit_client.fetch_random_memes.call_count == 1
        assert bot_with_mock_reddit.reddit_client.get_trending_memes.call_count == 1
        
        # Verify Discord context was used for all commands
        assert mock_context.typing.call_count == 3
        assert mock_context.send.call_count == 3
    
    @pytest.mark.asyncio
    async def test_async_operations_integration(self, bot_with_mock_reddit, mock_context):
        """Test that async operations work correctly in integration."""
        # Simulate slow Reddit API response
        async def slow_reddit_response(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate network delay
            return []
        
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.side_effect = slow_reddit_response
        
        cog = MemeCommands(bot_with_mock_reddit)
        
        # Should handle async operations correctly
        await cog.fetch_meme.callback(cog, mock_context, keyword="test")
        
        # Verify typing indicator was shown during async operation
        mock_context.typing.assert_called_once()
        mock_context.send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_config_integration(self, bot_with_mock_reddit, mock_context):
        """Test that configuration values are properly used in integration."""
        cog = MemeCommands(bot_with_mock_reddit)
        
        # Test that MAX_MEMES_PER_REQUEST is used
        await cog.fetch_meme.callback(cog, mock_context, keyword="test")
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.assert_called_with(
            "test", limit=MAX_MEMES_PER_REQUEST
        )
        
        # Test that DEFAULT_SUBREDDITS are used when no subreddit specified
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.reset_mock()
        await cog.search_memes.callback(cog, mock_context, "test", None, 1)
        bot_with_mock_reddit.reddit_client.fetch_memes_by_keyword.assert_called_with(
            "test", None, limit=1
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
