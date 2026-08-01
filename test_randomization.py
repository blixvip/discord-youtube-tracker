#!/usr/bin/env python3
"""
Test script to demonstrate the improved randomization in the Reddit client.
This script will show how the !random command now fetches different memes each time.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

__test__ = False  # Manual live-API probe, not an offline pytest module.

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reddit_client import RedditMemeFetcher

async def test_randomization():
    """Test the randomization improvements."""
    # Load environment variables
    load_dotenv()
    
    # Check if Reddit credentials are available
    if not os.getenv('REDDIT_CLIENT_ID') or not os.getenv('REDDIT_CLIENT_SECRET'):
        print("❌ Reddit credentials not found in .env file")
        print("Please set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
        return
    
    client = RedditMemeFetcher()
    
    try:
        print("🎲 Testing Random Meme Fetching...")
        print("=" * 50)
        
        # Test multiple fetches to show variety
        for i in range(3):
            print(f"\n📋 Fetch #{i + 1}:")
            print("-" * 30)
            
            memes = await client.fetch_random_memes(limit=3)
            
            for j, meme in enumerate(memes, 1):
                sort_info = meme.get('sort_method', 'unknown')
                if meme.get('time_filter'):
                    sort_info += f" ({meme['time_filter']})"
                
                print(f"  {j}. {meme['title'][:50]}...")
                print(f"     Subreddit: r/{meme['subreddit']}")
                print(f"     Sort: {sort_info}")
                print(f"     Score: {meme['score']}")
                print()
        
        print("✅ Randomization test completed!")
        print("\n🎯 Improvements made:")
        print("  • Uses multiple sorting methods (hot, new, top, rising)")
        print("  • Randomly selects sorting method for each subreddit")
        print("  • Uses different time filters for 'top' posts")
        print("  • Shuffles all collected memes before returning")
        print("  • Fetches 3x more posts than needed for better variety")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_randomization())
