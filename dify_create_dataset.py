import json
from datetime import datetime

import requests

# =========================
# 基础配置（与 dify_upload.py 对齐）
# =========================
# dify知识库(1.13及以上版本) -> 服务IP 
API_KEY = "dataset-Cm9UJQQlWwUoTjn0ycFf5uxr"
BASE_URL = "http://172.20.62.200:8080/v1"

# 新知识库名称（建议每次唯一，避免重名 409）
DATASET_NAME = f"目录示意-自动创建-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
DESCRIPTION = "useful for when you want to answer queries about uploaded markdown files"

# 与你现有配置对齐
INDEXING_TECHNIQUE = "high_quality"
PERMISSION = "only_me"
PROVIDER = "vendor"
EMBEDDING_MODEL = "multimodal-embedding-v1"
EMBEDDING_MODEL_PROVIDER = "langgenius/tongyi/tongyi"

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


def build_payload() -> dict:
    # 创建空知识库接口不需要 doc_form；后续首次建文档时由文档参数决定分段结构。
    return {
        "name": DATASET_NAME,
        "description": DESCRIPTION,
        "indexing_technique": INDEXING_TECHNIQUE,
        "permission": PERMISSION,
        "provider": PROVIDER,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_provider": EMBEDDING_MODEL_PROVIDER,
        "retrieval_model": RETRIEVAL_MODEL,
    }


def create_dataset() -> None:
    url = f"{BASE_URL.rstrip('/')}/datasets"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = build_payload()

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        print("请求失败:", repr(e))
        return

    print("status_code:", response.status_code)
    print("response:", response.text)

    if response.status_code == 409:
        print("提示: 知识库名称重复，请修改 DATASET_NAME 后重试。")
        return

    if not response.ok:
        print("创建失败，请检查参数或服务端报错。")
        return

    try:
        body = response.json()
    except ValueError:
        print("创建成功，但响应不是 JSON。")
        return

    print("\n创建成功:")
    print("dataset_id:", body.get("id"))
    print("name:", body.get("name"))
    print("indexing_technique:", body.get("indexing_technique"))
    print("embedding_model:", body.get("embedding_model"))
    print("embedding_model_provider:", body.get("embedding_model_provider"))
    print("retrieval_model_dict:", json.dumps(body.get("retrieval_model_dict"), ensure_ascii=False))


if __name__ == "__main__":
    create_dataset()
