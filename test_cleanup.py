#!/usr/bin/env python3
"""
Test script to check what logs would be deleted without actually deleting them
"""
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from app.config.db import get_collection

async def check_old_logs():
    """Check how many logs would be deleted"""
    try:
        collection = await get_collection("prediction_market_logs")
        
        # Calculate cutoff date (2 days ago)
        cutoff_date = datetime.now() - timedelta(days=2)
        print(f"Cutoff date: {cutoff_date}")
        
        # Count total logs
        total_logs = await collection.count_documents({})
        print(f"Total logs in collection: {total_logs}")
        
        # Count old logs that would be deleted
        old_logs_query = {"timestamp": {"$lt": cutoff_date}}
        old_logs_count = await collection.count_documents(old_logs_query)
        print(f"Logs older than 2 days (to be deleted): {old_logs_count}")
        
        # Count recent logs that would remain
        recent_logs_count = total_logs - old_logs_count
        print(f"Recent logs (to be kept): {recent_logs_count}")
        
        # Show some sample old logs
        if old_logs_count > 0:
            print("\nSample old logs that would be deleted:")
            sample_old_logs = collection.find(old_logs_query).limit(3)
            async for log in sample_old_logs:
                print(f"  - {log.get('timestamp', 'No timestamp')} | {log.get('level', 'No level')} | {log.get('message', 'No message')[:100]}...")
        
    except Exception as e:
        print(f"Error checking logs: {e}")

if __name__ == "__main__":
    asyncio.run(check_old_logs())