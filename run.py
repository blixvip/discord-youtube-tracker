#!/usr/bin/env python3
"""
Simple script to run the Discord Meme Fetcher Bot
"""

import asyncio
import sys
import os
from discord_bot import main
from colorama import init, Fore as f, Style as s

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

init(autoreset=True)

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print(f"🎭 {f.LIGHTMAGENTA_EX}Starting Discord Meme Fetcher Bot...")
    print(f"{f.RED}Press Ctrl+C to stop the bot")
    print(f"{f.YELLOW}=" * 50)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n👋 {f.RED}Bot stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
