import { BookOpen, Home, MessageSquareText, Search, Settings, Sparkles } from 'lucide-react';
import { motion } from 'motion/react';

interface SidebarProps {
  activeView: string;
  onNavigate: (view: string) => void;
  mobileOpen: boolean;
  onClose: () => void;
}
const menuItems = [
  { id: 'dashboard', label: '概览', icon: Home, disabled: false },
  { id: 'knowledge', label: '文献库', icon: BookOpen, disabled: false },
  { id: 'chat', label: '科研问答', icon: MessageSquareText, disabled: false, badge: 'RAG' },
  { id: 'retrieval', label: '检索评测', icon: Search, disabled: true, badge: 'Soon' },
  { id: 'settings', label: '设置', icon: Settings, disabled: false },
];

export function Sidebar({ activeView, onNavigate, mobileOpen, onClose }: SidebarProps) {
  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-slate-950/20 backdrop-blur-[1px] md:hidden"
          onClick={onClose}
          aria-label="关闭导航遮罩"
        />
      )}
      <aside className={`fixed inset-y-0 left-0 z-50 flex w-[232px] flex-col border-r border-slate-200 bg-white transition-transform duration-200 md:translate-x-0 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
      <div className="flex h-16 items-center border-b border-slate-200 px-5">
        <motion.div
          className="flex items-center gap-3"
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-[0_8px_22px_rgba(99,102,241,0.25)]">
            <Sparkles size={18} />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-slate-950">ScholarLens</h1>
            <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400">Research workspace</p>
          </div>
        </motion.div>
      </div>

      <nav className="flex-1 space-y-1.5 px-3 py-5">
        <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">工作台</p>
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeView === item.id;
          return (
            <button
              type="button"
              key={item.id}
              onClick={() => {
                if (!item.disabled) {
                  onNavigate(item.id);
                  onClose();
                }
              }}
              disabled={item.disabled}
              className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                item.disabled
                  ? 'cursor-not-allowed text-slate-300'
                  : isActive
                    ? 'bg-[#efedf9] text-violet-800'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950'
              }`}
            >
              <span className="flex items-center gap-3">
                <Icon size={18} className={isActive ? 'text-violet-600' : ''} />
                {item.label}
              </span>
              {item.badge && (
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  item.disabled ? 'bg-slate-100 text-slate-400' : 'bg-white text-violet-600'
                }`}>
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-slate-200 p-4">
        <div className="rounded-2xl bg-gradient-to-br from-violet-50 to-indigo-50 p-3.5">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-700">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            本地服务已连接
          </div>
          <p className="mt-2 text-[11px] leading-5 text-slate-500">论文内容默认保存在本地知识库。</p>
        </div>
      </div>
      </aside>
    </>
  );
}
