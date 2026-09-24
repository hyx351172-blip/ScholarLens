import { Activity, Bell, Menu, User } from 'lucide-react';
import { buttonStyles } from './ui/button';

interface HeaderProps {
  title: string;
  onOpenNavigation: () => void;
}

export function Header({ title, onOpenNavigation }: HeaderProps) {
  return (
    <header className="app-shell-header fixed right-0 top-0 z-40 h-16 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="flex h-full items-center justify-between px-4 md:px-6">
        <div className="flex items-center gap-3">
          <button type="button" onClick={onOpenNavigation} className={buttonStyles({ variant: 'ghost', size: 'sm', iconOnly: true, className: 'md:hidden' })} aria-label="打开导航">
            <Menu size={19} />
          </button>
          <div>
            <h2 className="font-semibold text-slate-950">{title}</h2>
            <p className="hidden text-[11px] text-slate-400 sm:block">面向科研论文的可溯源智能阅读</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1.5 sm:flex">
            <Activity size={13} className="text-emerald-600" />
            <span className="text-xs font-medium text-emerald-700">本地工作区</span>
          </div>
          <button type="button" className={buttonStyles({ variant: 'quiet', iconOnly: true, className: 'relative text-slate-500' })} aria-label="通知">
            <Bell size={17} />
            <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-rose-500" />
          </button>
          <button type="button" className={buttonStyles({ variant: 'primary', size: 'sm', iconOnly: true })} aria-label="用户账户">
            <User size={16} />
          </button>
        </div>
      </div>
    </header>
  );
}
