import json

import redis

from blotter.config import RedisConfig
from blotter.log import get_logger
from blotter.models import ChunkTask, TranscriptTask

log = get_logger(__name__)

CAPTURE_QUEUE = "blotter:capture:chunks"
TRANSCRIPT_QUEUE = "blotter:transcribe:done"


def get_redis(config: RedisConfig) -> redis.Redis:
    return redis.Redis(host=config.host, port=config.port, db=config.db, decode_responses=True)


def enqueue_chunk(r: redis.Redis, task: ChunkTask) -> None:
    r.lpush(CAPTURE_QUEUE, task.model_dump_json())
    log.debug("enqueued chunk", feed_id=task.feed_id, chunk_index=task.chunk_index)


def dequeue_chunk(r: redis.Redis, timeout: int = 5) -> ChunkTask | None:
    result = r.brpop(CAPTURE_QUEUE, timeout=timeout)
    if result is None:
        return None
    _, data = result
    return ChunkTask.model_validate_json(data)


def enqueue_transcript(r: redis.Redis, task: TranscriptTask) -> None:
    r.lpush(TRANSCRIPT_QUEUE, task.model_dump_json())
    log.debug("enqueued transcript", feed_id=task.feed_id)


def dequeue_transcript(r: redis.Redis, timeout: int = 5) -> TranscriptTask | None:
    result = r.brpop(TRANSCRIPT_QUEUE, timeout=timeout)
    if result is None:
        return None
    _, data = result
    return TranscriptTask.model_validate_json(data)


def queue_depth(r: redis.Redis, queue: str) -> int:
    return r.llen(queue)
