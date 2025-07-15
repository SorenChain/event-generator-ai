# app/utils/mongodb_logging.py
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
import traceback
import os
import socket
from dataclasses import dataclass, asdict

# from app.config.db import get_database
from app.config.db import get_collection


@dataclass
class LogEntry:
    """Data model for log entries stored in MongoDB"""
    timestamp: datetime
    level: str
    message: str
    logger_name: str
    module: str
    function: str
    line_number: int
    process_id: int
    thread_id: int
    hostname: str
    script_name: str
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    stack_trace: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None


class MongoDBHandler(logging.Handler):
    """Custom logging handler that writes logs to MongoDB"""
    
    def __init__(self, collection_name: str = "application_logs"):
        super().__init__()
        self.collection_name = collection_name
        self.hostname = socket.gethostname()
        self.script_name = os.path.basename(os.getcwd())
        
    async def _get_collection(self):
        """Get MongoDB collection for logs"""
        # db = await get_database()
        return await get_collection(self.collection_name)
    
    def emit(self, record: logging.LogRecord):
        """Emit a log record to MongoDB"""
        try:
            # Create log entry
            log_entry = LogEntry(
                timestamp=datetime.fromtimestamp(record.created),
                level=record.levelname,
                message=record.getMessage(),
                logger_name=record.name,
                module=record.module if hasattr(record, 'module') else 'unknown',
                function=record.funcName if hasattr(record, 'funcName') else 'unknown',
                line_number=record.lineno if hasattr(record, 'lineno') else 0,
                process_id=record.process if hasattr(record, 'process') else 0,
                thread_id=record.thread if hasattr(record, 'thread') else 0,
                hostname=self.hostname,
                script_name=self.script_name
            )
            
            # Add exception information if present
            if record.exc_info:
                exc_type, exc_value, exc_traceback = record.exc_info
                log_entry.exception_type = exc_type.__name__ if exc_type else None
                log_entry.exception_message = str(exc_value) if exc_value else None
                log_entry.stack_trace = ''.join(traceback.format_exception(
                    exc_type, exc_value, exc_traceback
                )) if exc_traceback else None
            
            # Add any extra data
            extra_data = {}
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                             'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                             'relativeCreated', 'thread', 'threadName', 'processName', 
                             'process', 'message', 'exc_info', 'exc_text', 'stack_info']:
                    extra_data[key] = str(value)  # Convert to string for JSON serialization
            
            if extra_data:
                log_entry.extra_data = extra_data
            
            # Save to MongoDB asynchronously
            asyncio.create_task(self._save_log(log_entry))
            
        except Exception as e:
            # Fallback to console logging if database logging fails
            print(f"Failed to log to MongoDB: {e}")
            print(f"Original log: {record.getMessage()}")
    
    async def _save_log(self, log_entry: LogEntry):
        """Save log entry to MongoDB"""
        try:
            collection = await self._get_collection()
            await collection.insert_one(asdict(log_entry))
        except Exception as e:
            # Fallback logging
            print(f"MongoDB logging error: {e}")


class AsyncMongoDBHandler(logging.Handler):
    """Async version of MongoDB handler for better performance"""
    
    def __init__(self, collection_name: str = "application_logs", batch_size: int = 10):
        super().__init__()
        self.collection_name = collection_name
        self.hostname = socket.gethostname()
        self.script_name = "prediction_market_app"
        self.batch_size = batch_size
        self.log_buffer = []
        
    async def _get_collection(self):
        """Get MongoDB collection for logs"""
        # db = await get_database()
        return await get_collection(self.collection_name)
    
    def emit(self, record: logging.LogRecord):
        """Buffer log records and batch insert"""
        try:
            log_entry = self._create_log_entry(record)
            self.log_buffer.append(asdict(log_entry))
            
            # Batch insert when buffer is full
            if len(self.log_buffer) >= self.batch_size:
                asyncio.create_task(self._flush_logs())
                
        except Exception as e:
            print(f"Failed to buffer log: {e}")
    
    def _create_log_entry(self, record: logging.LogRecord) -> LogEntry:
        """Create LogEntry from logging record"""
        log_entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created),
            level=record.levelname,
            message=record.getMessage(),
            logger_name=record.name,
            module=getattr(record, 'module', 'unknown'),
            function=getattr(record, 'funcName', 'unknown'),
            line_number=getattr(record, 'lineno', 0),
            process_id=getattr(record, 'process', 0),
            thread_id=getattr(record, 'thread', 0),
            hostname=self.hostname,
            script_name=self.script_name
        )
        
        # Add exception information
        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            log_entry.exception_type = exc_type.__name__ if exc_type else None
            log_entry.exception_message = str(exc_value) if exc_value else None
            log_entry.stack_trace = ''.join(traceback.format_exception(
                exc_type, exc_value, exc_traceback
            )) if exc_traceback else None
        
        return log_entry
    
    async def _flush_logs(self):
        """Flush buffered logs to MongoDB"""
        if not self.log_buffer:
            return
            
        try:
            collection = await self._get_collection()
            # Remove _id field to let MongoDB generate unique ones
            logs_to_insert = []
            for log_entry in self.log_buffer:
                log_copy = log_entry.copy()
                log_copy.pop('_id', None)  # Remove _id if present
                logs_to_insert.append(log_copy)
            
            await collection.insert_many(logs_to_insert)
            self.log_buffer.clear()
        except Exception as e:
            print(f"Failed to flush logs to MongoDB: {e}")
    
    async def close_async(self):
        """Ensure all logs are flushed before closing"""
        await self._flush_logs()


