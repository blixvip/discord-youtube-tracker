#!/usr/bin/env python3
"""
Comprehensive test script to verify cache busting for all bot commands.
This script tests that each command fetches different results every time.
"""

import asyncio
import os
import sys
import time
from dotenv import load_dotenv

__test__ = False  # Manual live-API probe, not an offline pytest module.

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reddit_client import RedditMemeFetcher

async def test_command_freshness(command_name: str, test_func, iterations: int = 3):
    """Test that a command returns fresh results each time."""
    print(f"\n🧪 Testing {command_name} command...")
    print("=" * 50)
    
    all_results = []
    
    for i in range(iterations):
        print(f"\n📋 Iteration #{i + 1}:")
        print("-" * 30)
        
        start_time = time.time()
        results = await test_func()
        end_time = time.time()
        
        print(f"⏱️  Fetch time: {end_time - start_time:.2f}s")
        print(f"📊 Results count: {len(results)}")
        
        # Show first result details
        if results:
            first_result = results[0]
            print(f"🎯 First result:")
            print(f"   Title: {first_result['title'][:50]}...")
            print(f"   Subreddit: r/{first_result['subreddit']}")
            print(f"   Score: {first_result['score']}")
            
            # Show method info
            if 'sort_method' in first_result:
                sort_info = first_result['sort_method']
                if 'time_filter' in first_result:
                    sort_info += f" ({first_result['time_filter']})"
                print(f"   Sort: {sort_info}")
            
            if 'search_method' in first_result:
                print(f"   Search: {first_result['search_method']}")
        
        all_results.append(results)
        
        # Small delay between iterations
        await asyncio.sleep(1)
    
    # Analyze results for freshness
    print(f"\n📈 Freshness Analysis:")
    print("-" * 30)
    
    # Check for duplicate posts across iterations
    all_post_ids = set()
    duplicates = 0
    
    for i, results in enumerate(all_results):
        iteration_ids = set()
        for result in results:
            post_id = f"{result['title']}{result['url']}{result['author']}"
            if post_id in all_post_ids:
                duplicates += 1
            all_post_ids.add(post_id)
            iteration_ids.add(post_id)
        
        print(f"   Iteration {i+1}: {len(iteration_ids)} unique posts")
    
    total_posts = sum(len(results) for results in all_results)
    duplicate_rate = (duplicates / total_posts * 100) if total_posts > 0 else 0
    
    print(f"   Total posts fetched: {total_posts}")
    print(f"   Duplicate posts: {duplicates}")
    print(f"   Duplicate rate: {duplicate_rate:.1f}%")
    
    if duplicate_rate < 20:
        print(f"✅ {command_name}: GOOD - Low duplicate rate")
    elif duplicate_rate < 50:
        print(f"⚠️  {command_name}: MODERATE - Some duplicates")
    else:
        print(f"❌ {command_name}: POOR - High duplicate rate")
    
    return duplicate_rate

async def test_all_commands():
    """Test all bot commands for freshness."""
    # Load environment variables
    load_dotenv()
    
    # Check if Reddit credentials are available
    if not os.getenv('REDDIT_CLIENT_ID') or not os.getenv('REDDIT_CLIENT_SECRET'):
        print("❌ Reddit credentials not found in .env file")
        print("Please set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
        return
    
    client = RedditMemeFetcher()
    
    try:
        print("🎭 Testing All Bot Commands for Cache Busting")
        print("=" * 60)
        
        # Test 1: Random memes command
        async def test_random():
            return await client.fetch_random_memes(limit=3)
        
        random_score = await test_command_freshness("!random", test_random)
        
        # Test 2: Trending memes command
        async def test_trending():
            return await client.get_trending_memes(limit=3)
        
        trending_score = await test_command_freshness("!meme (trending)", test_trending)
        
        # Test 3: Keyword search command
        async def test_keyword():
            return await client.fetch_memes_by_keyword("cat", limit=3)
        
        keyword_score = await test_command_freshness("!meme cat", test_keyword)
        
        # Test 4: Specific subreddit search
        async def test_subreddit():
            return await client.fetch_memes_by_keyword("funny", ["memes"], limit=3)
        
        subreddit_score = await test_command_freshness("!search funny memes", test_subreddit)
        
        # Overall assessment
        print(f"\n🎯 Overall Assessment:")
        print("=" * 30)
        
        scores = [random_score, trending_score, keyword_score, subreddit_score]
        avg_score = sum(scores) / len(scores)
        
        print(f"Average duplicate rate: {avg_score:.1f}%")
        
        if avg_score < 20:
            print("✅ EXCELLENT - All commands are fetching fresh results!")
        elif avg_score < 40:
            print("✅ GOOD - Most commands are working well")
        elif avg_score < 60:
            print("⚠️  MODERATE - Some commands need improvement")
        else:
            print("❌ POOR - Commands are heavily cached")
        
        print(f"\n🔧 Cache Busting Strategies Implemented:")
        print("  • Multiple sorting methods (hot, new, top, rising)")
        print("  • Random time filters for top posts")
        print("  • Cache buster timestamps in search queries")
        print("  • Post ID tracking to avoid duplicates")
        print("  • Random delays between requests")
        print("  • Variable fetch limits")
        print("  • Shuffled subreddit order")
        print("  • Multiple search methods per keyword")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_all_commands())
