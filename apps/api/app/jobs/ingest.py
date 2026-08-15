from arq import create_pool
from arq.connections import RedisSettings
from arq.constants import default_queue_name, job_key_prefix, result_key_prefix

from app.core.config import settings


def ingest_job_id(document_id: int) -> str:
    return f"ingest-document-{document_id}"


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def _drop_job(redis, document_id: int) -> None:
    job_id = ingest_job_id(document_id)
    await redis.delete(job_key_prefix + job_id, result_key_prefix + job_id)
    await redis.zrem(default_queue_name, job_id)


async def enqueue_ingest(document_id: int) -> str:
    redis = await create_pool(_redis_settings())
    try:
        await _drop_job(redis, document_id)
        job_id = ingest_job_id(document_id)
        job = await redis.enqueue_job(
            "ingest_document",
            document_id,
            _job_id=job_id,
        )
        return job.job_id if job is not None else job_id
    finally:
        await redis.aclose()


async def abort_ingest(document_id: int) -> None:
    redis = await create_pool(_redis_settings())
    try:
        await _drop_job(redis, document_id)
    except Exception:
        return
    finally:
        await redis.aclose()
