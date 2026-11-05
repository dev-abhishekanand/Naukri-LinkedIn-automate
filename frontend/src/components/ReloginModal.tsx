import React, { useState } from 'react';

interface ReloginModalProps {
  reloginModal: {
    open: boolean;
    site: string;
    portalKey?: string;
    command: string;
  };
  setReloginModal: React.Dispatch<
    React.SetStateAction<{
      open: boolean;
      site: string;
      portalKey?: string;
      command: string;
    }>
  >;
}

export const ReloginModal: React.FC<ReloginModalProps> = ({ reloginModal, setReloginModal }) => {
  const [importText, setImportText] = useState('');
  const [loading, setLoading] = useState(false);

  if (!reloginModal.open) return null;
  const target = reloginModal.portalKey || 'naukri';

  const handleLaunchChrome = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/chrome/open-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ site: target }),
      });
      const data = await res.json();
      if (data.success) {
        alert(data.message || `Google Chrome window opened for ${target.toUpperCase()}! Complete your login in Chrome.`);
      } else {
        alert('Error: ' + (data.error || 'Failed to launch browser'));
      }
    } catch (err: any) {
      alert('Network error: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleResetSession = async () => {
    if (confirm(`Remove old session for ${target.toUpperCase()} and start fresh?`)) {
      try {
        const res = await fetch('/api/session/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ portal: target }),
        });
        const d = await res.json();
        alert(d.message || 'Session reset!');
        window.location.reload();
      } catch (err: any) {
        alert('Reset error: ' + err.message);
      }
    }
  };

  const handleImportSession = async () => {
    const val = importText.trim();
    if (!val) return alert('Please paste cURL command or Cookie JSON');
    try {
      const res = await fetch('/api/session/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ portal: target, data: val }),
      });
      const d = await res.json();
      if (d.success) {
        alert(`✅ Verified & saved ${d.cookie_count} authenticated cookies for ${d.portal.toUpperCase()}!`);
        setReloginModal({ open: false, site: '', command: '' });
        window.location.reload();
      } else {
        alert('Import error: ' + (d.error || 'Failed to parse cookies'));
      }
    } catch (e: any) {
      alert('Network error: ' + e.message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-white/10 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
        <div className="flex justify-between items-center pb-2 border-b border-white/10">
          <h3 className="font-bold text-white text-base">
            🔑 Re-authenticate {reloginModal.site}
          </h3>
          <button
            onClick={() => setReloginModal({ open: false, site: '', command: '' })}
            className="text-slate-400 hover:text-white px-2 py-1 rounded bg-white/5"
          >
            ✕ Close
          </button>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed">
          Active session is missing or expired. To re-authenticate with anti-bot cookies, click "Launch Chrome Window" below or run in terminal:
        </p>
        <div className="bg-slate-950 p-3.5 rounded-xl border border-white/10 font-mono text-xs text-brand-300 flex items-center justify-between">
          <span className="select-all">{reloginModal.command}</span>
          <button
            onClick={() => {
              navigator.clipboard.writeText(reloginModal.command);
              alert('Copied command!');
            }}
            className="ml-2 px-2 py-1 bg-brand-600 hover:bg-brand-500 text-white rounded text-[11px] font-sans"
          >
            Copy
          </button>
        </div>
        <div className="flex justify-between items-center pt-2">
          <button
            onClick={handleResetSession}
            className="px-3 py-2 rounded-xl bg-rose-950/70 hover:bg-rose-900 border border-rose-500/40 text-rose-300 text-xs font-semibold"
          >
            🗑️ Reset This Session
          </button>

          <button
            disabled={loading}
            onClick={handleLaunchChrome}
            className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-semibold shadow-lg shadow-brand-600/30"
          >
            {loading ? 'Launching...' : '🚀 Launch Chrome Window'}
          </button>
        </div>

        {/* Instant Cookie / cURL Session Importer (Bypasses Cloudflare loops 100%) */}
        <div className="border-t border-white/10 pt-3 space-y-2 text-left">
          <span className="text-[11px] font-semibold text-slate-200 block">
            ⚡ Or Import from your normal Chrome (Zero Captcha):
          </span>
          <p className="text-[10px] text-slate-400 leading-tight">
            In your regular Chrome where you browse normally: Log in to {reloginModal.site} → Press F12 / Cmd+Opt+I → Network tab → Refresh → Right-click top request → Copy as cURL → Paste below:
          </p>
          <textarea
            rows={2}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder="Paste 'Copy as cURL' or Cookie-Editor JSON here..."
            className="w-full bg-slate-950 border border-white/10 rounded-lg p-2 text-[10px] text-slate-200 font-mono resize-none focus:outline-none focus:border-brand-500"
          />
          <div className="flex justify-end">
            <button
              onClick={handleImportSession}
              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow transition flex items-center gap-1.5"
            >
              <span>📥</span> Import Session Instantly
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
