import { ArrowRight, Bot, TrendingUp, TrendingDown } from 'lucide-react';
import { motion } from 'motion/react';
import { useState, useEffect } from 'react';
import { UploadDialog } from './UploadDialog';
import { config } from '../src/config';

interface DashboardProps {
  onNavigate?: (view: string) => void;
}

export function Dashboard({ onNavigate }: DashboardProps = {}) {
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [stats, setStats] = useState([
    { id: 1, label: '知识库', value: '0', unit: '个', icon: '📚', gradient: 'from-[#00d4ff] to-[#0066ff]', trend: '+0', trendUp: true },
    { id: 2, label: '文档数', value: '0', unit: '', icon: '📄', gradient: 'from-[#00ff88] to-[#00d4a0]', trend: '+0', trendUp: true },
    { id: 3, label: '查询次数', value: '0', unit: '', icon: '🔍', gradient: 'from-[#8b5cf6] to-[#6366f1]', trend: '+0%', trendUp: true },
    { id: 4, label: '响应时间', value: '0', unit: 'ms', icon: '⚡', gradient: 'from-[#ffb800] to-[#ff8c00]', trend: '-0ms', trendUp: true },
  ]);

  // 从Milvus API获取统计数据
  const fetchStats = async () => {
    try {
      const response = await fetch(`${config.milvusApiUrl}/stats/all`);
      const result = await response.json();

      if (result.status === 'success') {
        const data = result.data;
        setStats([
          { id: 1, label: '知识库', value: String(data.total_collections), unit: '个', icon: '📚', gradient: 'from-[#00d4ff] to-[#0066ff]', trend: '+0', trendUp: true },
          { id: 2, label: '文档数', value: String(data.total_documents), unit: '', icon: '📄', gradient: 'from-[#00ff88] to-[#00d4a0]', trend: '+0', trendUp: true },
          { id: 3, label: 'Chunk数', value: String(data.total_chunks), unit: '', icon: '🔍', gradient: 'from-[#8b5cf6] to-[#6366f1]', trend: '+0', trendUp: true },
          { id: 4, label: '响应时间', value: '142', unit: 'ms', icon: '⚡', gradient: 'from-[#ffb800] to-[#ff8c00]', trend: '-8ms', trendUp: true },
        ]);
      }
    } catch (error) {
      console.error('获取统计数据失败:', error);
    }
  };

  useEffect(() => {
    fetchStats();
    // 每30秒刷新一次数据
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleUpload = (files: File[], kbId: string, config: any) => {
    console.log('Uploading files:', files, 'to KB:', kbId, 'with config:', config);
    // 上传完成后刷新统计数据
    fetchStats();
  };

  const [conversations, setConversations] = useState<any[]>([]);

  // 从localStorage加载最近对话
  useEffect(() => {
    const loadRecentConversations = () => {
      try {
        const savedSessions = localStorage.getItem('chat_sessions');
        if (savedSessions) {
          const sessions = JSON.parse(savedSessions);
          // 只显示最近3个对话
          const recentSessions = sessions.slice(0, 3).map((session: any) => ({
            id: session.id,
            title: session.title,
            knowledgeBase: session.knowledgeBaseName,
            timestamp: formatTimestamp(session.updatedAt),
          }));
          setConversations(recentSessions);
        }
      } catch (error) {
        console.error('加载最近对话失败:', error);
      }
    };

    loadRecentConversations();
    // 每5秒检查一次更新
    const interval = setInterval(loadRecentConversations, 5000);
    return () => clearInterval(interval);
  }, []);

  // 格式化时间戳
  const formatTimestamp = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 60) return `${minutes}分钟前`;
    if (hours < 24) return `${hours}小时前`;
    return `${days}天前`;
  };

  const quickActions = [
    { id: 1, label: '上传文档', icon: '📤', variant: 'primary' },
    { id: 2, label: '开始对话', icon: '💬', variant: 'outline' },
    { id: 3, label: '测试检索', icon: '🔍', variant: 'secondary' },
  ];

  return (
    <div className="space-y-6">
      {/* Statistics Cards */}
      <div className="grid grid-cols-4 gap-4">
        {stats.map((stat, index) => (
          <motion.div
            key={stat.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: index * 0.1 }}
            whileHover={{ y: -5, transition: { duration: 0.2 } }}
            className="glass gradient-border rounded-2xl p-6 group cursor-pointer relative overflow-hidden"
          >
            {/* Background Shimmer Effect */}
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500">
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-[rgba(0,212,255,0.1)] to-transparent shimmer" />
            </div>

            <div className="relative z-10">
              <div className="flex items-start justify-between mb-4">
                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${stat.gradient} flex items-center justify-center text-2xl shadow-lg group-hover:scale-110 transition-transform duration-300`}>
                  {stat.icon}
                </div>
                <div className={`flex items-center gap-1 px-2 py-1 rounded-lg ${stat.trendUp ? 'bg-[rgba(0,255,136,0.1)] text-[#00ff88]' : 'bg-[rgba(255,59,92,0.1)] text-[#ff3b5c]'}`}>
                  {stat.trendUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                  <span className="text-xs">{stat.trend}</span>
                </div>
              </div>

              <div className="flex items-baseline gap-1 mb-2">
                <span className="text-4xl text-[#e8eaed]">{stat.value}</span>
                {stat.unit && <span className="text-lg text-[#94a3b8]">{stat.unit}</span>}
              </div>

              <div className="text-[#94a3b8]">{stat.label}</div>
            </div>

            {/* Glow effect on hover */}
            <div className={`absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-gradient-to-br ${stat.gradient} blur-xl -z-10`} style={{ filter: 'blur(20px)' }} />
          </motion.div>
        ))}
      </div>

      {/* Recent Conversations */}
      <motion.div
        className="glass gradient-border rounded-2xl p-6"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.5 }}
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-[#e8eaed]">最近对话</h3>
          <motion.button
            onClick={() => onNavigate && onNavigate('chat')}
            className="text-[#00d4ff] flex items-center gap-1 hover:gap-2 transition-all duration-300 group"
            whileHover={{ scale: 1.05 }}
          >
            查看全部
            <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
          </motion.button>
        </div>

        <div className="space-y-2">
          {conversations.length === 0 ? (
            <div className="text-center py-12 text-[#94a3b8]">
              <Bot size={48} className="mx-auto mb-4 opacity-50" />
              <p>暂无对话记录</p>
              <motion.button
                onClick={() => onNavigate && onNavigate('chat')}
                className="mt-4 px-4 py-2 border border-[#00d4ff] text-[#00d4ff] rounded-lg hover:bg-[rgba(0,212,255,0.1)] transition-all"
                whileHover={{ scale: 1.05 }}
              >
                开始第一次对话
              </motion.button>
            </div>
          ) : (
            conversations.map((conv, index) => (
            <motion.div
              key={conv.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.6 + index * 0.1 }}
              whileHover={{ x: 5, transition: { duration: 0.2 } }}
              className="flex items-center gap-4 p-4 rounded-xl hover:bg-[rgba(0,212,255,0.05)] cursor-pointer transition-all duration-300 border border-transparent hover:border-[rgba(0,212,255,0.2)] group"
            >
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff] to-[#0066ff] flex items-center justify-center flex-shrink-0 shadow-lg group-hover:shadow-[0_0_20px_rgba(0,212,255,0.4)] transition-shadow">
                <Bot size={20} className="text-[#0a0e27]" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="text-[#e8eaed] mb-1 group-hover:text-[#00d4ff] transition-colors">{conv.title}</div>
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center px-3 py-1 rounded-lg text-xs bg-[rgba(0,212,255,0.1)] text-[#00d4ff] border border-[rgba(0,212,255,0.2)]">
                    {conv.knowledgeBase}
                  </span>
                </div>
              </div>

              <div className="text-[#94a3b8] text-sm flex-shrink-0">
                {conv.timestamp}
              </div>
            </motion.div>
          )))}
        </div>
      </motion.div>

      {/* Quick Actions */}
      <motion.div
        className="glass gradient-border rounded-2xl p-6"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.8 }}
      >
        <h3 className="text-[#e8eaed] mb-6">快速操作</h3>

        <div className="flex gap-4">
          {quickActions.map((action, index) => (
            <motion.button
              key={action.id}
              onClick={() => {
                if (action.id === 1) {
                  setShowUploadDialog(true);
                } else if (action.id === 2 && onNavigate) {
                  onNavigate('chat');
                }
              }}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3, delay: 0.9 + index * 0.1 }}
              whileHover={{ scale: 1.05, y: -2 }}
              whileTap={{ scale: 0.95 }}
              className={`flex-1 h-16 rounded-xl flex items-center justify-center gap-3 transition-all duration-300 relative overflow-hidden group ${
                action.variant === 'primary'
                  ? 'bg-gradient-to-r from-[#00d4ff] to-[#0066ff] text-[#0a0e27] shadow-[0_0_20px_rgba(0,212,255,0.4)] hover:shadow-[0_0_30px_rgba(0,212,255,0.6)]'
                  : action.variant === 'outline'
                  ? 'border-2 border-[#00d4ff] text-[#00d4ff] hover:bg-[rgba(0,212,255,0.1)]'
                  : 'bg-[rgba(0,212,255,0.1)] text-[#00d4ff] border border-[rgba(0,212,255,0.2)] hover:bg-[rgba(0,212,255,0.2)]'
              }`}
            >
              {action.variant === 'primary' && (
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white to-transparent opacity-0 group-hover:opacity-20 shimmer" />
              )}
              <span className="text-2xl relative z-10">{action.icon}</span>
              <span className="relative z-10">{action.label}</span>
            </motion.button>
          ))}
        </div>
      </motion.div>

      {/* Upload Dialog */}
      <UploadDialog
        isOpen={showUploadDialog}
        onClose={() => setShowUploadDialog(false)}
        onUpload={handleUpload}
      />
    </div>
  );
}
