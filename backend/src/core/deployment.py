import hashlib
from src.core.settings import settings


def worker_heartbeat_key():
    # Workers for a different database must never make this API appear ready.
    identity=hashlib.sha256(settings.database_url.encode()).hexdigest()[:16]
    return 'devreason:worker:heartbeat:'+identity
