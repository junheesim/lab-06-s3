#!/usr/bin/env python3

import logging
import os
import sys
import requests
import boto3
from botocore.exceptions import ClientError
import time
import json

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# creating one S3 clients that all functions share
s3 = boto3.client("s3", region_name="us-east-1")

def parse_args():
    """
    Read the book list path, index page path, and bucket name from the command line
    """
    if len(sys.argv) != 4:
        log.error("Usage: stage_books.py LIST_FILE INDEX_PATH BUCKET")
        sys.exit(1)
    list_file = sys.argv[1]
    index_path = sys.argv[2]
    bucket = sys.argv[3]
    return (list_file, index_path, bucket)

def download_books(list_file, dest_dir="books"):
    """
    Download each book URL listed in list_file into dest_dir, skipping ones
    already saved, and return the list of local paths
    """
    os.makedirs(dest_dir, exist_ok=True)
    file_paths = []
    for url in open(list_file):
        url = url.strip() # get rid of lines with blank spaces
        if not url: # blank space lines will be encoded as False, so skip to next line
            continue
        filename = os.path.basename(url) # fetch the part after the last "/"
        new_path = os.path.join(dest_dir, filename)
        if os.path.exists(new_path):
            # already downloaded in a previous run, skip to next iteration
            file_paths.append(new_path)
            continue
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # raise an error for 404, etc.
            with open(new_path, "wb") as f:
                f.write(response.content)
            file_paths.append(new_path)
            time.sleep(1)  # delay to avoid overwhelming servers
        except requests.RequestException as e:
            log.error(f"Error downloading {url}: {e}")
    return file_paths
    
def create_bucket(bucket):
    """
    Create bucket if it doesn't already exist and return True if it exists afterwards
    """
    try:
        s3.head_bucket(Bucket=bucket)
        log.info(f"Bucket already exists: {bucket}")
        return True
    except ClientError as e:
        log.info(f"Bucket {bucket} doesn't exist yet, creating it now...")
        try:
            s3.create_bucket(Bucket=bucket)
            log.info(f"Created bucket: {bucket}")
            return True
        except ClientError as e:
            log.error(f"Error creating bucket {bucket}: {e}")
            return False

def make_public(bucket):
    """
    Turn off Block Public Access and attach a policy allowing public reads
    """
    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                }
            ],
        }
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        log.info(f"Made bucket public: {bucket}")
        return True
    except ClientError as e:
        log.error(f"Error making bucket public {bucket}: {e}")
        return False

def upload_files(bucket, file_paths):
    """
    Upload each local file to the top level of bucket and return the count that succeeded
    """
    successes = 0
    for path in file_paths:
        key = os.path.basename(path)  # upload flat to the bucket root, not under "books/"
        try:
            with open(path, "rb") as f:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType="text/plain; charset=utf-8",
                )
            log.info(f"Uploaded {path} to s3://{bucket}/{key}")
            successes += 1  # successful upload counter
        except FileNotFoundError:
            log.error(f"Local file not found: {path}")
        except ClientError as e:
            log.error(f"Error uploading file: {e}")
    return successes

def upload_index(bucket, index_path):
    """Upload index_path as index.html so the bucket root has a webpage"""
    try:
        key = os.path.basename(index_path)
        with open(index_path, "rb") as f:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=f,
                ContentType="text/html",  # so browsers render it as a webpage
        )
        log.info(f"Uploaded {index_path} to s3://{bucket}/{key}")
        return True
    except FileNotFoundError:
        log.error(f"Local file not found: {index_path}")
        return False
    except ClientError as e:
        log.error(f"Error uploading file: {e}")
        return False

def main():
    """
    Download the books, stage them in a public S3 bucket, and upload the index page
    """
    list_file, index_path, bucket = parse_args()
    file_paths = download_books(list_file)
    # failure messages for when the following functions fail
    if not file_paths:
        log.error("No books were downloaded")
        sys.exit(1)
    if not create_bucket(bucket):
        log.error(f"Could not create bucket {bucket}")
        sys.exit(1)
    if not make_public(bucket):
        log.error(f"Could not make bucket {bucket} public")
        sys.exit(1)
    upload_files(bucket, file_paths)
    upload_index(bucket, index_path)
    log.info(f"Books available at https://{bucket}.s3.amazonaws.com/index.html.")

if __name__ == "__main__":
    main()