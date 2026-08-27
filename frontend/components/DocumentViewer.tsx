import { ArrowLeft, ChevronLeft, ChevronRight, Copy, Loader2 } from 'lucide-react';
import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';

interface DocumentViewerProps {
  fileId: string;
  onBack: () => void;
}

interface DocumentData {
  file_id: string;
  filename: string;
  metadata: {
    total_pages: number;
    total_images: number;
  };
  extraction_time: string;
  markdown: string;
  chunks: ChunkData[];
  pdf_url: string;
  total_chunks: number;
  total_pages: number;
  total_images: number;
}

interface ChunkData {
  text: string;
  page_start: number;
  page_end: number;
  pages: number[];
  text_length: number;
  continued: boolean;
  cross_page_bridge: boolean;
  is_table_like: boolean;
}

export function DocumentViewer({ fileId, onBack }: DocumentViewerProps) {
  const [activeTab, setActiveTab] = useState('original');
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [docData, setDocData] = useState<DocumentData | null>(null);

  useEffect(() => {
    fetchDocumentData();
  }, [fileId]);

  const fetchDocumentData = async () => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/document/${fileId}/details`);
      const result = await response.json();

      if (result.status === 'success') {
        setDocData(result);
      } else {
        toast.error('获取文档详情失败');
      }
    } catch (error) {
      console.error('获取文档详情失败:', error);
      toast.error('获取文档详情失败');
    } finally {
      setLoading(false);
    }
  };

  const processMarkdownImages = (markdown: string, fileId: string) => {
    // Replace relative image paths with API URLs
    // ![](images/xxx.png) -> ![](http://localhost:8000/document/{fileId}/images/xxx.png)
    const processed = markdown.replace(
      /!\[([^\]]*)\]\(images\/([^)]+)\)/g,
      `![$1](http://localhost:8000/document/${fileId}/images/$2)`
    );
    console.log('[DocumentViewer] Processing markdown images:');
    console.log('Original length:', markdown.length);
    console.log('Processed length:', processed.length);
    console.log('Sample processed:', processed.substring(0, 300));
    return processed;
  };

  const handleCopyMarkdown = () => {
    if (docData?.markdown) {
      navigator.clipboard.writeText(docData.markdown);
      toast.success('Markdown已复制到剪贴板');
    }
  };

  const tabs = [
    { id: 'original', label: '原始PDF' },
    { id: 'markdown', label: 'Markdown' },
    { id: 'chunks', label: '切分块' },
    { id: 'extraction', label: '提取信息' },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 size={48} className="text-[#00d4ff] animate-spin" />
      </div>
    );
  }

  if (!docData) {
    return (
      <div className="text-center py-12">
        <p className="text-[#94a3b8]">文档不存在</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        className="flex items-center gap-4"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <motion.button
          onClick={onBack}
          className="text-[#00d4ff] hover:text-[#00ffaa] flex items-center gap-2 transition-colors group"
          whileHover={{ x: -4 }}
        >
          <ArrowLeft size={18} className="group-hover:animate-pulse" />
          返回
        </motion.button>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff] to-[#0066ff] flex items-center justify-center text-xl shadow-lg">
            📄
          </div>
          <h2 className="text-gradient">{docData.filename}</h2>
        </div>
      </motion.div>

      {/* Tab Navigation */}
      <motion.div
        className="glass gradient-border rounded-2xl overflow-hidden"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <div className="border-b border-[rgba(0,212,255,0.15)]">
          <div className="flex">
            {tabs.map((tab, index) => (
              <motion.button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 + index * 0.05 }}
                className={`flex-1 px-6 py-4 transition-all relative ${
                  activeTab === tab.id
                    ? 'text-[#00d4ff]'
                    : 'text-[#94a3b8] hover:text-[#e8eaed]'
                }`}
              >
                {tab.label}
                {activeTab === tab.id && (
                  <motion.div
                    layoutId="activeDocTab"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-[#00d4ff] to-[#0066ff]"
                    transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                  />
                )}
              </motion.button>
            ))}
          </div>
        </div>

        {/* Tab Content */}
        <div className="p-6">
          {/* Original PDF Tab */}
          {activeTab === 'original' && (
            <motion.div
              className="space-y-4"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <h3 className="text-[#e8eaed]">PDF文档</h3>
              <div className="aspect-[8.5/11] glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl overflow-hidden">
                <iframe
                  src={`http://localhost:8000${docData.pdf_url}`}
                  className="w-full h-full"
                  title={docData.filename}
                />
              </div>
            </motion.div>
          )}

          {/* Markdown Tab */}
          {activeTab === 'markdown' && (
            <motion.div
              className="space-y-4"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-[#e8eaed]">Markdown 内容</h3>
                <motion.button
                  onClick={handleCopyMarkdown}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl hover:bg-[rgba(0,212,255,0.05)] transition-all flex items-center gap-2 text-[#e8eaed]"
                >
                  <Copy size={16} className="text-[#00d4ff]" />
                  复制
                </motion.button>
              </div>

              <div className="p-6 rounded-xl glass-strong border border-[rgba(0,212,255,0.3)] max-h-[600px] overflow-y-auto">
                <div className="prose prose-invert max-w-none text-[#e8eaed]">
                  <ReactMarkdown
                    components={{
                      h1: ({node, ...props}) => <h1 className="text-2xl text-gradient mb-4" {...props} />,
                      h2: ({node, ...props}) => <h2 className="text-xl text-[#00d4ff] mb-3" {...props} />,
                      h3: ({node, ...props}) => <h3 className="text-lg text-[#00d4ff] mb-2" {...props} />,
                      p: ({node, ...props}) => <p className="text-[#94a3b8] mb-3" {...props} />,
                      code: ({node, ...props}) => (
                        <code className="bg-[rgba(0,212,255,0.1)] text-[#00ff88] px-2 py-1 rounded" {...props} />
                      ),
                      pre: ({node, ...props}) => (
                        <pre className="bg-[rgba(0,212,255,0.1)] p-4 rounded-xl overflow-x-auto" {...props} />
                      ),
                      img: ({node, ...props}) => (
                        <img className="max-w-full h-auto rounded-xl border border-[rgba(0,212,255,0.2)] my-4" {...props} />
                      ),
                    }}
                  >
                    {processMarkdownImages(docData.markdown, docData.file_id)}
                  </ReactMarkdown>
                </div>
              </div>
            </motion.div>
          )}

          {/* Chunks Tab */}
          {activeTab === 'chunks' && (
            <motion.div
              className="space-y-4"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-[#e8eaed]">共 {docData.total_chunks} 个切分块</h3>
              </div>

              <div className="space-y-4 max-h-[600px] overflow-y-auto">
                {docData.chunks.map((chunk, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.05 }}
                    whileHover={{ y: -2 }}
                    className="glass gradient-border rounded-xl p-5 hover:shadow-[0_0_20px_rgba(0,212,255,0.2)] transition-all group"
                  >
                    <div className="flex items-center gap-3 mb-4">
                      <span className="text-[#e8eaed]">Chunk #{index + 1}</span>
                      <span className="text-[#94a3b8] flex items-center gap-1">
                        📍第 {chunk.page_start}{chunk.page_start !== chunk.page_end ? `-${chunk.page_end}` : ''} 页
                      </span>
                      <span className="text-[#94a3b8] flex items-center gap-1">
                        📏 {chunk.text_length} 字符
                      </span>
                    </div>

                    <div className="p-4 glass-strong rounded-xl border border-[rgba(0,212,255,0.1)] font-mono text-sm mb-4 text-[#94a3b8] max-h-[200px] overflow-y-auto whitespace-pre-wrap">
                      {chunk.text}
                    </div>

                    <div className="flex gap-2">
                      <span className={`px-3 py-1 rounded-lg text-xs ${chunk.cross_page_bridge ? 'bg-[rgba(0,255,136,0.1)] text-[#00ff88] border border-[rgba(0,255,136,0.2)]' : 'bg-[rgba(148,163,184,0.1)] text-[#94a3b8] border border-[rgba(148,163,184,0.2)]'}`}>
                        跨页: {chunk.cross_page_bridge ? '✅' : '❌'}
                      </span>
                      <span className={`px-3 py-1 rounded-lg text-xs ${chunk.continued ? 'bg-[rgba(0,255,136,0.1)] text-[#00ff88] border border-[rgba(0,255,136,0.2)]' : 'bg-[rgba(148,163,184,0.1)] text-[#94a3b8] border border-[rgba(148,163,184,0.2)]'}`}>
                        续接: {chunk.continued ? '✅' : '❌'}
                      </span>
                      <span className={`px-3 py-1 rounded-lg text-xs ${chunk.is_table_like ? 'bg-[rgba(0,255,136,0.1)] text-[#00ff88] border border-[rgba(0,255,136,0.2)]' : 'bg-[rgba(148,163,184,0.1)] text-[#94a3b8] border border-[rgba(148,163,184,0.2)]'}`}>
                        表格: {chunk.is_table_like ? '✅' : '❌'}
                      </span>
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Extraction Info Tab */}
          {activeTab === 'extraction' && (
            <motion.div
              className="grid grid-cols-3 gap-6"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="space-y-4">
                <h3 className="text-[#e8eaed] flex items-center gap-2">
                  <span className="text-2xl">📄</span>
                  文档信息
                </h3>
                <div className="space-y-3">
                  <div className="p-4 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl">
                    <p className="text-[#94a3b8] mb-2">总页数</p>
                    <div className="text-2xl text-[#00d4ff]">{docData.total_pages}</div>
                  </div>
                  <div className="p-4 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl">
                    <p className="text-[#94a3b8] mb-2">提取时间</p>
                    <div className="text-sm text-[#00d4ff]">
                      {new Date(docData.extraction_time).toLocaleString('zh-CN')}
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <h3 className="text-[#e8eaed] flex items-center gap-2">
                  <span className="text-2xl">🔢</span>
                  切分统计
                </h3>
                <div className="space-y-3">
                  <div className="p-4 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl">
                    <p className="text-[#94a3b8] mb-2">总切分块数</p>
                    <div className="text-2xl text-[#00d4ff]">{docData.total_chunks}</div>
                  </div>
                  <div className="p-4 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl">
                    <p className="text-[#94a3b8] mb-2">跨页块数</p>
                    <div className="text-2xl text-[#00ff88]">
                      {docData.chunks.filter(c => c.cross_page_bridge).length}
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <h3 className="text-[#e8eaed] flex items-center gap-2">
                  <span className="text-2xl">🖼️</span>
                  图片统计
                </h3>
                <div className="space-y-3">
                  <div className="p-4 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl">
                    <p className="text-[#94a3b8] mb-2">提取图片数</p>
                    <div className="text-2xl text-[#00d4ff]">{docData.total_images}</div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* Page Navigation - Only for PDF tab */}
          {activeTab === 'original' && docData.total_pages > 1 && (
            <motion.div
              className="flex items-center justify-center gap-4 mt-6 pt-6 border-t border-[rgba(0,212,255,0.15)]"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
            >
              <motion.button
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                whileHover={{ scale: currentPage === 1 ? 1 : 1.05 }}
                whileTap={{ scale: currentPage === 1 ? 1 : 0.95 }}
                className="px-4 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl hover:bg-[rgba(0,212,255,0.05)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-[#e8eaed]"
              >
                <ChevronLeft size={16} />
                上一页
              </motion.button>

              <span className="text-[#94a3b8] px-4 py-2 glass rounded-xl border border-[rgba(0,212,255,0.2)]">
                第 <span className="text-[#00d4ff]">{currentPage}</span> / {docData.total_pages} 页
              </span>

              <motion.button
                onClick={() => setCurrentPage(Math.min(docData.total_pages, currentPage + 1))}
                disabled={currentPage === docData.total_pages}
                whileHover={{ scale: currentPage === docData.total_pages ? 1 : 1.05 }}
                whileTap={{ scale: currentPage === docData.total_pages ? 1 : 0.95 }}
                className="px-4 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl hover:bg-[rgba(0,212,255,0.05)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-[#e8eaed]"
              >
                下一页
                <ChevronRight size={16} />
              </motion.button>
            </motion.div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
