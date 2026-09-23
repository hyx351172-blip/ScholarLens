import {
  ArrowLeft,
  ChevronDown,
  CircleCheckBig,
  Eye,
  FileImage,
  FileText,
  FileType,
  LibraryBig,
  Loader2,
  Search,
  Trash2,
  Upload,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { toast } from 'sonner';
import { UploadDialog } from './UploadDialog';

interface KnowledgeBaseDetailProps {
  collectionId: string;
  onBack: () => void;
  onViewDocument: (fileId: string) => void;
}

interface DocumentData {
  filename: string;
  file_id: string;
  chunks: number;
  created_at: string;
  metadata: any;
}

interface KBInfo {
  collection_id: string;
  collection_name: string;
  total_documents: number;
  total_chunks: number;
  last_updated: string | null;
}

export function KnowledgeBaseDetail({ collectionId, onBack, onViewDocument }: KnowledgeBaseDetailProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [kbInfo, setKbInfo] = useState<KBInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [showUploadDialog, setShowUploadDialog] = useState(false);

  useEffect(() => {
    fetchKBDetails();
  }, [collectionId]);

  const fetchKBDetails = async () => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/knowledge_base/${collectionId}/documents`);
      const result = await response.json();

      if (result.status === 'success') {
        setKbInfo({
          collection_id: result.collection_id,
          collection_name: result.collection_name,
          total_documents: result.total_documents,
          total_chunks: result.total_chunks,
          last_updated: result.last_updated,
        });
        setDocuments(result.documents || []);
      } else {
        toast.error('获取知识库详情失败');
      }
    } catch (error) {
      console.error('获取知识库详情失败:', error);
      toast.error('获取知识库详情失败');
    } finally {
      setLoading(false);
    }
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    switch (ext) {
      case 'pdf':
        return FileText;
      case 'md':
      case 'txt':
        return FileType;
      case 'docx':
      case 'doc':
        return FileText;
      case 'jpg':
      case 'jpeg':
      case 'png':
      case 'gif':
        return FileImage;
      default:
        return FileText;
    }
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '未知';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const getRelativeTime = (dateStr: string | null) => {
    if (!dateStr) return '未知';
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diff = now.getTime() - date.getTime();
      const minutes = Math.floor(diff / 60000);
      const hours = Math.floor(minutes / 60);
      const days = Math.floor(hours / 24);

      if (minutes < 60) return `${minutes}分钟前`;
      if (hours < 24) return `${hours}小时前`;
      if (days < 7) return `${days}天前`;
      return formatDate(dateStr);
    } catch {
      return dateStr;
    }
  };

  const filteredDocuments = documents.filter((doc) =>
    doc.filename.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleUpload = (files: File[], kbId: string, config: any) => {
    console.log('Uploading files:', files, 'to KB:', kbId, 'with config:', config);
    // 上传完成后刷新文档列表
    fetchKBDetails();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 size={48} className="text-violet-600 animate-spin" />
      </div>
    );
  }

  if (!kbInfo) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-500">知识库不存在</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        className="flex items-center justify-between"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-4">
          <motion.button
            onClick={onBack}
            className="text-violet-600 hover:text-emerald-600 flex items-center gap-2 transition-colors group"
            whileHover={{ x: -4 }}
          >
            <ArrowLeft size={18} className="group-hover:animate-pulse" />
            返回
          </motion.button>
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-800 shadow-sm">
              <LibraryBig size={23} aria-hidden="true" />
            </div>
            <h2 className="text-gradient">{kbInfo.collection_name}</h2>
          </div>
        </div>

        <motion.button
          onClick={() => setShowUploadDialog(true)}
          className="px-6 py-3 bg-gradient-to-r from-violet-500 to-indigo-600 text-white rounded-xl hover:shadow-[0_0_30px_rgba(0,212,255,0.6)] transition-all flex items-center gap-2 relative overflow-hidden group"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white to-transparent opacity-0 group-hover:opacity-20 shimmer" />
          <Upload size={18} className="relative z-10" />
          <span className="relative z-10">上传文档</span>
        </motion.button>
      </motion.div>

      {/* Upload Dialog */}
      <UploadDialog
        isOpen={showUploadDialog}
        onClose={() => setShowUploadDialog(false)}
        onUpload={handleUpload}
        preselectedKB={collectionId}
      />

      {/* Summary Bar */}
      <motion.div
        className="flex items-center gap-3"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <span className="px-4 py-2 glass-strong rounded-xl border border-slate-200 text-slate-900">
          {kbInfo.total_documents}个文档
        </span>
        <span className="px-4 py-2 glass-strong rounded-xl border border-emerald-200 text-emerald-600">
          {kbInfo.total_chunks} chunks
        </span>
        <span className="px-4 py-2 glass-strong rounded-xl border border-slate-200 text-slate-500">
          最后更新: {getRelativeTime(kbInfo.last_updated)}
        </span>
      </motion.div>

      {/* Search and Filters */}
      <motion.div
        className="flex items-center gap-4"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <div className="relative flex-1 max-w-[320px]">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-violet-600" size={18} />
          <input
            type="text"
            placeholder="搜索文档..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-12 pl-11 pr-4 glass-strong border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-transparent text-slate-900 placeholder-slate-400 transition-all"
          />
        </div>

        <motion.button
          className="px-4 py-3 glass-strong border border-slate-200 rounded-xl hover:bg-violet-50/50 transition-all flex items-center gap-2 text-slate-900"
          whileHover={{ scale: 1.05 }}
        >
          按时间
          <ChevronDown size={16} className="text-violet-600" />
        </motion.button>

        <motion.button
          className="px-4 py-3 glass-strong border border-slate-200 rounded-xl hover:bg-violet-50/50 transition-all flex items-center gap-2 text-slate-900"
          whileHover={{ scale: 1.05 }}
        >
          按大小
          <ChevronDown size={16} className="text-violet-600" />
        </motion.button>
      </motion.div>

      {/* Document List */}
      {filteredDocuments.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center py-12"
        >
          <p className="text-slate-500">
            {documents.length === 0 ? '暂无文档' : '没有找到匹配的文档'}
          </p>
        </motion.div>
      ) : (
        <div className="space-y-3">
          {filteredDocuments.map((doc, index) => {
            const FileIcon = getFileIcon(doc.filename);
            return (
            <motion.div
              key={doc.file_id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.3 + index * 0.1 }}
              whileHover={{ y: -2 }}
              className="glass gradient-border rounded-xl p-5 hover:shadow-[0_0_25px_rgba(0,212,255,0.2)] transition-all group relative overflow-hidden"
            >
              {/* Hover shimmer */}
              <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500">
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-[rgba(0,212,255,0.1)] to-transparent shimmer" />
              </div>

              <div className="flex items-center gap-4 relative z-10">
                {/* File Icon */}
                <div className="glass-strong flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-600 transition-all group-hover:scale-105 group-hover:text-violet-700">
                  <FileIcon size={24} aria-hidden="true" />
                </div>

                {/* File Info */}
                <div className="flex-1 min-w-0">
                  <div className="text-slate-900 mb-2 group-hover:text-violet-600 transition-colors truncate" title={doc.filename}>
                    {doc.filename}
                  </div>
                  <div className="text-slate-500 text-sm flex items-center gap-3">
                    <span className="px-2 py-1 glass rounded-lg border border-slate-100">
                      {doc.chunks} chunks
                    </span>
                    <span>上传于 {formatDate(doc.created_at)}</span>
                  </div>
                </div>

                {/* Status */}
                <div className="flex items-center gap-2">
                  <span className="px-3 py-1.5 bg-emerald-50 text-emerald-600 rounded-lg text-xs border border-emerald-200 flex items-center gap-1">
                    <CircleCheckBig size={14} aria-hidden="true" />
                    已索引
                  </span>
                </div>

                {/* Actions */}
                <div className="flex gap-2">
                  <motion.button
                    onClick={() => onViewDocument(doc.file_id)}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    className="px-4 py-2 border border-violet-500 text-violet-600 rounded-xl hover:bg-violet-50 transition-all flex items-center gap-2"
                  >
                    <Eye size={16} />
                    查看
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    aria-label={`删除文档 ${doc.filename}`}
                    className="px-4 py-2 border border-rose-500 text-rose-600 rounded-xl hover:bg-[rgba(255,59,92,0.1)] transition-all"
                  >
                    <Trash2 size={16} />
                  </motion.button>
                </div>
              </div>
            </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
