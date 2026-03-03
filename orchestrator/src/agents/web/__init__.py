"""Web agents -- news, general web search, and crime map scraping."""

# Import all web agents to trigger registration
from src.agents.web.news_scraper import NewsScraperAgent
from src.agents.web.web_search import WebSearchAgent
from src.agents.web.brottsplats import BrottsplatsAgent

__all__ = [
    "NewsScraperAgent",
    "WebSearchAgent",
    "BrottsplatsAgent",
]
