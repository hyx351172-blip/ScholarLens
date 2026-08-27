import { useState, useEffect } from 'react';
import { X, Upload, FileText, Settings, AlertCircle, CheckCircle, Loader2, Plus } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { toast } from 'sonner';

interface UploadDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (files: File[], kbId: string, config: UploadConfig) => void;
  preselectedKB?: string; // 预选的知识库ID
}

interface UploadConfig {
  extractionMode: 'fast' | 'vlm';
  chunkSize: number;
  overlap: number;
  maxPageSpan: number;
  bridgeLength: number;
  chunkingMethod: string;
}

interface KnowledgeBase {
  collection_id: string;
  collection_name: string;
  total_documents: number;
  total_chunks: number;
}

export function UploadDialog({ isOpen, onClose, onUpload, preselectedKB }: UploadDialogProps) {
  const [selectedKB, setSelectedKB] = useState<string | null>(preselectedKB || null);
  const [files, setFiles] = useState<File[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ [key: string]: string }>({});
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreateKB, setShowCreateKB] = useState(false);
  const [newKBName, setNewKBName] = useState('');
  const [config, setConfig] = useState<UploadConfig>({
    extractionMode: 'fast',
    chunkSize: 1500,
    overlap: 200,
    maxPageSpan: 3,
    bridgeLength: 100,
    chunkingMethod: 'header_recursive',
  });

  // 从Milvus API获取知识库列表
  useEffect(() => {
    if (isOpen) {
      fetchKnowledgeBases();
    }
  }, [isOpen]);

  // 当预选知识库变化时更新选中状态
  useEffect(() => {
    if (preselectedKB) {
      setSelectedKB(preselectedKB);
    }
  }, [preselectedKB]);

  const fetchKnowledgeBases = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/stats/all');
      const result = await response.json();

      if (result.status === 'success') {
        setKnowledgeBases(result.data.collections || []);
      }
    } catch (error) {
      console.error('获取知识库列表失败:', error);
      toast.error('获取知识库列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateKB = async () => {
    if (!newKBName.trim()) {
      toast.error('请输入知识库名称');
      return;
    }

    try {
      const response = await fetch(
        `http://localhost:8000/knowledge_base/create?display_name=${encodeURIComponent(newKBName)}`,
        { method: 'POST' }
      );
      const result = await response.json();

      if (result.status === 'success') {
        toast.success(result.message);
        setShowCreateKB(false);
        setNewKBName('');
        // 刷新列表并自动选中新创建的知识库
        await fetchKnowledgeBases();
        setSelectedKB(result.collection_id);
      } else {
        toast.error(result.message || '创建知识库失败');
      }
    } catch (error) {
      console.error('创建知识库失败:', error);
      toast.error('创建知识库失败');
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files) {
      setFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleSubmit = async () => {
    if (!selectedKB || files.length === 0) return;

    setUploading(true);
    const API_BASE_URL = 'http://localhost:8006';

    try {
      // 逐个上传文件
      for (const file of files) {
        setUploadProgress((prev) => ({ ...prev, [file.name]: 'uploading' }));

        const formData = new FormData();
        formData.append('file', file);
        formData.append('knowledge_base_id', selectedKB);  // 直接使用collection_id
        formData.append('auto_extract', 'true');
        formData.append('extraction_mode', config.extractionMode);
        formData.append('auto_chunk', 'true');
        formData.append('chunking_method', config.chunkingMethod);
        formData.append('chunk_size', config.chunkSize.toString());
        formData.append('chunk_overlap', config.overlap.toString());
        formData.append('max_page_span', config.maxPageSpan.toString());

        try {
          const response = await fetch(`${API_BASE_URL}/api/v1/files/upload`, {
            method: 'POST',
            body: formData,
          });

          const result = await response.json();

          if (result.success) {
            setUploadProgress((prev) => ({ ...prev, [file.name]: 'success' }));

            // 构建成功消息
            let description = '文件已保存';
            if (result.data.extraction?.status === 'completed') {
              const pages = result.data.extraction.total_pages;
              const images = result.data.extraction.total_images;
              description = `已提取 ${pages} 页`;
              if (images > 0) {
                description += `，${images} 张图片`;
              }

              // 如果有切分结果
              if (result.data.chunking?.status === 'completed') {
                const chunks = result.data.chunking.total_chunks;
                description += `，已切分为 ${chunks} 个块`;
              }
            }

            toast.success(`${file.name} 上传成功`, {
              description,
            });
          } else {
            setUploadProgress((prev) => ({ ...prev, [file.name]: 'error' }));
            toast.error(`${file.name} 上传失败`, {
              description: result.error?.message || '未知错误',
            });
          }
        } catch (error) {
          setUploadProgress((prev) => ({ ...prev, [file.name]: 'error' }));
          toast.error(`${file.name} 上传失败`, {
            description: error instanceof Error ? error.message : '网络错误',
          });
        }
      }

      // 所有文件上传完成后，调用父组件的回调
      onUpload(files, selectedKB, config);

      // 延迟关闭对话框，让用户看到结果
      setTimeout(() => {
        onClose();
        setFiles([]);
        setUploadProgress({});
      }, 1500);

    } catch (error) {
      toast.error('上传过程中发生错误', {
        description: error instanceof Error ? error.message : '请稍后重试',
      });
    } finally {
      setUploading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        />

        {/* Dialog */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="relative w-full max-w-3xl max-h-[90vh] overflow-hidden glass-strong rounded-2xl border border-[rgba(0,212,255,0.3)] shadow-[0_0_50px_rgba(0,212,255,0.3)]"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-[rgba(0,212,255,0.15)]">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff] to-[#0066ff] flex items-center justify-center">
                <Upload size={20} className="text-[#0a0e27]" />
              </div>
              <h2 className="text-xl text-[#e8eaed]">上传文档</h2>
            </div>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg hover:bg-[rgba(0,212,255,0.1)] transition-colors flex items-center justify-center text-[#94a3b8] hover:text-[#e8eaed]"
            >
              <X size={20} />
            </button>
          </div>

          {/* Content */}
          <div className="p-6 overflow-y-auto max-h-[calc(90vh-180px)]">
            <div className="space-y-6">
              {/* Knowledge Base Selection */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-[#e8eaed] flex items-center gap-2">
                    <FileText size={16} />
                    选择知识库
                  </label>
                  <motion.button
                    onClick={() => setShowCreateKB(!showCreateKB)}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm border border-[#00d4ff] text-[#00d4ff] rounded-lg hover:bg-[rgba(0,212,255,0.1)] transition-all"
                  >
                    <Plus size={14} />
                    新建知识库
                  </motion.button>
                </div>

                {/* Create KB Input */}
                <AnimatePresence>
                  {showCreateKB && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="flex gap-2 p-3 glass rounded-xl border border-[rgba(0,212,255,0.2)]">
                        <input
                          type="text"
                          value={newKBName}
                          onChange={(e) => setNewKBName(e.target.value)}
                          placeholder="输入知识库名称（支持中文）"
                          className="flex-1 px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] placeholder-[#94a3b8]"
                          onKeyDown={(e) => e.key === 'Enter' && handleCreateKB()}
                          autoFocus
                        />
                        <motion.button
                          onClick={handleCreateKB}
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          className="px-4 py-2 bg-gradient-to-r from-[#00d4ff] to-[#0066ff] text-[#0a0e27] rounded-lg hover:shadow-[0_0_20px_rgba(0,212,255,0.5)] transition-all"
                        >
                          创建
                        </motion.button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* KB List */}
                {loading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 size={24} className="text-[#00d4ff] animate-spin" />
                  </div>
                ) : knowledgeBases.length === 0 ? (
                  <div className="text-center py-8 text-[#94a3b8]">
                    暂无知识库，请先创建一个
                  </div>
                ) : (
                  <div className="grid grid-cols-3 gap-3">
                    {knowledgeBases.map((kb) => (
                      <motion.button
                        key={kb.collection_id}
                        onClick={() => setSelectedKB(kb.collection_id)}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        className={`p-4 rounded-xl border-2 transition-all text-left ${
                          selectedKB === kb.collection_id
                            ? 'border-[#00d4ff] bg-[rgba(0,212,255,0.1)]'
                            : 'border-[rgba(0,212,255,0.2)] glass hover:border-[rgba(0,212,255,0.4)]'
                        }`}
                      >
                        <div
                          className={`mb-1 truncate ${
                            selectedKB === kb.collection_id ? 'text-[#00d4ff]' : 'text-[#e8eaed]'
                          }`}
                          title={kb.collection_name}
                        >
                          {kb.collection_name}
                        </div>
                        <div className="text-xs text-[#94a3b8]">
                          {kb.total_documents} 文档 · {kb.total_chunks} chunks
                        </div>
                      </motion.button>
                    ))}
                  </div>
                )}
              </div>

              {/* File Upload Area */}
              <div className="space-y-3">
                <label className="text-[#e8eaed]">选择文件</label>
                <div
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
                  className="border-2 border-dashed border-[rgba(0,212,255,0.3)] rounded-xl p-8 text-center glass hover:border-[#00d4ff] transition-all cursor-pointer"
                >
                  <input
                    type="file"
                    multiple
                    onChange={handleFileSelect}
                    className="hidden"
                    id="file-upload"
                    accept=".pdf,.md,.docx,.jpg,.jpeg,.png"
                  />
                  <label htmlFor="file-upload" className="cursor-pointer">
                    <Upload size={48} className="mx-auto mb-4 text-[#00d4ff]" />
                    <p className="text-[#e8eaed] mb-2">点击或拖拽文件到此处</p>
                    <p className="text-sm text-[#94a3b8]">目前仅支持 PDF 格式</p>
                  </label>
                </div>

                {/* Selected Files */}
                {files.length > 0 && (
                  <div className="space-y-2">
                    {files.map((file, index) => {
                      const status = uploadProgress[file.name];
                      return (
                        <div
                          key={index}
                          className="flex items-center justify-between p-3 glass rounded-lg border border-[rgba(0,212,255,0.2)]"
                        >
                          <div className="flex items-center gap-3">
                            {status === 'uploading' && (
                              <Loader2 size={16} className="text-[#00d4ff] animate-spin" />
                            )}
                            {status === 'success' && (
                              <CheckCircle size={16} className="text-[#00ff88]" />
                            )}
                            {status === 'error' && (
                              <AlertCircle size={16} className="text-[#ff3b5c]" />
                            )}
                            {!status && <FileText size={16} className="text-[#00d4ff]" />}
                            <span className="text-[#e8eaed]">{file.name}</span>
                            <span className="text-xs text-[#94a3b8]">
                              {(file.size / 1024 / 1024).toFixed(2)} MB
                            </span>
                          </div>
                          {!uploading && (
                            <button
                              onClick={() => setFiles(files.filter((_, i) => i !== index))}
                              className="text-[#94a3b8] hover:text-[#ff3b5c] transition-colors"
                            >
                              <X size={16} />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Advanced Settings Toggle */}
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-[#00d4ff] hover:text-[#e8eaed] transition-colors"
              >
                <Settings size={16} />
                {showAdvanced ? '隐藏' : '显示'}高级配置
              </button>

              {/* Advanced Settings */}
              <AnimatePresence>
                {showAdvanced && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="space-y-6 overflow-hidden"
                  >
                    {/* Extraction Mode */}
                    <div className="space-y-3">
                      <label className="text-[#e8eaed]">提取模式</label>
                      <div className="grid grid-cols-2 gap-3">
                        <button
                          onClick={() => setConfig({ ...config, extractionMode: 'fast' })}
                          className={`p-4 rounded-xl border-2 transition-all text-left ${
                            config.extractionMode === 'fast'
                              ? 'border-[#00d4ff] bg-[rgba(0,212,255,0.1)]'
                              : 'border-[rgba(0,212,255,0.2)] glass'
                          }`}
                        >
                          <div className={config.extractionMode === 'fast' ? 'text-[#00d4ff]' : 'text-[#e8eaed]'}>
                            快速模式(PyMuPDF4LLM)
                          </div>
                          <div className="text-xs text-[#94a3b8] mt-1">
                            适合简单文档
                          </div>
                        </button>

                        <button
                          onClick={() => setConfig({ ...config, extractionMode: 'vlm' })}
                          className={`p-4 rounded-xl border-2 transition-all text-left ${
                            config.extractionMode === 'vlm'
                              ? 'border-[#00d4ff] bg-[rgba(0,212,255,0.1)]'
                              : 'border-[rgba(0,212,255,0.2)] glass'
                          }`}
                        >
                          <div className={config.extractionMode === 'vlm' ? 'text-[#00d4ff]' : 'text-[#e8eaed]'}>
                            精确模式(VLM)
                          </div>
                          <div className="text-xs text-[#94a3b8] mt-1">
                            支持复杂布局
                          </div>
                        </button>
                      </div>
                    </div>

                    {/* Chunking Parameters */}
                    <div className="space-y-3">
                      <label className="text-[#e8eaed]">切分参数</label>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <label className="text-[#94a3b8] text-sm">Chunk Size</label>
                          <div className="flex gap-2">
                            <input
                              type="number"
                              value={config.chunkSize}
                              onChange={(e) => setConfig({ ...config, chunkSize: parseInt(e.target.value) })}
                              className="flex-1 px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                            />
                            <span className="px-3 py-2 glass rounded-lg text-[#94a3b8] text-sm">tokens</span>
                          </div>
                        </div>

                        <div className="space-y-2">
                          <label className="text-[#94a3b8] text-sm">Overlap</label>
                          <div className="flex gap-2">
                            <input
                              type="number"
                              value={config.overlap}
                              onChange={(e) => setConfig({ ...config, overlap: parseInt(e.target.value) })}
                              className="flex-1 px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                            />
                            <span className="px-3 py-2 glass rounded-lg text-[#94a3b8] text-sm">tokens</span>
                          </div>
                        </div>

                        <div className="space-y-2">
                          <label className="text-[#94a3b8] text-sm">Max Page Span</label>
                          <div className="flex gap-2">
                            <input
                              type="number"
                              value={config.maxPageSpan}
                              onChange={(e) => setConfig({ ...config, maxPageSpan: parseInt(e.target.value) })}
                              className="flex-1 px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                            />
                            <span className="px-3 py-2 glass rounded-lg text-[#94a3b8] text-sm">pages</span>
                          </div>
                        </div>

                        <div className="space-y-2">
                          <label className="text-[#94a3b8] text-sm">Bridge Length</label>
                          <div className="flex gap-2">
                            <input
                              type="number"
                              value={config.bridgeLength}
                              onChange={(e) => setConfig({ ...config, bridgeLength: parseInt(e.target.value) })}
                              className="flex-1 px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                            />
                            <span className="px-3 py-2 glass rounded-lg text-[#94a3b8] text-sm">tokens</span>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <label className="text-[#94a3b8] text-sm">切分方法</label>
                        <select
                          value={config.chunkingMethod}
                          onChange={(e) => setConfig({ ...config, chunkingMethod: e.target.value })}
                          className="w-full px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]"
                        >
                          <option value="header_recursive">递归标题分割</option>
                          <option value="markdown_only">自定义Markdown分割</option>
                        </select>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Warning */}
              {!selectedKB && files.length > 0 && (
                <div className="flex items-center gap-2 p-3 glass rounded-lg border border-[rgba(255,184,0,0.3)] bg-[rgba(255,184,0,0.05)]">
                  <AlertCircle size={16} className="text-[#ffb800]" />
                  <span className="text-sm text-[#ffb800]">请先选择一个知识库</span>
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 p-6 border-t border-[rgba(0,212,255,0.15)]">
            <motion.button
              onClick={onClose}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="px-6 py-3 glass border border-[rgba(0,212,255,0.2)] rounded-xl hover:bg-[rgba(0,212,255,0.05)] transition-all text-[#e8eaed]"
            >
              取消
            </motion.button>
            <motion.button
              onClick={handleSubmit}
              disabled={!selectedKB || files.length === 0 || uploading}
              whileHover={selectedKB && files.length > 0 && !uploading ? { scale: 1.05 } : {}}
              whileTap={selectedKB && files.length > 0 && !uploading ? { scale: 0.95 } : {}}
              className={`px-6 py-3 rounded-xl transition-all relative overflow-hidden group flex items-center gap-2 ${
                selectedKB && files.length > 0 && !uploading
                  ? 'bg-gradient-to-r from-[#00d4ff] to-[#0066ff] text-[#0a0e27] hover:shadow-[0_0_30px_rgba(0,212,255,0.6)]'
                  : 'bg-[rgba(0,212,255,0.2)] text-[#94a3b8] cursor-not-allowed'
              }`}
            >
              {selectedKB && files.length > 0 && !uploading && (
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white to-transparent opacity-0 group-hover:opacity-20 shimmer" />
              )}
              {uploading && <Loader2 size={16} className="animate-spin" />}
              <span className="relative z-10">
                {uploading ? '上传中...' : `上传 (${files.length})`}
              </span>
            </motion.button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
