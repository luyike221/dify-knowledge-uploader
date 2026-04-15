import json
import os
import time
from datetime import datetime

import requests

# 知识库 Dataset API Key、知识库 ID、API 基址（需含 /v1，与官方文档一致）
API_KEY = "dataset-Cm9UJQQlWwUoTjn0ycFf5uxr"
DATASET_ID = "0e5a006b-1c1a-41e7-9402-a434cba195b5"
BASE_URL = "http://172.20.62.200:8080/v1"

# 待上传文件所在目录
folder = r"/root/project/project_data"

# 批次：每批文件数、批次与批次之间的间隔（秒）
BATCH_SIZE = 2
BATCH_INTERVAL_SEC = 30

# 失败重试：最多尝试次数（含首次）、两次尝试之间的间隔（秒）
MAX_RETRIES = 3
RETRY_INTERVAL_SEC = 5

# 轮询索引进度配置：轮询间隔、最大等待时间
POLL_INTERVAL_SEC = 2
POLL_TIMEOUT_SEC = 600

# 重试耗尽后仍失败时追加写入的日志（每行一条）
FAIL_LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "dify_upload_failed.txt"
)

# 索引完成但分片为 0 时记录日志（每行一条）
ZERO_SEGMENTS_LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "dify_zero_segments.txt"
)

# 按你的知识库配置对齐（来自创建文档.json 中当前 DATASET_ID 的配置）
EMBEDDING_MODEL_PROVIDER = "langgenius/tongyi/tongyi"
EMBEDDING_MODEL = "multimodal-embedding-v1"
RETRIEVAL_MODEL = {
    "search_method": "hybrid_search",
    "reranking_enable": True,
    "reranking_mode": "reranking_model",
    "reranking_model": {
        "reranking_provider_name": "langgenius/tongyi/tongyi",
        "reranking_model_name": "qwen3-rerank",
    },
    "weights": {
        "weight_type": "customized",
        "keyword_setting": {"keyword_weight": 0.3},
        "vector_setting": {
            "vector_weight": 0.7,
            "embedding_model_name": EMBEDDING_MODEL,
            "embedding_provider_name": EMBEDDING_MODEL_PROVIDER,
        },
    },
    "top_k": 3,
    "score_threshold_enabled": False,
    "score_threshold": 0.5,
}

# 从文件创建文档时，data 为 JSON 字符串；需包含 indexing_technique、process_rule 等（不含 name/text）
# 文档：https://docs.dify.ai/api-reference/%E6%96%87%E6%A1%A3/%E4%BB%8E%E6%96%87%E4%BB%B6%E5%88%9B%E5%BB%BA%E6%96%87%E6%A1%A3
INDEX_CONFIG_PRIMARY = {
    "indexing_technique": "high_quality",
    "doc_form": "hierarchical_model",
    "doc_language": "Chinese",
    "process_rule": {
        "mode": "hierarchical",
        "rules": {
            "segmentation": {"separator": "\n\n", "max_tokens": 2000},
            "parent_mode": "full-doc",
            "subchunk_segmentation": {"separator": "\n", "max_tokens": 512},
            "pre_processing_rules": [{"id": "remove_extra_spaces", "enabled": True}],
        },
    },
    "retrieval_model": RETRIEVAL_MODEL,
}

# 分片为 0 时兜底重传策略（更偏向通用文本切分）
INDEX_CONFIG_FALLBACK = {
    "indexing_technique": "high_quality",
    "doc_form": "text_model",
    "doc_language": "Chinese",
    "process_rule": {
        "mode": "custom",
        "rules": {"pre_processing_rules": [], "segmentation": {"separator": "\n\n", "max_tokens": 500}},
    },
    "retrieval_model": RETRIEVAL_MODEL,
}

headers = {
    "Authorization": f"Bearer {API_KEY}",
}


def build_index_config(base_config: dict) -> dict:
    config = dict(base_config)
    if EMBEDDING_MODEL:
        config["embedding_model"] = EMBEDDING_MODEL
    if EMBEDDING_MODEL_PROVIDER:
        config["embedding_model_provider"] = EMBEDDING_MODEL_PROVIDER
    return config


def append_log(log_path: str, file_path: str, message: str) -> None:
    line = f"{datetime.now().isoformat()}\t{file_path}\t{message.replace(chr(10), ' ')}\n"
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(line)
    print(f"  !! 已写入日志: {log_path}")


def extract_status_item(payload: object) -> dict:
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else {}
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            items = payload.get("data") or []
            return items[0] if items and isinstance(items[0], dict) else {}
        if isinstance(payload.get("data"), dict):
            return payload.get("data") or {}
        return payload
    return {}


