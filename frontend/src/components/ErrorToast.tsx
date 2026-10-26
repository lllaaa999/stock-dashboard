import { useMarketStore } from '../store/useMarketStore';

/**
 * 非侵入式错误提示组件
 * 从 store 读取 errorToasts，在屏幕右下角显示最多 5 条 toast
 * 错误用红色，警告用橙色，自动消失（store 层 setTimeout 控制）
 */
export default function ErrorToast() {
  const errorToasts = useMarketStore((s) => s.errorToasts);
  const dismissErrorToast = useMarketStore((s) => s.dismissErrorToast);

  if (errorToasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none"
      role="alert"
      aria-live="assertive"
    >
      {errorToasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto flex items-start gap-2 rounded-lg px-4 py-3 text-sm shadow-lg backdrop-blur-sm transition-all duration-300 animate-[fadeIn_0.2s_ease-out] ${
            toast.severity === 'error'
              ? 'bg-[#1e222d]/95 border border-[#F6465D]/40 text-[#d1d4dc]'
              : 'bg-[#1e222d]/95 border border-[#F59E0B]/40 text-[#d1d4dc]'
          }`}
          onClick={() => dismissErrorToast(toast.id)}
        >
          <span
            className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${
              toast.severity === 'error' ? 'bg-[#F6465D]' : 'bg-[#F59E0B]'
            }`}
          />
          <span className="flex-1 leading-snug">{toast.message}</span>
          <button
            className="ml-1 shrink-0 text-[#787b86] hover:text-[#d1d4dc] transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              dismissErrorToast(toast.id);
            }}
            aria-label="关闭提示"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
