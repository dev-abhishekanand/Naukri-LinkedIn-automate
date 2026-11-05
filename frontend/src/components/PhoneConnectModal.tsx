import React, { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';

interface PhoneConnectModalProps {
  open: boolean;
  onClose: () => void;
}

export const PhoneConnectModal: React.FC<PhoneConnectModalProps> = ({ open, onClose }) => {
  const [networkInfo, setNetworkInfo] = useState<{
    local_ip: string;
    port: number;
    url: string;
    hostname: string;
    mdns_url: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open) {
      fetch('/api/network-info')
        .then((r) => r.json())
        .then((d) => setNetworkInfo(d))
        .catch(() => {
          // Fallback to window host
          const host = window.location.hostname;
          const port = window.location.port || '8585';
          setNetworkInfo({
            local_ip: host,
            port: Number(port),
            url: `http://${host}:${port}`,
            hostname: host,
            mdns_url: `http://${host}:${port}`,
          });
        });
    }
  }, [open]);

  if (!open) return null;

  const targetUrl = networkInfo?.url || `http://${window.location.host}`;

  const copyUrl = () => {
    navigator.clipboard.writeText(targetUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-white/10 rounded-2xl max-w-md w-full p-6 space-y-5 shadow-2xl">
        <div className="flex justify-between items-center pb-3 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">📱</span>
            <div>
              <h3 className="font-bold text-white text-base leading-none">
                Open on Phone (Web App)
              </h3>
              <p className="text-[11px] text-slate-400 mt-1 font-mono">
                Install as standalone app on iOS & Android
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white px-2 py-1 rounded bg-white/5"
          >
            ✕
          </button>
        </div>

        {/* QR Code Card */}
        <div className="bg-white p-4 rounded-xl flex flex-col items-center justify-center shadow-inner mx-auto w-fit">
          <QRCodeSVG
            value={targetUrl}
            size={180}
            level="M"
            includeMargin={true}
          />
          <span className="text-[10px] text-slate-500 font-mono mt-1 font-semibold">
            Scan with Phone Camera
          </span>
        </div>

        {/* URL Pill & Copy */}
        <div className="space-y-1.5">
          <span className="text-[11px] font-semibold text-slate-300 block">
            Direct Phone Browser Link:
          </span>
          <div className="bg-slate-950 p-2.5 rounded-xl border border-white/10 flex items-center justify-between font-mono text-xs text-brand-300">
            <span className="select-all truncate mr-2">{targetUrl}</span>
            <button
              onClick={copyUrl}
              className="px-2.5 py-1 bg-brand-600 hover:bg-brand-500 text-white rounded text-[11px] font-sans font-semibold shrink-0"
            >
              {copied ? '✓ Copied' : 'Copy'}
            </button>
          </div>
          {networkInfo?.mdns_url && networkInfo.mdns_url !== targetUrl && (
            <p className="text-[10px] text-slate-400 font-mono">
              Also accessible at: <span className="text-slate-300 select-all">{networkInfo.mdns_url}</span>
            </p>
          )}
        </div>

        {/* Install instructions */}
        <div className="bg-slate-950/60 p-3.5 rounded-xl border border-white/5 space-y-2 text-xs text-slate-300">
          <div className="font-semibold text-white flex items-center gap-1.5">
            <span>✨</span> How to install as a Home Screen App:
          </div>
          <div className="space-y-1.5 text-[11px] text-slate-300 leading-relaxed">
            <p>
              🍏 <strong className="text-white">iPhone (Safari):</strong> Scan QR or open link in Safari → tap <strong className="text-white">Share</strong> icon → tap <strong className="text-emerald-400">Add to Home Screen</strong>.
            </p>
            <p>
              🤖 <strong className="text-white">Android (Chrome):</strong> Scan QR or open in Chrome → tap <strong className="text-emerald-400">Install App</strong> or Menu (⋮) → <strong className="text-emerald-400">Add to Home screen</strong>.
            </p>
          </div>
        </div>

        <div className="text-[10px] text-amber-300/80 bg-amber-950/30 border border-amber-500/20 px-3 py-2 rounded-lg flex items-center gap-2">
          <span>📶</span>
          <span>Ensure your phone is connected to the same Wi-Fi network as this Mac.</span>
        </div>
      </div>
    </div>
  );
};