def setup_mongodb_logging(
    level: int = logging.INFO,
    collection_name: str = "application_logs",
    console_logging: bool = True,
    use_async_handler: bool = True
):
    """
    Setup MongoDB logging configuration
    
    Args:
        level: Logging level
        collection_name: MongoDB collection name for logs
        console_logging: Whether to also log to console
        use_async_handler: Whether to use async batched handler
    """
    # Clear existing handlers
    logging.getLogger().handlers.clear()
    
    # Setup formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Setup MongoDB handler
    if use_async_handler:
        mongo_handler = AsyncMongoDBHandler(collection_name=collection_name)
    else:
        mongo_handler = MongoDBHandler(collection_name=collection_name)
    
    mongo_handler.setLevel(level)
    mongo_handler.setFormatter(detailed_formatter)
    
    # Setup console handler if requested
    handlers = [mongo_handler]
    if console_logging:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(simple_formatter)
        handlers.append(console_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers
    )
    
    # Reduce noise from HTTP libraries
    for logger_name in ["aiohttp", "urllib3", "motor"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    return mongo_handler


# Context manager for tracking function execution
class LoggedFunction:
    """Context manager to log function entry/exit and capture errors"""
    
    def __init__(self, function_name: str, logger: logging.Logger = None, **kwargs):
        self.function_name = function_name
        self.logger = logger or logging.getLogger(__name__)
        self.extra_data = kwargs
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info(
            f"Starting function: {self.function_name}",
            extra={"function_start": True, **self.extra_data}
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.info(
                f"Completed function: {self.function_name} (duration: {duration:.2f}s)",
                extra={"function_complete": True, "duration": duration, **self.extra_data}
            )
        else:
            self.logger.error(
                f"Function {self.function_name} failed after {duration:.2f}s: {exc_val}",
                exc_info=(exc_type, exc_val, exc_tb),
                extra={"function_error": True, "duration": duration, **self.extra_data}
            )
        
        return False  # Don't suppress the exception


# Utility functions for common logging patterns
async def cleanup_all_logs(collection_name: str = "application_logs", logger: logging.Logger = None):
    """
    Delete ALL logs from MongoDB collection to start fresh
    
    Args:
        collection_name: MongoDB collection name for logs
        logger: Logger instance for logging cleanup operations
    """
    logger = logger or logging.getLogger(__name__)
    
    try:
        # Get collection
        collection = await get_collection(collection_name)
        
        # Count all documents
        total_logs_count = await collection.count_documents({})
        
        if total_logs_count == 0:
            logger.info(f"No logs found in {collection_name}")
            return 0
        
        # Delete all logs
        delete_result = await collection.delete_many({})
        deleted_count = delete_result.deleted_count
        
        logger.info(
            f"Cleaned up ALL {deleted_count} logs from {collection_name} for fresh start",
            extra={
                "cleanup_operation": True,
                "collection": collection_name,
                "deleted_count": deleted_count,
                "cleanup_type": "all_logs"
            }
        )
        
        return deleted_count
        
    except Exception as e:
        logger.error(
            f"Failed to cleanup all logs from {collection_name}: {str(e)}",
            exc_info=True,
            extra={
                "cleanup_error": True,
                "collection": collection_name,
                "cleanup_type": "all_logs"
            }
        )
        raise


def log_api_call(url: str, status_code: int, response_time: float, logger: logging.Logger = None):
    """Log API call details"""
    logger = logger or logging.getLogger(__name__)
    level = logging.INFO if 200 <= status_code < 400 else logging.WARNING
    
    logger.log(
        level,
        f"API call to {url} returned {status_code} in {response_time:.2f}s",
        extra={
            "api_url": url,
            "status_code": status_code,
            "response_time": response_time,
            "api_call": True
        }
    )


def log_database_operation(operation: str, collection: str, count: int = None, logger: logging.Logger = None):
    """Log database operations"""
    logger = logger or logging.getLogger(__name__)
    message = f"Database {operation} on {collection}"
    if count is not None:
        message += f" (count: {count})"
    
    logger.info(
        message,
        extra={
            "db_operation": operation,
            "collection": collection,
            "count": count,
            "database_operation": True
        }
    )