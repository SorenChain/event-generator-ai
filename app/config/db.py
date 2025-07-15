import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import MONGODB_URI, DATABASE_NAME, EVENT_COLLECTION

logger = logging.getLogger(__name__)

async def get_database_connection():
    """
    Establish a connection to the MongoDB cluster.
    
    Returns:
        AsyncIOMotorClient: The MongoDB client.
    """
    try:
        # Initialize the MongoDB client
        client = AsyncIOMotorClient(MONGODB_URI)
        # Test the connection asynchronously
        await client.admin.command("ping")
        return client
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        raise ConnectionError(f"Database connection failed: {e}")

async def get_collection(collection_name=None):
    """
    Get a specific MongoDB collection.
    
    Args:
        collection_name (str, optional): Name of the collection to retrieve.
                                        Defaults to EVENT_COLLECTION.
    
    Returns:
        AsyncIOMotorCollection: The specified collection.
    """
    if collection_name is None:
        collection_name = EVENT_COLLECTION
        
    try:
        client = await get_database_connection()
        db = client[DATABASE_NAME]
        collection = db[collection_name]
        return collection
    except Exception as e:
        logger.error(f"Failed to retrieve collection '{collection_name}': {e}")
        raise RuntimeError(f"Failed to retrieve collection: {e}")

async def get_event_collection():
    """
    Get the MongoDB collection for event data.
    
    Returns:
        AsyncIOMotorCollection: The event data collection.
    """
    return await get_collection(EVENT_COLLECTION)