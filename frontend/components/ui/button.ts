import { cn } from './utils.ts';

export type ButtonVariant = 'primary' | 'secondary' | 'quiet' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

const base =
  'inline-flex items-center justify-center whitespace-nowrap rounded-full font-medium transition-[background-color,border-color,color,box-shadow,transform] duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-45';

const variants: Record<ButtonVariant, string> = {
  primary:
    'border border-violet-600 bg-violet-600 text-white shadow-[0_4px_12px_rgba(102,87,232,0.18)] hover:border-violet-700 hover:bg-violet-700 hover:shadow-[0_7px_18px_rgba(102,87,232,0.24)]',
  secondary:
    'border border-violet-400 bg-white text-violet-700 shadow-sm hover:border-violet-500 hover:bg-violet-50',
  quiet:
    'border border-slate-200 bg-white text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950',
  ghost:
    'border border-transparent bg-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-950',
  danger:
    'border border-rose-200 bg-white text-rose-600 shadow-sm hover:border-rose-300 hover:bg-rose-50',
};

const sizes: Record<ButtonSize, string> = {
  sm: 'h-8 gap-1.5 px-3 text-xs',
  md: 'h-10 gap-2 px-5 text-sm',
  lg: 'h-11 gap-2 px-6 text-sm',
};

interface ButtonStyleOptions {
  variant?: ButtonVariant;
  size?: ButtonSize;
  iconOnly?: boolean;
  className?: string;
}

export function buttonStyles({
  variant = 'primary',
  size = 'md',
  iconOnly = false,
  className,
}: ButtonStyleOptions = {}): string {
  return cn(
    base,
    variants[variant],
    iconOnly ? (size === 'sm' ? 'h-8 w-8 p-0' : size === 'lg' ? 'h-11 w-11 p-0' : 'h-10 w-10 p-0') : sizes[size],
    className,
  );
}
