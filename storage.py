import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import boto3
from botocore.config import Config


def _storage_location():
    """Build the production Supabase S3 client and resolve its bucket."""
    bucket_url = os.environ["STORAGE_BUCKET_URL"].rstrip("/")
    parsed = urlparse(bucket_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("STORAGE_BUCKET_URL must be the HTTPS Supabase S3 URL")

    path_parts = [part for part in parsed.path.split("/") if part]
    try:
        s3_index = path_parts.index("s3")
    except ValueError as exc:
        raise ValueError(
            "STORAGE_BUCKET_URL must include the Supabase /storage/v1/s3 endpoint"
        ) from exc

    if s3_index + 1 >= len(path_parts):
        raise ValueError(
            "STORAGE_BUCKET_URL must end with the Supabase bucket name, e.g. /storage/v1/s3/pdf-uploads"
        )
    if s3_index + 2 != len(path_parts):
        raise ValueError("STORAGE_BUCKET_URL must end with exactly one bucket name")

    bucket = path_parts[s3_index + 1]
    endpoint_path = "/" + "/".join(path_parts[: s3_index + 1])
    endpoint_url = urlunparse(
        (parsed.scheme, parsed.netloc, endpoint_path, "", "", "")
    )

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=os.getenv("STORAGE_REGION", "ap-south-1"),
        aws_access_key_id=os.environ["STORAGE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["STORAGE_SECRET_KEY"],
        config=Config(s3={"addressing_style": "path"}),
    )
    return client, bucket


def upload_pdf(file_name: str, file_bytes: bytes) -> str:
    client, bucket = _storage_location()
    object_key = f"{uuid.uuid4()}/{Path(file_name).name}"
    client.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=file_bytes,
        ContentType="application/pdf",
    )
    return object_key


def download_pdf(object_key: str) -> str:
    client, bucket = _storage_location()
    temporary_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    temporary_file.close()
    try:
        client.download_file(bucket, object_key, temporary_file.name)
    except Exception:
        Path(temporary_file.name).unlink(missing_ok=True)
        raise
    return temporary_file.name
