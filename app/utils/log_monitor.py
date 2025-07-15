# app/utils/log_monitor.py
import asyncio
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from collections import defaultdict, Counter

from app.config.db import get_collection


class LogMonitor:
    """MongoDB log monitoring and analysis tool"""
    
    def __init__(self, collection_name: str = "prediction_market_logs"):
        self.collection_name = collection_name
    
    async def get_collection(self):
        """Get the logs collection"""
        # db = await get_database()
        return await get_collection(self.collection_name)
    
    async def get_recent_logs(self, hours: int = 24, level: str = None, limit: int = 100) -> List[Dict]:
        """
        Get recent logs from the database
        
        Args:
            hours: Number of hours to look back
            level: Log level filter (INFO, WARNING, ERROR, CRITICAL)
            limit: Maximum number of logs to return
        """
        collection = await self.get_collection()
        
        # Build query
        query = {
            "timestamp": {
                "$gte": datetime.now() - timedelta(hours=hours)
            }
        }
        
        if level:
            query["level"] = level.upper()
        
        # Get logs sorted by timestamp (newest first)
        cursor = collection.find(query).sort("timestamp", -1).limit(limit)
        logs = await cursor.to_list(length=limit)
        
        return logs
    
    async def get_error_summary(self, hours: int = 24) -> Dict:
        """Get summary of errors in the specified time period"""
        collection = await self.get_collection()
        
        pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)},
                    "level": {"$in": ["ERROR", "CRITICAL"]}
                }
            },
            {
                "$group": {
                    "_id": {
                        "level": "$level",
                        "function": "$function",
                        "exception_type": "$exception_type"
                    },
                    "count": {"$sum": 1},
                    "latest_occurrence": {"$max": "$timestamp"},
                    "messages": {"$addToSet": "$message"}
                }
            },
            {
                "$sort": {"count": -1}
            }
        ]
        
        cursor = collection.aggregate(pipeline)
        errors = await cursor.to_list(length=None)
        
        return {
            "total_errors": len(errors),
            "error_breakdown": errors
        }
    
    async def get_function_performance(self, hours: int = 24) -> Dict:
        """Analyze function performance from logs"""
        collection = await self.get_collection()
        
        # Find function start/complete pairs
        pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)},
                    "extra_data.function_complete": {"$exists": True}
                }
            },
            {
                "$group": {
                    "_id": "$function",
                    "avg_duration": {"$avg": {"$toDouble": "$extra_data.duration"}},
                    "max_duration": {"$max": {"$toDouble": "$extra_data.duration"}},
                    "min_duration": {"$min": {"$toDouble": "$extra_data.duration"}},
                    "count": {"$sum": 1}
                }
            },
            {
                "$sort": {"avg_duration": -1}
            }
        ]
        
        cursor = collection.aggregate(pipeline)
        performance = await cursor.to_list(length=None)
        
        return performance
    
    async def check_cron_job_health(self, expected_interval_hours: int = 24) -> Dict:
        """Check if cron job is running as expected"""
        collection = await self.get_collection()
        
        # Look for main function executions
        last_main_execution = await collection.find_one(
            {"function": "main", "extra_data.function_start": "True"},
            sort=[("timestamp", -1)]
        )
        
        if not last_main_execution:
            return {
                "status": "ERROR",
                "message": "No main function execution found",
                "last_execution": None
            }
        
        last_run = last_main_execution["timestamp"]
        time_since_last_run = datetime.now() - last_run
        
        if time_since_last_run.total_seconds() > expected_interval_hours * 3600 * 1.5:  # 1.5x tolerance
            status = "WARNING"
            message = f"Last execution was {time_since_last_run} ago (expected every {expected_interval_hours}h)"
        else:
            status = "OK"
            message = f"Last execution was {time_since_last_run} ago"
        
        # Check for recent errors
        recent_errors = await collection.count_documents({
            "timestamp": {"$gte": last_run},
            "level": {"$in": ["ERROR", "CRITICAL"]}
        })
        
        return {
            "status": status,
            "message": message,
            "last_execution": last_run,
            "recent_errors": recent_errors
        }
    
    async def get_database_operations_summary(self, hours: int = 24) -> Dict:
        """Summarize database operations"""
        collection = await self.get_collection()
        
        pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)},
                    "extra_data.database_operation": "True"
                }
            },
            {
                "$group": {
                    "_id": {
                        "operation": "$extra_data.db_operation",
                        "collection": "$extra_data.collection"
                    },
                    "total_count": {"$sum": {"$toInt": "$extra_data.count"}},
                    "operation_count": {"$sum": 1}
                }
            }
        ]
        
        cursor = collection.aggregate(pipeline)
        operations = await cursor.to_list(length=None)
        
        return operations
    
    async def print_log_report(self, hours: int = 24):
        """Print a comprehensive log report"""
        print(f"\n{'='*60}")
        print(f"PREDICTION MARKET LOG REPORT - Last {hours} hours")
        print(f"{'='*60}")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Cron job health
        print(f"\n{'CRON JOB HEALTH':-^60}")
        health = await self.check_cron_job_health()
        print(f"Status: {health['status']}")
        print(f"Message: {health['message']}")
        if health['last_execution']:
            print(f"Last Execution: {health['last_execution'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Recent Errors: {health['recent_errors']}")
        
        # Error summary
        print(f"\n{'ERROR SUMMARY':-^60}")
        error_summary = await self.get_error_summary(hours)
        print(f"Total Error Types: {error_summary['total_errors']}")
        
        if error_summary['error_breakdown']:
            print("\nTop Errors:")
            for i, error in enumerate(error_summary['error_breakdown'][:5], 1):
                print(f"{i}. {error['_id']['function']} - {error['_id']['exception_type']} ({error['count']} times)")
                print(f"   Latest: {error['latest_occurrence'].strftime('%Y-%m-%d %H:%M:%S')}")
                if error['messages']:
                    print(f"   Sample: {list(error['messages'])[0][:100]}...")
                print()
        
        # Function performance
        print(f"\n{'FUNCTION PERFORMANCE':-^60}")
        performance = await self.get_function_performance(hours)
        if performance:
            print(f"{'Function':<25} {'Count':<8} {'Avg(s)':<8} {'Max(s)':<8}")
            print("-" * 50)
            for func in performance[:10]:
                print(f"{func['_id']:<25} {func['count']:<8} {func['avg_duration']:<8.2f} {func['max_duration']:<8.2f}")
        
        # Database operations
        print(f"\n{'DATABASE OPERATIONS':-^60}")
        db_ops = await self.get_database_operations_summary(hours)
        if db_ops:
            print(f"{'Operation':<15} {'Collection':<15} {'Count':<8} {'Records':<8}")
            print("-" * 50)
            for op in db_ops:
                print(f"{op['_id']['operation']:<15} {op['_id']['collection']:<15} {op['operation_count']:<8} {op['total_count']:<8}")
        
        # Recent critical errors
        print(f"\n{'RECENT CRITICAL ERRORS':-^60}")
        critical_logs = await self.get_recent_logs(hours=hours, level="CRITICAL", limit=5)
        if critical_logs:
            for log in critical_logs:
                print(f"[{log['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}] {log['function']}")
                print(f"  {log['message']}")
                if log.get('exception_type'):
                    print(f"  Exception: {log['exception_type']} - {log.get('exception_message', '')}")
                print()
        else:
            print("No critical errors found.")
    
    async def export_logs_to_file(self, filename: str, hours: int = 24, level: str = None):
        """Export logs to JSON file"""
        logs = await self.get_recent_logs(hours=hours, level=level, limit=1000)
        
        # Convert ObjectIds and datetime objects to strings
        for log in logs:
            if '_id' in log:
                log['_id'] = str(log['_id'])
            if 'timestamp' in log and isinstance(log['timestamp'], datetime):
                log['timestamp'] = log['timestamp'].isoformat()
        
        with open(filename, 'w') as f:
            json.dump(logs, f, indent=2, default=str)
        
        print(f"Exported {len(logs)} logs to {filename}")


