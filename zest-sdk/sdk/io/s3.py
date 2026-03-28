import hashlib
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from sdk.io.base import FileStore


logger = logging.getLogger(__name__)


class S3FileStoreConfig:
    """Configuration for S3FileStore."""

    def __init__(
        self,
        bucket_name: str,
        region_name: str = "us-east-1",
        prefix: str = "",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        lock_timeout: float = 30.0,
        use_dynamodb_lock: bool = False,
        dynamodb_table_name: str | None = None,
    ):
        """Initialize S3FileStore configuration.

        Args:
          bucket_name: S3 bucket name.
          region_name: AWS region name.
          prefix: Prefix for all S3 keys (e.g., "data/").
          access_key_id: AWS access key ID (uses default credentials if None).
          secret_access_key: AWS secret access key.
          endpoint_url: Custom S3 endpoint URL (for S3-compatible services).
          max_retries: Maximum number of retry attempts.
          retry_delay: Initial delay between retries in seconds.
          lock_timeout: Default timeout for lock acquisition.
          use_dynamodb_lock: Whether to use DynamoDB for distributed locking.
          dynamodb_table_name: DynamoDB table name for locks.
        """
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.prefix = prefix.rstrip("/") if prefix else ""
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.endpoint_url = endpoint_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.lock_timeout = lock_timeout
        self.use_dynamodb_lock = use_dynamodb_lock
        self.dynamodb_table_name = dynamodb_table_name


