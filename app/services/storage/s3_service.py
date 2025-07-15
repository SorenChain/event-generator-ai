"""
S3 Storage Service.

This module provides functionality to upload and retrieve images
from Amazon S3 for prediction market events.
"""
import logging
from typing import Optional
import aiohttp
import boto3
from botocore.exceptions import NoCredentialsError

from app.config.settings import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    AWS_BUCKET_NAME
)

# Configure logging
logger = logging.getLogger(__name__)

class S3StorageService:
    """Service for S3 storage operations."""
    
    def __init__(
        self, 
        access_key: str = AWS_ACCESS_KEY_ID,
        secret_key: str = AWS_SECRET_ACCESS_KEY,
        region: str = AWS_REGION,
        bucket: str = AWS_BUCKET_NAME
    ):
        """
        Initialize the S3 Storage Service.
        
        Args:
            access_key: AWS access key ID
            secret_key: AWS secret access key
            region: AWS region
            bucket: S3 bucket name
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.bucket = bucket
        
        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )
    
    async def upload_image(self, image_url: str, s3_filename: str) -> Optional[str]:
        """
        Download an image from URL and upload to S3.
        
        Args:
            image_url: URL of the image to download
            s3_filename: Desired filename in S3
            
        Returns:
            S3 URL of the uploaded image or None if failed
        """
        try:
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download image: HTTP {response.status}")
                        return None
                    image_data = await response.read()
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_filename,
                Body=image_data,
                ContentType='image/jpeg'
            )

            # Generate S3 URL
            s3_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_filename}"
            logger.info(f"Successfully uploaded image to {s3_url}")
            
            return s3_url
        
        except NoCredentialsError:
            logger.error("AWS credentials not available")
            return None
        except Exception as e:
            logger.error(f"Error uploading image: {e}")
            return None

# Alias function for backward compatibility
async def upload_image_to_s3(image_url, s3_filename):
    """Backward compatibility function for upload_image_to_s3."""
    service = S3StorageService()
    return await service.upload_image(image_url, s3_filename)