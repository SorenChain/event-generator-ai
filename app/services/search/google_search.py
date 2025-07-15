"""
Google Search Service for prediction market app.

This module provides functionality to search Google for images and information
related to prediction market events.
"""
import logging
import asyncio
import aiohttp
import requests
import pandas as pd
from typing import List, Dict, Any, Optional

from app.config.settings import (
    GOOGLE_API_KEY, 
    GOOGLE_CSE_ID, 
    RESULTS_PER_REQUEST,
    MAX_RESULTS_TO_FETCH,
    DESIRED_RECENT_RESULTS,
    DELAY_BETWEEN_REQUESTS,
    DEFAULT_RETRY_COUNT,
    DEFAULT_RETRY_DELAY
)
from app.utils.date_utils import get_date_time_from_snippet

# Configure logging
logger = logging.getLogger(__name__)

class GoogleSearchService:
    """Service for performing Google image and text searches."""
    
    def __init__(
        self, 
        api_key: str = GOOGLE_API_KEY, 
        search_engine_id: str = GOOGLE_CSE_ID
    ):
        """
        Initialize the Google Search Service.
        
        Args:
            api_key: Google API key
            search_engine_id: Google Custom Search Engine ID
        """
        if not api_key or not search_engine_id:
            raise ValueError("Google API key and Search Engine ID are required")
            
        self.api_key = api_key
        self.search_engine_id = search_engine_id
        self.search_url = 'https://www.googleapis.com/customsearch/v1'
    
    def search_image(
        self, 
        query: str, 
        max_retries: int = DEFAULT_RETRY_COUNT, 
        retry_delay: int = DEFAULT_RETRY_DELAY,
        timeout: int = 10
    ) -> Optional[str]:
        """
        Search for an image using Google's Custom Search API.
        
        Args:
            query: Search query
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            timeout: Request timeout in seconds
            
        Returns:
            URL of the first valid image found, or None if no valid image found
        """
        params = {
            'key': self.api_key,
            'cx': self.search_engine_id,
            'q': query,
            'searchType': 'image',
            'num': 10  # Fetch multiple to find a downloadable one
        }
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Image search attempt {attempt} for '{query}'")
                response = requests.get(self.search_url, params=params, timeout=timeout)
                response.raise_for_status()
                
                items = response.json().get('items', [])
                
                for item in items:
                    link = item.get('link')
                    if not link or 'instagram' in link.lower():
                        continue
                    
                    # Check if the image URL is downloadable (HTTP 200)
                    try:
                        head_resp = requests.head(link, allow_redirects=True, timeout=5)
                        if head_resp.status_code == 200:
                            logger.info(f"Valid image URL found: {link}")
                            return link
                        else:
                            logger.warning(f"URL returned status {head_resp.status_code}: {link}")
                    except requests.RequestException as head_err:
                        logger.warning(f"Failed to reach URL {link}: {head_err}")
                
                logger.warning(f"No downloadable image found for '{query}' (attempt {attempt}/{max_retries}).")
            except Exception as e:
                logger.error(f"Error in image search for '{query}' on attempt {attempt}/{max_retries}: {e}")
            
            if attempt < max_retries:
                import time
                time.sleep(retry_delay)
        
        return None
    
    async def fetch(self, session, url, params):
        """Asynchronously fetch data from the Google Custom Search API."""
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    logger.info(f"Successful response for query: {params['q']}")
                    return await response.json()
                else:
                    logger.warning(f"HTTP Error {response.status}: {await response.text()}")
        except asyncio.TimeoutError:
            logger.error(f"Request timed out for query: {params['q']}")
        except aiohttp.ClientError as e:
            logger.error(f"Client error: {e}")
        return None
    
    async def search(
        self,
        category: str,
        results_per_request: int = RESULTS_PER_REQUEST,
        max_results: int = MAX_RESULTS_TO_FETCH,
        desired_recent_results: int = DESIRED_RECENT_RESULTS,
        delay: int = DELAY_BETWEEN_REQUESTS
    ) -> pd.DataFrame:
        """
        Perform a Google search, fetching multiple results.
        
        Args:
            category: Search category/query
            results_per_request: Number of results per request
            max_results: Total maximum results to fetch
            desired_recent_results: Target number of results
            delay: Delay between requests in seconds
            
        Returns:
            DataFrame containing search results
        """
        results = []
        num_batches = max_results // results_per_request
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for batch in range(num_batches):
                if len(results) >= desired_recent_results:
                    break
                    
                start = batch * results_per_request + 1
                params = {
                    'key': self.api_key,
                    'cx': self.search_engine_id,
                    'q': category,
                    'start': start,
                    'num': results_per_request
                }
                
                # Fetch the batch
                response = await self.fetch(session, self.search_url, params)
                
                if response and "items" in response:
                    items = response["items"]
                    for item in items:
                        if len(results) >= desired_recent_results:
                            break
                            
                        # Extract fields
                        title = item.get('title', 'N/A')
                        link = item.get('link', 'N/A')
                        display_link = item.get('displayLink', 'N/A')
                        snippet = item.get('snippet', 'N/A')
                        pagemap = item.get('pagemap', {})
                        metatags = pagemap.get('metatags', [{}])[0]
                        image_url = metatags.get('og:image', None)
                        published_time = metatags.get('article:published_time', 'N/A')
                        
                        if not published_time or published_time == 'N/A':
                            published_time = await get_date_time_from_snippet(snippet)
                            
                        results.append({
                            'Title': title,
                            'Link': link,
                            'Display Link': display_link,
                            'Snippet': snippet,
                            'Image URL': image_url,
                            'Published Time': published_time
                        })
                    
                    logger.info(f"Fetched batch {batch + 1}: {len(items)} results, total results: {len(results)}")
                
                # Delay between requests, unless enough results are collected
                if batch < num_batches - 1 and len(results) < desired_recent_results:
                    logger.info(f"Waiting {delay} seconds...")
                    await asyncio.sleep(delay)
        
        logger.info(f"Total results found: {len(results)} for category: {category}")
        return pd.DataFrame(results)

# Function aliases for backward compatibility
async def google_search(category, *args, **kwargs):
    """Backward compatibility function for google_search."""
    service = GoogleSearchService()
    return await service.search(category, *args, **kwargs)

def google_image_search(query, *args, **kwargs):
    """Backward compatibility function for google_image_search."""
    service = GoogleSearchService()
    return service.search_image(query, *args, **kwargs)