async def main():
    """Main CLI function"""
    parser = argparse.ArgumentParser(description="Monitor prediction market logs")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default: 24)")
    parser.add_argument("--report", action="store_true", help="Generate full report")
    parser.add_argument("--errors", action="store_true", help="Show only errors")
    parser.add_argument("--health", action="store_true", help="Check cron job health")
    parser.add_argument("--export", type=str, help="Export logs to JSON file")
    parser.add_argument("--level", type=str, choices=["INFO", "WARNING", "ERROR", "CRITICAL"], 
                       help="Filter by log level")
    
    args = parser.parse_args()
    
    monitor = LogMonitor()
    
    if args.report:
        await monitor.print_log_report(args.hours)
    elif args.errors:
        error_summary = await monitor.get_error_summary(args.hours)
        print(f"Found {error_summary['total_errors']} error types in last {args.hours} hours")
        for error in error_summary['error_breakdown']:
            print(f"- {error['_id']['function']}: {error['count']} times")
    elif args.health:
        health = await monitor.check_cron_job_health()
        print(f"Status: {health['status']}")
        print(f"Message: {health['message']}")
    elif args.export:
        await monitor.export_logs_to_file(args.export, args.hours, args.level)
    else:
        # Default: show recent logs
        logs = await monitor.get_recent_logs(args.hours, args.level, 20)
        print(f"Recent logs (last {args.hours} hours):")
        for log in logs:
            timestamp = log['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] {log['level']} - {log['function']}: {log['message']}")


if __name__ == "__main__":
    asyncio.run(main())