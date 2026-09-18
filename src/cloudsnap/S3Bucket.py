import boto3
from botocore.exceptions import ClientError, BotoCoreError
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool
import os
import logging

logger = logging.getLogger(__name__)

load_dotenv(override=True)

aws_access_key_id = os.getenv("aws_access_key_id")
aws_secret_access_key = os.getenv("aws_secret_access_key")

s3_client = boto3.client('s3', aws_access_key_id=aws_access_key_id,
                         aws_secret_access_key=aws_secret_access_key)


def upload_file_sync(file_obj, bucket, object_name, content_type=None):

    try:
        extra_args = {"ContentType": content_type} if content_type else {}
        response = s3_client.upload_fileobj(file_obj, bucket, object_name, ExtraArgs=extra_args)
    except (ClientError, BotoCoreError) as e:
        logger.error("S3 upload failed: %s", e)
        return False
    return True


async def upload_file(file_obj, bucket, object_name, content_type=None):
    return await run_in_threadpool(upload_file_sync, file_obj, bucket, object_name, content_type)


def delete_file_sync(bucket, object_name):
    try:
        s3_client.delete_object(Bucket=bucket, Key=object_name)
    except (ClientError, BotoCoreError) as e:
        logging.error(e)
        return False
    return True


async def delete_file(bucket, object_name):
    return await run_in_threadpool(delete_file_sync, bucket, object_name)
