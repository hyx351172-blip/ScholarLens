import { Bell, User, Activity } from 'lucide-react';
import { motion } from 'motion/react';

interface HeaderProps {
  title: string;
}

export function Header({ title }: HeaderProps) {
  return (
    <header className="h-16 glass fixed top-0 left-[260px] right-0 z-40 border-b border-[rgba(0,212,255,0.15)]">
      <div className="h-full px-6 flex items-center justify-between">
        <motion.h2
          className="text-[#e8eaed]"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          {title}
        </motion.h2>

        <div className="flex items-center gap-3">
          {/* Activity Indicator */}
          <motion.div
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass border border-[rgba(0,212,255,0.2)]"
            whileHover={{ scale: 1.05 }}
          >
            <Activity size={14} className="text-[#00ff88]" />
            <span className="text-xs text-[#94a3b8]">运行中</span>
          </motion.div>

          <motion.button
            className="w-10 h-10 rounded-xl glass-strong flex items-center justify-center transition-all duration-300 hover:bg-[rgba(0,212,255,0.1)] hover:shadow-[0_0_15px_rgba(0,212,255,0.3)] relative group"
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.95 }}
          >
            <Bell size={18} className="text-[#94a3b8] group-hover:text-[#00d4ff] transition-colors" />
            <div className="absolute top-2 right-2 w-2 h-2 bg-[#ff3b5c] rounded-full animate-pulse" />
          </motion.button>

          <motion.button
            className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff] to-[#0066ff] flex items-center justify-center shadow-[0_0_20px_rgba(0,212,255,0.4)] hover:shadow-[0_0_30px_rgba(0,212,255,0.6)] transition-all duration-300"
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.95 }}
          >
            <User size={18} className="text-[#0a0e27]" />
          </motion.button>
        </div>
      </div>
    </header>
  );
}
