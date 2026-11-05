import React from 'react';

interface LogModalProps {
  logModal: {
    open: boolean;
    title: string;
    content: string;
  };
  setLogModal: React.Dispatch<
    React.SetStateAction<{
      open: boolean;
      title: string;
      content: string;
    }>
  >;
}

export const LogModal: React.FC<LogModalProps> = ({ logModal, setLogModal }) => {
  if (!logModal.open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-white/10 rounded-2xl max-w-4xl w-full p-6 max-h-[85vh] flex flex-col shadow-2xl">
        <div className="flex justify-between items-center pb-4 border-b border-white/10">
          <h3 className="font-bold text-white text-base font-mono">
            📄 Viewing Log: {logModal.title}
          </h3>
          <button
            onClick={() => setLogModal({ open: false, title: '', content: '' })}
            className="text-slate-400 hover:text-white px-2 py-1 rounded bg-white/5"
          >
            ✕ Close
          </button>
        </div>
        <pre className="flex-1 overflow-auto bg-slate-950 p-4 rounded-xl mt-4 font-mono text-xs text-slate-300 whitespace-pre-wrap leading-relaxed custom-scrollbar">
          {logModal.content || 'Log file is empty or not yet generated.'}
        </pre>
      </div>
    </div>
  );
};
