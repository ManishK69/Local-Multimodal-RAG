from arq.connections import RedisSettings

from app.core.config import settings
from app.jobs.ingest import ingest_document


class WorkerSettings:
    functions = [ingest_document]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
