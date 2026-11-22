"""Cloudflare R2 storage client and connection check."""

import os
from contextlib import closing
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

BUCKET = "insider-research"


def client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def smoke_test():
    storage = client()
    key = f"_connection_tests/{uuid4().hex}.txt"
    payload = b"insider research R2 connection test\n"

    try:
        storage.put_object(Bucket=BUCKET, Key=key, Body=payload)
        with closing(storage.get_object(Bucket=BUCKET, Key=key)["Body"]) as body:
            if body.read() != payload:
                raise RuntimeError("R2 readback differs from uploaded bytes")
    finally:
        storage.delete_object(Bucket=BUCKET, Key=key)

    try:
        storage.head_object(Bucket=BUCKET, Key=key)
    except ClientError as error:
        if error.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
            raise
    else:
        raise RuntimeError("R2 test object still exists")

    print("R2 upload, readback, and deletion verified")


if __name__ == "__main__":
    try:
        smoke_test()
    except Exception:
        raise SystemExit("R2 test failed. Check endpoint, credentials, and bucket permissions.") from None
