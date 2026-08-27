import { Home, Database, MessageSquare, Search, Settings, Zap } from 'lucide-react';
import { motion } from 'motion/react';

interface SidebarProps {
  activeView: string;
  onNavigate: (view: string) => void;
}

export function Sidebar({ activeView, onNavigate }: SidebarProps) {
  const menuItems = [
    { id: 'dashboard', label: '仪表盘', icon: Home, disabled: false },
    { id: 'knowledge', label: '知识库管理', icon: Database, disabled: false },
    { id: 'chat', label: '对话', icon: MessageSquare, disabled: false },
    { id: 'retrieval', label: '检索测试', icon: Search, disabled: true, badge: '待开发' },
    { id: 'settings', label: '设置', icon: Settings, disabled: false, badge: '待优化' },
  ];

  return (
    <div className="w-[260px] h-screen glass-strong fixed left-0 top-0 flex flex-col z-50 border-r border-[rgba(0,212,255,0.15)]">
      {/* Logo/Brand */}
      <div className="h-16 flex items-center px-6 border-b border-[rgba(0,212,255,0.15)]">
        <motion.div
          className="flex items-center gap-2"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#00d4ff] to-[#0066ff] flex items-center justify-center animate-pulse-glow">
            <Zap size={18} className="text-[#0a0e27]" />
          </div>
          <h1 className="text-gradient">ScholarLens</h1>
        </motion.div>
      </div>

      {/* Navigation Menu */}
      <nav className="flex-1 px-4 py-6 space-y-1">
        {menuItems.map((item, index) => {
          const Icon = item.icon;
          const isActive = activeView === item.id;
          const isDisabled = item.disabled;

          return (
            <motion.button
              key={item.id}
              onClick={() => !isDisabled && onNavigate(item.id)}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: index * 0.1 }}
              disabled={isDisabled}
              className={`w-full flex items-center justify-between gap-3 px-4 py-3 rounded-xl transition-all duration-300 group ${
                isDisabled
                  ? 'text-[#64748b] opacity-50 cursor-not-allowed'
                  : isActive
                  ? 'bg-gradient-to-r from-[#00d4ff] to-[#0066ff] text-[#0a0e27] shadow-[0_0_20px_rgba(0,212,255,0.4)]'
                  : 'text-[#e8eaed] hover:bg-[rgba(0,212,255,0.1)]'
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon size={20} className={`${isDisabled ? 'text-[#64748b]' : isActive ? 'text-[#0a0e27]' : 'group-hover:text-[#00d4ff]'} transition-colors`} />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span className="px-2 py-0.5 text-xs bg-[rgba(255,184,0,0.15)] text-[#ffb800] rounded-full border border-[rgba(255,184,0,0.3)]">
                  {item.badge}
                </span>
              )}
            </motion.button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-[rgba(0,212,255,0.15)]">
        <motion.div
          className="text-[#94a3b8] text-sm flex items-center gap-2"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
        >
          <div className="w-2 h-2 rounded-full bg-[#00ff88] animate-pulse" />
          <span>系统在线 v1.0.0</span>
        </motion.div>
      </div>
    </div>
  );
}
