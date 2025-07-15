import logging
from typing import List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, validator
from bson.objectid import ObjectId
from app.config.db import get_event_collection

logger = logging.getLogger(__name__)

# Define the status Enum
class StatusEnum(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

# Define a model for individual options in a multi-option question
class OptionData(BaseModel):
    option: str
    probability: int
    market: Optional[ObjectId] = None

    class Config:
        arbitrary_types_allowed = True  # Allow ObjectId

# Define the data model for saving event data
class EventData(BaseModel):
    conditionId: Optional[str] = None
    fpmm_address: Optional[str] = None
    is_child: bool
    is_sport_page: bool
    sport_key: Optional[str] = None
    is_disabled: bool = False
    is_approved: bool = False
    featured: bool = False
    category: Optional[ObjectId] = None
    topic: Optional[ObjectId] = None
    has_options: bool
    title: str
    end_date: Optional[datetime] = None
    event_description: str
    rules: Optional[str] = None
    probability_of_yes: Optional[int] = None
    probability_of_no: Optional[int] = None
    options: Optional[List[OptionData]] = None
    status: StatusEnum = StatusEnum.pending
    event_image: Optional[str] = None
    source_link: Optional[str] = None
    is_settled: bool = False
    settled_date: Optional[datetime] = None
    is_ready_for_settlement: bool = False
    questionId: Optional[str] = None
    yesPositionId: Optional[str] = None
    noPositionId: Optional[str] = None
    created_date: datetime = datetime.now()

    # Custom validators to convert string to ObjectId for category and topic
    @validator('category', 'topic', pre=True)
    def convert_to_objectid(cls, v):
        if isinstance(v, str):
            try:
                return ObjectId(v)  # Convert string to ObjectId
            except Exception:
                raise ValueError(f"Invalid ObjectId format: {v}")
        return v  # Return as is if it's already an ObjectId

    class Config:
        arbitrary_types_allowed = True  # Allow ObjectId to be used in the model

async def   save_event(event_data: EventData):
    """
    Save event data to the database.
    
    Args:
        event_data (EventData): The event data to save
        
    Returns:
        dict: Operation result with status and inserted_id
    """
    try:
        collection = await get_event_collection() 
        if collection is None:
            raise RuntimeError("Database connection failed")
        
        event_data_dict = event_data.dict()
        result = await collection.insert_one(event_data_dict)
        
        return {"status": "success", "inserted_id": str(result.inserted_id)}
    except Exception as e:
        logger.error(f"Failed to save event data: {e}")
        raise RuntimeError(f"Failed to save event data: {e}")

async def remove_duplicate_titles():
    """
    Identify and remove documents with duplicate titles in the collection.
    
    Returns:
        dict: Summary of the operation
    """
    try:
        collection = await get_event_collection()
        if collection is None:
            raise RuntimeError("Database connection failed")

        # Find duplicate titles
        pipeline = [
            {"$group": {
                "_id": "$title",
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]

        duplicates = await collection.aggregate(pipeline).to_list(length=None)

        if not duplicates:
            return {"status": "success", "message": "No duplicate titles found."}

        # Remove duplicates (retain the first occurrence)
        total_deleted = 0
        for duplicate in duplicates:
            ids = duplicate["ids"]
            # Keep the first ID, delete the rest
            ids_to_delete = ids[1:]
            result = await collection.delete_many({"_id": {"$in": ids_to_delete}})
            total_deleted += result.deleted_count

        return {"status": "success", "deleted_count": total_deleted}

    except Exception as e:
        logger.error(f"Failed to remove duplicate titles: {e}")
        raise RuntimeError(f"Failed to remove duplicate titles: {e}")