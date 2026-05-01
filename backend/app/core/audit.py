import logging
from datetime import datetime, timezone

logger = logging.getLogger("audit")
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(message)s")
)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def log_access(
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    ip_address: str | None = None,
):
    logger.info(
        "user=%s action=%s resource=%s/%s ip=%s time=%s",
        user_id,
        action,
        resource_type,
        resource_id or "n/a",
        ip_address or "unknown",
        datetime.now(timezone.utc).isoformat(),
    )
