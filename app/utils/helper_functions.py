"""
Helper functions for the prediction market app.
"""
import re
import sys
import logging
from io import StringIO
from typing import Optional, Dict, List, Any

from bing_image_downloader import downloader
from app.config.db import get_collection

# Configure logging
logger = logging.getLogger(__name__)

def download_first_image(query: str) -> Optional[str]:
    """
    Download the first image for a given query using Bing Image Downloader.
    
    Args:
        query: Search query
        
    Returns:
        Image URL or None if failed
    """
    # Capture the standard output
    old_stdout = sys.stdout
    sys.stdout = buffer = StringIO()
    
    try:
        downloader.download(query, limit=1, output_dir='images', adult_filter_off=True, force_replace=False, timeout=60)
    finally:
        sys.stdout = old_stdout  # Restore standard output
    
    # Extract the printed output
    output_text = buffer.getvalue()
    
    # Use regex to find the image URL
    match = re.search(r'\[%\] Downloading Image #1 from (.+)', output_text)
    
    if match:
        image_url = match.group(1)
        return image_url
    
    return None

async def get_categories_with_topics() -> Dict[str, List[str]]:
    """
    Retrieve all categories and their associated topics.
    
    Returns:
        Dictionary with category names as keys and lists of topic names as values
    """
    try:
        categories_collection = await get_collection("categories")
        topics_collection = await get_collection("topics")

        # Fetch all categories (_id and name)
        categories_cursor = categories_collection.find({}, {"_id": 1, "name": 1})
        categories = {}
        
        async for category in categories_cursor:
            category_id = str(category["_id"])
            category_name = f"{category['name']}_{category_id}"
            categories[category_id] = category_name

        # Fetch all topics (_id, name, and category)
        topics_cursor = topics_collection.find({}, {"_id": 1, "name": 1, "category": 1})

        category_topics_map = {name: [] for name in categories.values()}

        async for topic in topics_cursor:
            category_id = str(topic.get("category"))  # Convert ObjectId to string
            topic_id = str(topic["_id"])
            topic_name = f"{topic.get('name', 'Unknown')}_{topic_id}"

            if category_id in categories:
                category_name = categories[category_id]
                category_topics_map[category_name].append(topic_name)

        return category_topics_map
    except Exception as e:
        logger.error(f"Error retrieving categories and topics: {e}")
        return {}