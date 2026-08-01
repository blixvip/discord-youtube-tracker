#!/bin/bash

# Discord YouTuber Tracker Docker Runner
# This script helps you run the Discord bot in a Docker container

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🐳 Discord YouTuber Tracker Docker Runner${NC}"
echo "=================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating from env_example.txt...${NC}"
    if [ -f env_example.txt ]; then
        cp env_example.txt .env
        echo -e "${YELLOW}📝 Please edit .env file with your actual credentials before running.${NC}"
        echo -e "${YELLOW}   Required: DISCORD_TOKEN, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET${NC}"
        exit 1
    else
        echo -e "${RED}❌ No .env file or env_example.txt found. Please create .env file with your credentials.${NC}"
        exit 1
    fi
fi

# Create logs directory if it doesn't exist
mkdir -p logs

echo -e "${GREEN}✅ Environment check passed${NC}"

# Function to handle cleanup
cleanup() {
    echo -e "\n${YELLOW}🛑 Stopping containers...${NC}"
    docker-compose down
    echo -e "${GREEN}✅ Cleanup complete${NC}"
}

# Set up trap to handle Ctrl+C
trap cleanup SIGINT

echo -e "${BLUE}🚀 Starting Discord YouTuber Tracker...${NC}"
echo -e "${BLUE}📊 Use 'docker-compose logs -f' to view logs${NC}"
echo -e "${BLUE}🛑 Press Ctrl+C to stop${NC}"
echo ""

# Build and run the container
docker-compose up --build
