# Dify 知识库创建与批量上传

通过 Dify **Dataset（知识库）API**，先创建空知识库，再批量上传本地文件并等待索引进度。适用于 Dify 知识库 **1.13 及以上**版本（`BASE_URL` 需带 `/v1`，与[官方文档](https://docs.dify.ai)一致）。

## 环境要求

- Python 3.8+
- 依赖：`requests`

```bash
pip install requests
```

## 使用流程

1. **创建知识库**：运行 `dify_create_dataset.py`，在 Dify 中创建一个新的空数据集（知识库）。
2. **上传文档**：将脚本里输出的 `dataset_id` 填到 `dify_upload.py` 的 `DATASET_ID`，配置待上传目录后运行 `dify_upload.py`，将文件批量上传到该知识库。

两个脚本中的 `API_KEY`、`BASE_URL`、嵌入与检索模型等需**保持一致**，并与你在 Dify 控制台中实际启用的模型、供应商一致。

## `dify_create_dataset.py`（创建知识库）

| 配置项 | 说明 |
|--------|------|
| `API_KEY` | 知识库的 Dataset API Key（Bearer） |
| `BASE_URL` | 服务地址，形如 `http://<host>:<port>/v1` |
| `DATASET_NAME` | 新知识库名称；脚本默认带时间戳，避免重名导致 **409** |
| `DESCRIPTION` | 知识库描述 |
| `INDEXING_TECHNIQUE` / `PERMISSION` / `PROVIDER` | 与 Dify 创建知识库接口一致 |
| `EMBEDDING_MODEL` / `EMBEDDING_MODEL_PROVIDER` | 嵌入模型及供应商 |
| `RETRIEVAL_MODEL` | 检索配置（混合检索、重排等） |

运行：

```bash
python dify_create_dataset.py
```

成功时终端会打印 `dataset_id`、`name` 等。若返回 **409**，说明名称冲突，请修改 `DATASET_NAME` 后重试。

## `dify_upload.py`（批量上传）

| 配置项 | 说明 |
|--------|------|
| `API_KEY` | 与目标知识库相同的 Dataset API Key |
| `DATASET_ID` | 上一步创建成功后得到的知识库 ID |
| `BASE_URL` | 与创建脚本一致 |
| `folder` | 待上传文件所在目录（脚本会遍历该目录下**文件**，不递归子目录） |
| `BATCH_SIZE` / `BATCH_INTERVAL_SEC` | 每批文件数量与批次间隔，用于限流 |
| `MAX_RETRIES` / `RETRY_INTERVAL_SEC` | 单文件上传与索引失败时的重试次数与间隔 |
| `POLL_INTERVAL_SEC` / `POLL_TIMEOUT_SEC` | 索引进度轮询间隔与最长等待时间 |
| `INDEX_CONFIG_PRIMARY` / `INDEX_CONFIG_FALLBACK` | 主索引策略（层级分段等）与分片为 0 时的兜底策略 |

运行：

```bash
python dify_upload.py
```

### 行为说明

- 调用接口：[从文件创建文档](https://docs.dify.ai/api-reference/%E6%96%87%E6%A1%A3/%E4%BB%8E%E6%96%87%E4%BB%B6%E5%88%9B%E5%BB%BA%E6%96%87%E6%A1%A3)（`document/create-by-file`）。
- 上传后会轮询索引状态；若主策略索引完成但 **completed_segments 为 0**，会自动用兜底配置再传一次。
- 失败记录：`dify_upload_failed.txt`（项目脚本同目录）。
- 主策略与兜底均为 0 分片时：`dify_zero_segments.txt`。