class S3FileStore(FileStore):
    """S3-based file storage implementation.

    This implementation provides file storage operations backed by AWS S3.
    It includes retry logic, error handling, and distributed locking support.
    """

    def __init__(self, config: S3FileStoreConfig):
        """Initialize S3FileStore.

        Args:
          config: S3FileStoreConfig instance.

        Raises:
          ValueError: If configuration is invalid.
        """
        self.config = config
        self._local_locks = {}  # For in-process locking
        self._lock = threading.Lock()

        # Initialize S3 client
        session_kwargs = {}
        if config.access_key_id and config.secret_access_key:
            session_kwargs = {
                "aws_access_key_id": config.access_key_id,
                "aws_secret_access_key": config.secret_access_key,
            }

        session = boto3.Session(**session_kwargs)

        # Configure S3 client with retry policy
        s3_config = Config(
            retries={"max_attempts": config.max_retries, "mode": "adaptive"},
            max_pool_connections=50,
        )

        self.s3_client = session.client(
            "s3",
            region_name=config.region_name,
            endpoint_url=config.endpoint_url,
            config=s3_config,
        )

        # Initialize DynamoDB client if using DynamoDB locks
        if config.use_dynamodb_lock:
            self.dynamodb_client = session.client(
                "dynamodb",
                region_name=config.region_name,
            )
        else:
            self.dynamodb_client = None

        logger.info(
            f"S3FileStore initialized with bucket={config.bucket_name}, "
            f"prefix={config.prefix}, region={config.region_name}"
        )

    def _get_s3_key(self, path: str) -> str:
        """Convert a relative path to an S3 key.

        Args:
          path: Relative path.

        Returns:
          S3 key with prefix applied.
        """
        # Normalize path
        path = path.lstrip("/")

        if self.config.prefix:
            return f"{self.config.prefix}/{path}"
        return path

    def _normalize_path(self, path: str) -> str:
        """Normalize a path by removing leading/trailing slashes.

        Args:
          path: Path to normalize.

        Returns:
          Normalized path.
        """
        return path.strip("/")

    def write(self, path: str, contents: str | bytes, **kwargs) -> None:
        """Write contents to a file at the specified path.

        Args:
          path: The file path where contents should be written.
          contents: The data to write, either as string or bytes.
          **kwargs: Additional arguments:
            - metadata: dict of metadata to attach to the object
            - content_type: MIME type of the content
            - acl: S3 ACL (e.g., "private", "public-read")

        Raises:
          IOError: If write operation fails.
        """
        if not path:
            raise ValueError("Path cannot be empty")

        s3_key = self._get_s3_key(path)

        # Convert string to bytes if necessary
        if isinstance(contents, str):
            body = contents.encode("utf-8")
        else:
            body = contents

        # Prepare put_object parameters
        put_kwargs = {
            "Bucket": self.config.bucket_name,
            "Key": s3_key,
            "Body": body,
        }

        # Add optional parameters
        if "metadata" in kwargs:
            put_kwargs["Metadata"] = kwargs["metadata"]
        if "content_type" in kwargs:
            put_kwargs["ContentType"] = kwargs["content_type"]
        if "acl" in kwargs:
            put_kwargs["ACL"] = kwargs["acl"]

        try:
            self.s3_client.put_object(**put_kwargs)
            logger.debug(
                f"Successfully wrote to S3: s3://{self.config.bucket_name}/{s3_key}"
            )
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to write to S3 path {path}: {e}")
            raise OSError(f"Failed to write to S3: {e}") from e

    def read(self, path: str, **kwargs) -> str:
        """Read and return the contents of a file as a string.

        Args:
          path: The file path to read from.
          **kwargs: Additional arguments (reserved for future use).

        Returns:
          The file contents as a string.

        Raises:
          FileNotFoundError: If the file does not exist.
          IOError: If read operation fails.
        """
        if not path:
            raise ValueError("Path cannot be empty")

        s3_key = self._get_s3_key(path)

        try:
            response = self.s3_client.get_object(
                Bucket=self.config.bucket_name,
                Key=s3_key,
            )
            contents = response["Body"].read().decode("utf-8")
            logger.debug(
                f"Successfully read from S3: s3://{self.config.bucket_name}/{s3_key}"
            )
            return contents
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning(f"File not found in S3: {path}")
                raise FileNotFoundError(f"File not found: {path}") from e
            logger.error(f"Failed to read from S3 path {path}: {e}")
            raise OSError(f"Failed to read from S3: {e}") from e
        except BotoCoreError as e:
            logger.error(f"Failed to read from S3 path {path}: {e}")
            raise OSError(f"Failed to read from S3: {e}") from e

    def list(self, path: str) -> list[str]:
        """List all files and directories at the specified path.

        Args:
          path: The directory path to list contents from.

        Returns:
          A list of file and directory names in the specified path.

        Raises:
          IOError: If list operation fails.
        """
        path = self._normalize_path(path)
        prefix = self._get_s3_key(path)

        # Ensure prefix ends with / for directory listing
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        items = []
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(
                Bucket=self.config.bucket_name,
                Prefix=prefix,
                Delimiter="/",
            )

            for page in pages:
                # Add files
                if "Contents" in page:
                    for obj in page["Contents"]:
                        key = obj["Key"]
                        # Remove prefix to get relative path
                        if key.startswith(prefix):
                            relative_key = key[len(prefix) :]
                            if relative_key:  # Skip empty keys
                                items.append(relative_key)

                # Add directories
                if "CommonPrefixes" in page:
                    for prefix_info in page["CommonPrefixes"]:
                        dir_name = prefix_info["Prefix"][len(prefix) :].rstrip("/")
                        if dir_name:
                            items.append(dir_name + "/")

            logger.debug(f"Listed {len(items)} items in S3 path: {path}")
            return items
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to list S3 path {path}: {e}")
            raise OSError(f"Failed to list S3 path: {e}") from e

    def delete(self, path: str) -> None:
        """Delete the file or directory at the specified path.

        Args:
          path: The file or directory path to delete.

        Raises:
          IOError: If delete operation fails.
        """
        if not path:
            raise ValueError("Path cannot be empty")

        path = self._normalize_path(path)
        s3_key = self._get_s3_key(path)

        try:
            # Check if it's a directory (ends with /)
            if path.endswith("/") or not self._is_file(s3_key):
                # Delete directory and all contents
                self._delete_directory(s3_key)
            else:
                # Delete single file
                self.s3_client.delete_object(
                    Bucket=self.config.bucket_name,
                    Key=s3_key,
                )
                logger.debug(f"Deleted file from S3: {path}")
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to delete S3 path {path}: {e}")
            raise OSError(f"Failed to delete S3 path: {e}") from e

    def _is_file(self, s3_key: str) -> bool:
        """Check if S3 key is a file (not a directory).

        Args:
          s3_key: S3 key to check.

        Returns:
          True if it's a file, False otherwise.
        """
        try:
            self.s3_client.head_object(
                Bucket=self.config.bucket_name,
                Key=s3_key,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def _delete_directory(self, prefix: str) -> None:
        """Delete all objects with the given prefix.

        Args:
          prefix: S3 prefix to delete.
        """
        if not prefix.endswith("/"):
            prefix += "/"

        paginator = self.s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=self.config.bucket_name,
            Prefix=prefix,
        )

        for page in pages:
            if "Contents" in page:
                delete_request = {
                    "Objects": [{"Key": obj["Key"]} for obj in page["Contents"]]
                }
                self.s3_client.delete_objects(
                    Bucket=self.config.bucket_name,
                    Delete=delete_request,
                )

        logger.debug(f"Deleted directory from S3: {prefix}")

    def exists(self, path: str) -> bool:
        """Check if a file or directory exists at the specified path.

        Args:
          path: The file or directory path to check.

        Returns:
          True if the path exists, False otherwise.
        """
        if not path:
            return False

        path = self._normalize_path(path)
        s3_key = self._get_s3_key(path)

        try:
            # Try to get the object
            self.s3_client.head_object(
                Bucket=self.config.bucket_name,
                Key=s3_key,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                # Check if it's a directory
                if not s3_key.endswith("/"):
                    s3_key += "/"

                try:
                    response = self.s3_client.list_objects_v2(
                        Bucket=self.config.bucket_name,
                        Prefix=s3_key,
                        MaxKeys=1,
                    )
                    return "Contents" in response
                except (ClientError, BotoCoreError):
                    return False
            return False
        except BotoCoreError:
            return False

    def get_absolute_path(self, path: str) -> str:
        """Get the absolute S3 path for a given relative path.

        Args:
          path: The relative path within the file store.

        Returns:
          The absolute S3 path (s3://bucket/key).
        """
        path = self._normalize_path(path)
        s3_key = self._get_s3_key(path)
        return f"s3://{self.config.bucket_name}/{s3_key}"

    @contextmanager
    def lock(self, path: str, timeout: float = 30.0) -> Iterator[None]:
        """Acquire an exclusive lock for the given path.

        This implementation supports both local (in-process) and distributed
        (DynamoDB-based) locking.

        Args:
          path: The path to lock (used to identify the lock).
          timeout: Maximum seconds to wait for lock acquisition.

        Yields:
          None when lock is acquired.

        Raises:
          TimeoutError: If lock cannot be acquired within timeout.
        """
        if self.config.use_dynamodb_lock:
            with self._acquire_dynamodb_lock(path, timeout):
                yield
        else:
            with self._acquire_local_lock(path, timeout):
                yield

    @contextmanager
    def _acquire_local_lock(self, path: str, timeout: float) -> Iterator[None]:
        """Acquire a local (in-process) lock.

        Args:
          path: The path to lock.
          timeout: Maximum seconds to wait for lock acquisition.

        Yields:
          None when lock is acquired.

        Raises:
          TimeoutError: If lock cannot be acquired within timeout.
        """
        lock_id = hashlib.md5(path.encode()).hexdigest()
        start_time = time.time()

        with self._lock:
            if lock_id not in self._local_locks:
                self._local_locks[lock_id] = threading.Lock()
            local_lock = self._local_locks[lock_id]

        # Try to acquire the lock with timeout
        acquired = local_lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(
                f"Failed to acquire lock for path {path} within {timeout}s"
            )

        try:
            logger.debug(f"Acquired local lock for path: {path}")
            yield
        finally:
            local_lock.release()
            logger.debug(f"Released local lock for path: {path}")

    @contextmanager
    def _acquire_dynamodb_lock(self, path: str, timeout: float) -> Iterator[None]:
        """Acquire a distributed lock using DynamoDB.

        Args:
          path: The path to lock.
          timeout: Maximum seconds to wait for lock acquisition.

        Yields:
          None when lock is acquired.

        Raises:
          TimeoutError: If lock cannot be acquired within timeout.
        """
        if not self.dynamodb_client or not self.config.dynamodb_table_name:
            raise RuntimeError("DynamoDB client not configured for distributed locking")

        lock_id = hashlib.md5(path.encode()).hexdigest()
        lock_key = f"lock#{lock_id}"
        start_time = time.time()
        lock_acquired = False

        try:
            while time.time() - start_time < timeout:
                try:
                    # Try to create a lock item with TTL
                    self.dynamodb_client.put_item(
                        TableName=self.config.dynamodb_table_name,
                        Item={
                            "lock_id": {"S": lock_key},
                            "owner": {"S": f"{threading.current_thread().ident}"},
                            "acquired_at": {"N": str(int(time.time()))},
                            "ttl": {"N": str(int(time.time()) + 300)},  # 5 minute TTL
                        },
                        ConditionExpression="attribute_not_exists(lock_id)",
                    )
                    lock_acquired = True
                    logger.debug(f"Acquired DynamoDB lock for path: {path}")
                    break
                except ClientError as e:
                    if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                        raise
                    # Lock is held by someone else, wait and retry
                    time.sleep(0.1)

            if not lock_acquired:
                raise TimeoutError(
                    f"Failed to acquire DynamoDB lock for path {path} within {timeout}s"
                )

            yield
        finally:
            if lock_acquired:
                try:
                    self.dynamodb_client.delete_item(
                        TableName=self.config.dynamodb_table_name,
                        Key={"lock_id": {"S": lock_key}},
                    )
                    logger.debug(f"Released DynamoDB lock for path: {path}")
                except ClientError as e:
                    logger.error(f"Failed to release DynamoDB lock: {e}")


# Example usage and configuration
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Example 1: Basic S3 file store
    config = S3FileStoreConfig(
        bucket_name="my-bucket",
        region_name="us-east-1",
        prefix="data",
    )
    store = S3FileStore(config)

    # Write a file
    store.write("test.txt", "Hello, S3!")

    # Read the file
    content = store.read("test.txt")
    print(f"Content: {content}")

    # List files
    files = store.list("")
    print(f"Files: {files}")

    # Check if file exists
    exists = store.exists("test.txt")
    print(f"File exists: {exists}")

    # Use lock
    with store.lock("test.txt", timeout=10.0):
        print("Lock acquired!")
        store.write("test.txt", "Updated content")

    # Get absolute path
    abs_path = store.get_absolute_path("test.txt")
    print(f"Absolute path: {abs_path}")

    # Delete file
    store.delete("test.txt")