def upload_file_once(file_path: str, index_config: dict) -> tuple[bool, str, str]:
    url = f"{BASE_URL.rstrip('/')}/datasets/{DATASET_ID}/document/create-by-file"
    basename = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as f:
            files = {"file": (basename, f)}
            data = {"data": json.dumps(index_config, ensure_ascii=False)}
            response = requests.post(
                url, headers=headers, files=files, data=data, timeout=300
            )
    except requests.RequestException as e:
        return False, "", repr(e)

    print(file_path, response.status_code, response.text)
    if response.ok:
        try:
            body = response.json()
            doc = body.get("document") or {}
            batch = str(body.get("batch") or "")
            print(
                "  -> document_id:",
                doc.get("id"),
                "| batch:",
                batch,
                "| indexing_status:",
                doc.get("indexing_status"),
            )
            return True, batch, ""
        except (ValueError, TypeError):
            return True, "", ""

    return False, "", f"HTTP {response.status_code} {response.text}"


def wait_indexing_result(batch_id: str) -> tuple[bool, int, str]:
    if not batch_id:
        return False, -1, "missing_batch_id"

    status_url = (
        f"{BASE_URL.rstrip('/')}/datasets/{DATASET_ID}/documents/{batch_id}/indexing-status"
    )
    start = time.time()
    last_status = "unknown"

    while time.time() - start <= POLL_TIMEOUT_SEC:
        try:
            response = requests.get(status_url, headers=headers, timeout=30)
        except requests.RequestException as e:
            return False, -1, repr(e)

        if not response.ok:
            return False, -1, f"HTTP {response.status_code} {response.text}"

        try:
            payload = response.json()
        except ValueError as e:
            return False, -1, f"invalid_json: {e}"

        item = extract_status_item(payload)
        last_status = str(item.get("indexing_status") or "unknown")
        completed_segments = int(item.get("completed_segments") or 0)
        total_segments = int(item.get("total_segments") or 0)
        error = item.get("error")
        print(
            "  -> 进度:",
            last_status,
            "| completed_segments:",
            completed_segments,
            "| total_segments:",
            total_segments,
        )

        if last_status == "completed":
            return True, completed_segments, ""
        if last_status in {"error", "paused"}:
            return False, completed_segments, str(error or last_status)

        time.sleep(POLL_INTERVAL_SEC)

    return False, -1, f"poll_timeout_last_status={last_status}"


def upload_file_with_retry(file_path: str) -> bool:
    last_err = ""
    primary_config = build_index_config(INDEX_CONFIG_PRIMARY)
    fallback_config = build_index_config(INDEX_CONFIG_FALLBACK)

    for attempt in range(1, MAX_RETRIES + 1):
        ok, batch_id, err = upload_file_once(file_path, primary_config)
        if ok:
            indexed_ok, completed_segments, index_err = wait_indexing_result(batch_id)
            if indexed_ok:
                if completed_segments == 0:
                    print("  -> 主策略分片为 0，开始兜底策略重传...")
                    fallback_ok, fallback_batch, fallback_err = upload_file_once(
                        file_path, fallback_config
                    )
                    if fallback_ok:
                        f_indexed_ok, f_segments, f_index_err = wait_indexing_result(
                            fallback_batch
                        )
                        if f_indexed_ok and f_segments > 0:
                            print(f"  -> 兜底策略成功，completed_segments={f_segments}")
                            return True
                        if f_indexed_ok and f_segments == 0:
                            append_log(
                                ZERO_SEGMENTS_LOG_PATH,
                                file_path,
                                "primary=0,fallback=0",
                            )
                            return True
                        last_err = f"fallback_indexing_failed: {f_index_err}"
                    else:
                        last_err = f"fallback_upload_failed: {fallback_err}"
                else:
                    return True
            last_err = f"indexing_failed: {index_err}"
        else:
            last_err = err

        print(f"  第 {attempt}/{MAX_RETRIES} 次失败: {last_err}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_INTERVAL_SEC)

    append_log(FAIL_LOG_PATH, file_path, last_err)
    return False


all_files = []
for filename in sorted(os.listdir(folder)):
    file_path = os.path.join(folder, filename)
    if os.path.isfile(file_path):
        all_files.append(file_path)

for batch_start in range(0, len(all_files), BATCH_SIZE):
    batch = all_files[batch_start : batch_start + BATCH_SIZE]
    batch_no = batch_start // BATCH_SIZE + 1
    print(f"--- 批次 {batch_no}，共 {len(batch)} 个文件 ---")
    for file_path in batch:
        try:
            upload_file_with_retry(file_path)
        except Exception as e:  # 防御性兜底：单文件异常不影响后续
            append_log(FAIL_LOG_PATH, file_path, f"unexpected_error: {repr(e)}")
            continue

    if batch_start + BATCH_SIZE < len(all_files):
        print(f"批次间隔 {BATCH_INTERVAL_SEC}s …")
        time.sleep(BATCH_INTERVAL_SEC)
