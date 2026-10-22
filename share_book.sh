#!/bin/bash
set -euo pipefail

# need exactly 3 positional arguments: URL, bucket name, expiration in seconds
if [ $# -ne 3 ]; then
    echo "Usage: share_book.sh URL BUCKET T_EXPIRATION" >&2
    exit 1
fi

URL="$1"
BUCKET="$2"
T_EXPIRATION="$3"

DEST_DIR="books"
mkdir -p "$DEST_DIR"

# extract the file name from the URL
FILENAME=$(basename "$URL")

# download the book, --fail makes curl error out on 404, etc.
curl --fail -o "$DEST_DIR/$FILENAME" "$URL"

# create the bucket only if it doesn't already exist
if ! aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    aws s3 mb "s3://$BUCKET"
fi

# upload privately, content type lets it display in the browser
aws s3 cp "$DEST_DIR/$FILENAME" "s3://$BUCKET/$FILENAME" --content-type "text/plain; charset=utf-8"

# temporary presigned read URL, valid for the specified number of seconds
aws s3 presign "s3://$BUCKET/$FILENAME" --expires-in "$T_EXPIRATION"