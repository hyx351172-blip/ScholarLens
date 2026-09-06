# VLM 困难页面修复层

## 目标

当前实现使用 Docling 生成可追溯的 `ContentBlock`，再用确定性规则建立章节、表格、Figure 和公式关系。
VLM 只处理规则无法可靠完成的页面，第一版覆盖：

- 第一页标题为空、过短、为 URL 或通用栏目名时，选择正确的标题 Block。
- 摘要缺失时，选择已有的摘要正文 Block。
- 逻辑表格没有 Caption 时，在同页已有 Block 中选择 Caption。
- 逻辑 Figure 没有 Caption 时，在同页已有 Block 中选择 Caption。
- Docling 将作者明确标注的 Figure 识别为 Table 时，执行受控的 Table→Figure 逻辑重分类。

VLM 不生成或修改表格单元格、正文、公式，也不创建新的 Block。

## 数据流

```text
PDF → Docling → 规则后处理 → 困难页选择 → 页面渲染 → VLM 选择 Block ID
    → 白名单/页码/类型/显式标签/置信度校验 → 修复副本 → Chunker → 保存审计记录
```

原始 `DoclingParseResult` 不会被原地修改。只有满足以下条件的建议才会被接受：

- 所有 Block ID 已存在。
- Object 和 Caption 位于当前页面。
- 普通 Caption 绑定的 Object 类型与 `table` / `figure` 一致，且 Caption 的显式标签不冲突。
- Caption 是允许的文本类型且内容非空。
- 能唯一匹配一个尚未绑定 Caption 的逻辑对象。
- 置信度不低于 `VLM_REPAIR_MIN_CONFIDENCE`。

### 受控语义重分类

当前只允许 `table → figure`，不允许反向转换。建议必须同时满足：

- VLM 使用独立的 `reclassifications` 字段建议转换，不能用普通 Binding 绕过类型校验。
- Object 必须完整、唯一地对应一个未绑定 Caption 的逻辑 Table。
- 所有源 Block 与唯一 Caption Block 必须位于同一页。
- Caption 必须以 `Figure` 或 `Fig.` 加编号开头，包括 `Figure 2` 和 `Figure G.1`。
- VLM 置信度达到阈值，Caption 未绑定到其他对象，且源 Block 尚未被语义重分类。

接受后不会覆盖 Docling 的 `ContentBlock.type`。物理 Block 仍为 `table`，关系字段记录：

```json
{
  "source_type": "table",
  "semantic_type": "figure",
  "classification_source": "vlm_repair",
  "semantic_confidence": 0.98
}
```

对应对象从 `logical_tables` 迁移到 `logical_figures`，Chunker 随后生成 Figure Chunk。原始 Docling
文档和输入的 `DoclingParseResult` 均不原地修改，可通过 `vlm-repair.json` 回溯转换前后的逻辑 ID。

被拒绝的建议与原因会和成功修复一起写入 `vlm-repair.json`。

## 配置

在仓库根目录 `.env` 中配置：

```dotenv
VLM_REPAIR_API_KEY=
VLM_REPAIR_MODEL_NAME=qwen3-vl-plus
VLM_REPAIR_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VLM_REPAIR_MIN_CONFIDENCE=0.8
VLM_REPAIR_MAX_PAGES=8
VLM_REPAIR_RENDER_DPI=144
```

如果专用 API Key、模型或 Base URL 为空，服务分别回退到 `API_KEY`、`MODEL_NAME` 和 `MODEL_URL`。
不开启 VLM 修复时不会初始化客户端，也不会产生模型费用。

## API

上传接口和 `/extract/docling` 均新增表单字段：

```text
enable_vlm_repair=true
```

主上传接口只有在 `extraction_mode=docling` 时使用这个开关。修复发生在结构感知切分之前，因此 Chunker
会消费修复后的 Metadata 和 Caption 关系。

响应中新增：

```json
{
  "metadata": {
    "vlm_repair_performed": true
  },
  "vlm_repair": {
    "schema_version": "1.0",
    "candidate_pages": [1, 7],
    "accepted_repairs": [],
    "rejected_repairs": [],
    "warnings": []
  }
}
```

## 当前边界

- 只做同页 Caption 绑定，不做跨页 Caption 或续表判断。
- 语义重分类仅支持作者显式标注的 Table→Figure；不根据视觉外观猜测，也不支持 Figure→Table。
- 不拆分一个物理 Block 中合并的多个 Figure。
- 不从纯图片页创建新 Block；空页恢复需要单独的 OCR/VLM transcription Feature。
- Figure 解释段仍沿用确定性显式引用规则。
- 自动指标只能证明关系完整性，语义准确率需要人工 Ground Truth 评测。
