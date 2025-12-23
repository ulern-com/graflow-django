
from django.db import models
from django.utils import timezone


class Store(models.Model):
    """
    LangGraph's store table used as the long-term memory shared between threads.

    For how to use long-term memory, see https://docs.langchain.com/oss/python/langgraph/add-memory#add-long-term-memory
    We need to keep the Store model consistent with the LangGraph's implementation.
    For the schema, table name, indexes and other constraints, refer to the following file:
    https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/langgraph/store/postgres/base.py
    """

    prefix = models.TextField()
    key = models.TextField()
    value = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    ttl_minutes = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "store"  # Should match the LangGraph's implementation.
        indexes = [
            models.Index(fields=["prefix"], name="store_prefix_idx"),
            models.Index(fields=["expires_at"], name="store_expires_at_idx"),
        ]
        unique_together = (("prefix", "key"),)

    def __str__(self):
        return f"Store(prefix={self.prefix}, key={self.key})"


# TODO: Add vector_store table. See these:
# https://docs.langchain.com/oss/python/langgraph/add-memory#use-semantic-search
# https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/langgraph/store/postgres/base.py


class Checkpoint(models.Model):
    """
    This is the primary table to make checkpointing possible and works like a timeline
    of snapshots (super-steps).

    For the schema, table name, indexes and other constraints, see:
    https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py
    """

    thread_id = models.TextField()
    checkpoint_ns = models.TextField(default="")
    checkpoint_id = models.TextField()  # monotonic ID per thread/NS
    parent_checkpoint_id = models.TextField(null=True, blank=True)  # for history/lineage
    type = models.TextField(null=True, blank=True)
    checkpoint = models.JSONField()  # Mapping of channels to versions
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "checkpoints"  # Should match the LangGraph's implementation.
        indexes = [
            models.Index(fields=["thread_id"], name="checkpoints_thread_id_idx"),
        ]
        unique_together = (("thread_id", "checkpoint_ns", "checkpoint_id"),)


class CheckpointBlob(models.Model):
    """
    Stores actual data for each channel and version.

    A channel = a named component of the graph's state, persisted independently. For example in
    state = {
        "messages": [...],
        "user_profile": {...},
    }
    messages and user_profile are channels.

    A version = a snapshot identifier for one channel. They are used to reconstruct
    the full state at a checkpoint.

    Relationship to checkpoints:
    - The row in checkpoints has something like: "
    "checkpoint.channel_versions = {\"messages\": \"v5\", \"user_profile\": \"v2\"}
    - To reconstruct the full state at that checkpoint, LangGraph: looks up each
    (thread_id, checkpoint_ns, channel, version) in checkpoint_blobs, "
    "deserializes the blobs, assembles them into the channel state.
    """

    thread_id = models.TextField()
    checkpoint_ns = models.TextField(default="")
    channel = models.TextField()
    version = models.TextField()
    type = models.TextField()  # null, empty or msgpack
    blob = models.BinaryField(null=True, blank=True)  # The actual binary data

    class Meta:
        db_table = "checkpoint_blobs"  # Should match the LangGraph's implementation.
        indexes = [
            models.Index(fields=["thread_id"], name="checkpoint_blobs_thread_id_idx"),
        ]
        unique_together = (("thread_id", "checkpoint_ns", "channel", "version"),)


class CheckpointWrite(models.Model):
    """
    Stores writes produced by tasks that are not yet consolidated into a new checkpoint,
    i.e. intermediate or pending changes.
    """

    thread_id = models.TextField()
    checkpoint_ns = models.TextField(default="")
    checkpoint_id = models.TextField()
    task_id = models.TextField()
    idx = models.IntegerField()  # ordering for multiple writes from same task
    channel = models.TextField()
    type = models.TextField(null=True, blank=True)
    blob = models.BinaryField(null=True, blank=True)
    task_path = models.TextField(default="")

    class Meta:
        db_table = "checkpoint_writes"  # Should match the LangGraph's implementation.
        indexes = [
            models.Index(fields=["thread_id"], name="checkpoint_writes_thrd_id_idx"),
        ]
        unique_together = (("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"),)


class CacheEntry(models.Model):
    """
    LangGraph's cache table for storing cached values with TTL support.

    LangGraph doesn't have a DB-based node cache implementation. But in some cases,
    especially when nodes are LLM calls, it's possible to cache generated responses
    to avoid redundant LLM calls with the same exact context. It should be done
    carefully to make sure the all the context of LLM calls is captured in the cache
    key, otherwise the cached response will be incorrect and it'll be hard to debug.
    InMemoryCache or RedisCache can be used beside DB-based caching.
    """

    namespace = models.TextField()  # JSON-encoded namespace tuple
    key = models.TextField()
    value_encoding = models.TextField()  # Serialization format
    value_data = models.BinaryField()  # Serialized value
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "graflow_cache_entry"
        indexes = [
            models.Index(fields=["namespace"], name="cache_namespace_idx"),
            models.Index(fields=["expires_at"], name="cache_expires_at_idx"),
        ]
        unique_together = (("namespace", "key"),)

    def __str__(self):
        return f"CacheEntry(namespace={self.namespace}, key={self.key})"

    def is_expired(self):
        """Check if the cache entry has expired."""
        if self.expires_at is None:
            return False
        return timezone.now() >= self.expires_at
