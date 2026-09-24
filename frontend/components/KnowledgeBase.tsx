import { Database, LibraryBig, Plus, Search, Trash2 } from 'lucide-react';
import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { ConfirmDialog } from './ConfirmDialog';
import { Toast } from './Toast';
import { buttonStyles } from './ui/button';

interface KnowledgeBaseProps {
  onViewDetail: (collectionId: string) => void;
}

interface KnowledgeBaseData {
  id: number;
  collection_id: string;  // Milvus collection ID
  name: string;  // 显示名称（中文）
  documents: number;
  chunks: number | string;
  updated: string;
  storageUsed: number;
}

export function KnowledgeBase({ onViewDetail }: KnowledgeBaseProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseData[]>([]);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newKbName, setNewKbName] = useState('');
  const [loading, setLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ show: boolean; id: string; name: string }>({
    show: false,
    id: '',
    name: '',
  });
  const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' | 'info' | 'warning' }>({
    show: false,
    message: '',
    type: 'info',
  });

  // 从Milvus API获取知识库列表
  useEffect(() => {
    fetchKnowledgeBases();
  }, []);

  const fetchKnowledgeBases = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/stats/all');
      const result = await response.json();

      if (result.status === 'success') {
        const collections = result.data.collections || [];

        const kbData = collections.map((col: any, index: number) => {
          // 格式化更新时间
          let updated = '未知';
          if (col.last_updated) {
            const date = new Date(col.last_updated);
            const now = new Date();
            const diffMs = now.getTime() - date.getTime();
            const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
            const diffDays = Math.floor(diffHours / 24);

            if (diffHours < 1) {
              updated = '刚刚';
            } else if (diffHours < 24) {
              updated = `${diffHours}小时前`;
            } else if (diffDays < 7) {
              updated = `${diffDays}天前`;
            } else {
              updated = date.toLocaleDateString('zh-CN');
            }
          }

          return {
            id: index + 1,
            collection_id: col.collection_id,  // Milvus内部ID
            name: col.collection_name,  // 显示名称（中文）
            documents: col.total_documents || 0,
            chunks: col.total_chunks || 0,
            updated: updated,
            storageUsed: Math.min(95, Math.floor((col.total_chunks || 0) / 100)), // 简单的存储使用率估算
          };
        });

        setKnowledgeBases(kbData);
      }
    } catch (error) {
      console.error('获取知识库列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const showToast = (message: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') => {
    setToast({ show: true, message, type });
  };

  const handleCreateKB = async () => {
    if (!newKbName.trim()) {
      showToast('请输入知识库名称', 'warning');
      return;
    }

    try {
      const response = await fetch(`http://localhost:8000/knowledge_base/create?display_name=${encodeURIComponent(newKbName)}`, {
        method: 'POST',
      });
      const result = await response.json();

      if (result.status === 'success') {
        showToast(result.message, 'success');
        setShowCreateDialog(false);
        setNewKbName('');
        // 刷新列表
        fetchKnowledgeBases();
      } else {
        showToast(result.message || '创建知识库失败', 'error');
      }
    } catch (error) {
      console.error('创建知识库失败:', error);
      showToast('创建知识库失败: ' + (error instanceof Error ? error.message : String(error)), 'error');
    }
  };

  const confirmDelete = (collectionId: string, displayName: string) => {
    setDeleteConfirm({ show: true, id: collectionId, name: displayName });
  };

  const handleDeleteKB = async () => {
    try {
      const response = await fetch('http://localhost:8000/knowledge_base/delete', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ collection_id: deleteConfirm.id }),
      });
      const result = await response.json();

      if (result.status === 'success') {
        showToast(result.message, 'success');
        // 刷新列表
        fetchKnowledgeBases();
      } else {
        showToast(result.message || '删除知识库失败', 'error');
      }
    } catch (error) {
      console.error('删除知识库失败:', error);
      showToast('删除知识库失败', 'error');
    }
  };

  // 过滤知识库
  const filteredKBs = knowledgeBases.filter(kb =>
    kb.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        className="flex items-center justify-between"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-800 shadow-sm">
            <LibraryBig size={23} aria-hidden="true" />
          </div>
          <h2 className="text-gradient">知识库管理</h2>
        </div>
        <motion.button
          onClick={() => setShowCreateDialog(true)}
          className={buttonStyles({ variant: 'primary', size: 'lg' })}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Plus size={18} aria-hidden="true" />
          <span>新建知识库</span>
        </motion.button>
      </motion.div>

      {/* Stats Summary */}
      {!loading && knowledgeBases.length > 0 && (
        <motion.div
          className="flex items-center gap-6 glass rounded-xl p-4 border border-slate-200"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <div className="flex items-center gap-2">
            <span className="text-slate-500 text-sm">总计:</span>
            <span className="text-slate-900 font-medium">{knowledgeBases.length} 个知识库</span>
          </div>
          <div className="w-px h-4 bg-violet-100" />
          <div className="flex items-center gap-2">
            <span className="text-slate-500 text-sm">文档:</span>
            <span className="text-violet-600 font-medium">
              {knowledgeBases.reduce((sum, kb) => sum + kb.documents, 0)} 个
            </span>
          </div>
          <div className="w-px h-4 bg-violet-100" />
          <div className="flex items-center gap-2">
            <span className="text-slate-500 text-sm">Chunks:</span>
            <span className="text-emerald-600 font-medium">
              {knowledgeBases.reduce((sum, kb) => sum + (typeof kb.chunks === 'number' ? kb.chunks : 0), 0)} 个
            </span>
          </div>
        </motion.div>
      )}

      {/* Search Bar */}
      <motion.div
        className="relative"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-violet-600" size={20} />
        <input
          type="text"
          placeholder="搜索知识库..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full h-14 pl-12 pr-4 glass-strong rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-violet-500 text-slate-900 placeholder-slate-400 transition-all duration-300"
        />
      </motion.div>

      {/* Loading State */}
      {loading && (
        <div className="text-center text-slate-500 py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-violet-500"></div>
          <p className="mt-4">加载中...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && filteredKBs.length === 0 && (
        <div className="text-center text-slate-500 py-12">
          <Database size={48} className="mx-auto mb-4 opacity-50" />
          <p>暂无知识库</p>
        </div>
      )}

      {/* Knowledge Base Cards */}
      <div className="space-y-4">
        {!loading && filteredKBs.map((kb, index) => (
          <motion.div
            key={kb.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 + index * 0.1 }}
            whileHover={{ y: -4, transition: { duration: 0.2 } }}
            className="glass gradient-border rounded-2xl p-6 hover:shadow-[0_0_30px_rgba(0,212,255,0.3)] transition-all cursor-pointer group relative overflow-hidden"
          >
            {/* Hover shimmer effect */}
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500">
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-[rgba(0,212,255,0.1)] to-transparent shimmer" />
            </div>

            <div className="flex items-start gap-4 relative z-10">
              {/* Icon */}
              <div className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-700 shadow-sm transition-all duration-300 group-hover:scale-105 group-hover:border-violet-200 group-hover:text-violet-700">
                <LibraryBig size={27} aria-hidden="true" />
              </div>

              {/* Content */}
              <div className="flex-1">
                <h3 className="mb-2 text-slate-900 group-hover:text-violet-600 transition-colors">{kb.name}</h3>

                <div className="text-slate-500 mb-4 text-sm flex items-center gap-3">
                  <span className="px-3 py-1 rounded-lg bg-violet-50 text-violet-600 border border-slate-200">
                    {kb.documents}个文档
                  </span>
                  <span className="px-3 py-1 rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-200">
                    {kb.chunks} chunks
                  </span>
                  <span>更新: {kb.updated}</span>
                </div>

                {/* Progress Bar */}
                <div className="mb-4">
                  <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
                    <span>存储使用</span>
                    <span className="text-violet-600">{kb.storageUsed}%</span>
                  </div>
                  <div className="h-2 bg-white rounded-full overflow-hidden border border-slate-200">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${kb.storageUsed}%` }}
                      transition={{ duration: 1, delay: 0.5 + index * 0.1 }}
                      className="h-full bg-gradient-to-r from-violet-500 to-indigo-600 relative overflow-hidden"
                    >
                      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white to-transparent opacity-30 shimmer" />
                    </motion.div>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2">
                <motion.button
                  onClick={() => onViewDetail(kb.collection_id)}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className={buttonStyles({ variant: 'primary', size: 'md' })}
                >
                  进入
                </motion.button>
                <motion.button
                  onClick={(e) => {
                    e.stopPropagation();
                    confirmDelete(kb.collection_id, kb.name);
                  }}
                  aria-label={`删除知识库 ${kb.name}`}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className={buttonStyles({ variant: 'danger', size: 'md', iconOnly: true })}
                >
                  <Trash2 size={18} />
                </motion.button>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Create Knowledge Base Dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="glass gradient-border rounded-2xl p-8 w-full max-w-md mx-4 relative overflow-hidden"
          >
            {/* Background shimmer */}
            <div className="absolute inset-0 opacity-5">
              <div className="absolute inset-0 bg-gradient-to-br from-violet-500 to-indigo-600 blur-3xl" />
            </div>

            <div className="relative z-10">
              <h3 className="text-2xl mb-6 text-slate-900">新建知识库</h3>

              <div className="mb-6">
                <label className="block text-slate-500 mb-2">知识库名称</label>
                <input
                  type="text"
                  value={newKbName}
                  onChange={(e) => setNewKbName(e.target.value)}
                  placeholder="请输入知识库名称（支持中文）"
                  className="w-full px-4 py-3 glass-strong rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-violet-500 text-slate-900 placeholder-slate-400 transition-all"
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateKB()}
                  autoFocus
                />
              </div>

              <div className="flex gap-3">
                <motion.button
                  onClick={handleCreateKB}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className={buttonStyles({ variant: 'primary', size: 'lg', className: 'flex-1' })}
                >
                  <span>创建</span>
                </motion.button>
                <motion.button
                  onClick={() => {
                    setShowCreateDialog(false);
                    setNewKbName('');
                  }}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className={buttonStyles({ variant: 'quiet', size: 'lg', className: 'flex-1' })}
                >
                  取消
                </motion.button>
              </div>
            </div>
          </motion.div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.show}
        onClose={() => setDeleteConfirm({ show: false, id: '', name: '' })}
        onConfirm={handleDeleteKB}
        title="确认删除知识库"
        message={`确定要删除知识库 "${deleteConfirm.name}" 吗？\n此操作不可恢复！`}
        type="warning"
        confirmText="删除"
        cancelText="取消"
      />

      {/* Toast Notification */}
      <Toast
        isOpen={toast.show}
        onClose={() => setToast({ ...toast, show: false })}
        message={toast.message}
        type={toast.type}
        duration={3000}
      />
    </div>
  );
}
