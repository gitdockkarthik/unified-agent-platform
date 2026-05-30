from datetime import datetime, timezone

from fastapi import APIRouter

import kafka_store
from tools.synthetic import SyntheticCollector

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate-sample")
async def generate_sample() -> dict:
    """Generate synthetic Kafka cluster data and load into the in-memory store."""
    collector = SyntheticCollector()
    data = await collector.collect()
    kafka_store.set_cluster_data(data, source_type="synthetic")
    meta = kafka_store.get_sync_meta()
    return {
        "ok": True,
        "message": (
            f"Synthetic data loaded — {meta['broker_count']} brokers, "
            f"{meta['consumer_group_count']} consumer groups, "
            f"{meta['topic_count']} topics, "
            f"{meta['connector_count']} connectors"
        ),
        **meta,
    }


@router.get("")
async def list_reports() -> dict:
    """Return current sync metadata."""
    return kafka_store.get_sync_meta()
