/**
 * 前端环境配置
 * 从环境变量读取API地址，如果没有则使用默认值
 */

export const config = {
  // Milvus API 服务地址
  milvusApiUrl: import.meta.env.VITE_MILVUS_API_URL || 'http://localhost:8000',

  // Chat 对话服务地址
  chatApiUrl: import.meta.env.VITE_CHAT_API_URL || 'http://localhost:8501',

  // PDF 提取服务地址
  extractionApiUrl: import.meta.env.VITE_EXTRACTION_API_URL || 'http://localhost:8006',

  // 切分服务地址
  chunkApiUrl: import.meta.env.VITE_CHUNK_API_URL || 'http://localhost:8001',
} as const;

// 导出便捷方法
export const getApiUrl = (service: keyof typeof config): string => {
  return config[service];
};
