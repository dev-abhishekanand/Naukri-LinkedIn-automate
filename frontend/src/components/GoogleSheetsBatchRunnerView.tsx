import React, { useState, useEffect } from "react";

    function GoogleSheetsBatchRunnerView({ sheetsData, loading, reload, runStatus }: any) {
      const [limit, setLimit] = useState(10);
      const [roleFilter, setRoleFilter] = useState('');
      const [visible, setVisible] = useState(false);
      const [launchingBatch, setLaunchingBatch] = useState(false);
      const [statusOverrideModal, setStatusOverrideModal] = useState({ open: false, row: null, status: 'APPLIED', reason: '' });
      const [batchOutcome, setBatchOutcome] = useState(null);

      const fetchOutcome = async () => {
        try {
          const res = await fetch('/api/google-sheets/batch-outcome');
          const d = await res.json();
          if (d.success && d.outcome) {
            setBatchOutcome(d.outcome);
          }
        } catch (e) {}
      };

      useEffect(() => {
        fetchOutcome();
      }, []);

      const handleBatchApply = async () => {
        setLaunchingBatch(true);
        try {
          const res = await fetch('/api/google-sheets/batch-apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ limit, role: roleFilter, visible })
          });
          const d = await res.json();
          if (d.success) {
            alert(`🚀 Sheet Batch Apply launched! Processing up to ${limit} pending jobs. Watch the live console banner above.`);
            setTimeout(fetchOutcome, 5000);
          } else {
            alert(d.error || "Could not launch batch run");
          }
        } catch (e) {
          alert("Error: " + e);
        } finally {
          setLaunchingBatch(false);
        }
      };

      const handleApplySingleRow = async (row) => {
        try {
          const res = await fetch('/api/google-sheets/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              row_index: row.row_index,
              url: row.direct_apply_url,
              company: row.company,
              title: row.job_title,
              resume_path: row.tailored_resume_path
            })
          });
          const d = await res.json();
          alert(d.message || "Launched application for row #" + row.row_index);
        } catch (e) {
          alert("Error: " + e);
        }
      };

      const handleStatusOverride = async () => {
        if (!statusOverrideModal.row) return;
        try {
          const res = await fetch('/api/google-sheets/update-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              url: statusOverrideModal.row.direct_apply_url,
              row_index: statusOverrideModal.row.row_index,
              status: statusOverrideModal.status,
              reason: statusOverrideModal.reason
            })
          });
          const d = await res.json();
          if (d.success) {
            alert("Updated Column 10 in Google Sheet to: " + statusOverrideModal.status);
            setStatusOverrideModal({ open: false, row: null, status: 'APPLIED', reason: '' });
            reload();
          } else {
            alert(d.error || "Failed to update status");
          }
        } catch (e) {
          alert("Error: " + e);
        }
      };

      if (loading) return <div className="text-xs text-slate-400 p-8 text-center">Syncing live records with Google Sheets 'Apply Yourself' tab...</div>;

      const jobs = sheetsData?.jobs || [];
      const pendingCount = sheetsData?.stats?.pending || 0;
      const totalCount = sheetsData?.stats?.total || 0;
      const appliedCount = sheetsData?.stats?.applied || 0;
      const reviewCount = (sheetsData?.stats?.review_required || 0) + (sheetsData?.stats?.failed || 0);

      return (
        <div className="space-y-6">
          {/* Top Control Bar for Batch Runner */}
          <div className="glass-card p-5 rounded-2xl border border-amber-500/30 bg-amber-950/10 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-bold text-base text-white flex items-center gap-2">
                  <span>⚡</span> Google Sheet 'Apply Yourself' Batch Runner Engine
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Reads pending jobs directly from Google Sheet Column 7, auto-applies via Universal ATS, and updates Column 10 (`Status`) live
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 font-mono font-semibold">
                  {pendingCount} Pending in Sheet
                </span>
                <button onClick={() => { reload(); fetchOutcome(); }} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono transition">
                  Refresh Sheet ⟳
                </button>
              </div>
            </div>

            {/* Batch Controls Bar */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-2">
              <div>
                <label className="block text-[11px] font-semibold text-slate-300 mb-1">Batch Limit (Jobs to Apply)</label>
                <div className="flex gap-1.5">
                  {[5, 10, 25, 50].map(n => (
                    <button
                      key={n}
                      onClick={() => setLimit(n)}
                      className={`flex-1 py-1.5 rounded-lg text-xs font-mono font-bold transition ${limit === n ? 'bg-amber-500 text-slate-950' : 'bg-slate-900 text-slate-400 hover:text-white border border-white/5'}`}>
                      {n}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-300 mb-1">Filter Job Title Keyword</label>
                <input
                  type="text"
                  value={roleFilter}
                  onChange={e => setRoleFilter(e.target.value)}
                  placeholder="e.g. React Developer"
                  className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-brand-500 font-mono"
                />
              </div>

              <div className="flex items-center gap-2 pt-4">
                <input
                  type="checkbox"
                  id="visibleSheet"
                  checked={visible}
                  onChange={e => setVisible(e.target.checked)}
                  className="rounded border-white/10 text-brand-600 focus:ring-0"
                />
                <label htmlFor="visibleSheet" className="text-xs text-slate-300 font-medium">Visible Browser Mode</label>
              </div>

              <div className="pt-2">
                <button
                  disabled={runStatus.is_running || launchingBatch}
                  onClick={handleBatchApply}
                  className="w-full py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 disabled:opacity-50 text-slate-950 font-extrabold text-xs shadow-lg shadow-amber-950/40 transition flex items-center justify-center gap-2">
                  <span>⚡</span>
                  <span>{runStatus.is_running ? 'Batch Task Running...' : `Auto-Apply Pending Sheet Jobs (${limit} Batch)`}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Dedicated Transparent Post-Batch Outcome Card */}
          {batchOutcome && (
            <div className={`p-5 rounded-2xl border ${
              batchOutcome.unapplied_count > 0 
                ? 'border-amber-500/40 bg-amber-950/20' 
                : 'border-emerald-500/40 bg-emerald-950/20'
            } space-y-3`}>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{batchOutcome.unapplied_count > 0 ? '⚠️' : '🎉'}</span>
                  <div>
                    <h4 className="font-bold text-sm text-white">
                      {batchOutcome.unapplied_count > 0 
                        ? `${batchOutcome.unapplied_count} jobs left for apply. Just go and apply yourself!` 
                        : 'Batch Run 100% Complete — All processed jobs were automatically applied!'}
                    </h4>
                    <p className="text-xs text-slate-400 font-mono mt-0.5">
                      Batch finished: {batchOutcome.timestamp} · Total attempted: {batchOutcome.total_processed} · Applied: {batchOutcome.applied_count} · Left: {batchOutcome.unapplied_count}
                    </p>
                  </div>
                </div>
                <button onClick={fetchOutcome} className="text-xs text-slate-400 hover:text-white font-mono px-2 py-1 rounded bg-slate-800">
                  Refresh Outcome ⟳
                </button>
              </div>

              {batchOutcome.unapplied_jobs?.length > 0 && (
                <div className="space-y-2 pt-1">
                  <div className="text-xs font-semibold text-amber-300">
                    👉 Unapplied links from last batch run — click "Apply Yourself" to open directly:
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-64 overflow-y-auto custom-scrollbar">
                    {batchOutcome.unapplied_jobs.map((job, idx) => (
                      <div key={idx} className="bg-slate-900/90 border border-white/10 p-3 rounded-xl flex items-center justify-between gap-3 text-xs">
                        <div className="truncate pr-2">
                          <div className="font-bold text-white truncate">{job.title}</div>
                          <div className="text-[11px] text-slate-400 truncate">{job.company} · Row #{job.row_index}</div>
                          {job.reason && <div className="text-[10px] text-amber-400/90 font-mono truncate">{job.reason}</div>}
                        </div>
                        <a
                          href={job.url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs font-mono whitespace-nowrap shadow transition flex items-center gap-1"
                        >
                          <span>🔗</span> Apply Yourself
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Sheet KPI Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="glass-card p-4 rounded-2xl">
              <span className="text-[11px] font-medium text-slate-400">Total Rows in Sheet</span>
              <div className="text-2xl font-bold text-white">{totalCount}</div>
              <span className="text-[11px] text-slate-400 font-mono">Column 1 to 10 mapped</span>
            </div>
            <div className="glass-card p-4 rounded-2xl border-amber-500/20 bg-amber-950/10">
              <span className="text-[11px] font-medium text-amber-400">Pending External Apply</span>
              <div className="text-2xl font-bold text-amber-300">{pendingCount}</div>
              <span className="text-[11px] text-amber-400/80 font-mono">Status = 'PENDING'</span>
            </div>
            <div className="glass-card p-4 rounded-2xl border-emerald-500/20 bg-emerald-950/10">
              <span className="text-[11px] font-medium text-emerald-400">Successfully Applied</span>
              <div className="text-2xl font-bold text-emerald-300">{appliedCount}</div>
              <span className="text-[11px] text-emerald-400/80 font-mono">Column 10 = 'APPLIED'</span>
            </div>
            <div className="glass-card p-4 rounded-2xl">
              <span className="text-[11px] font-medium text-slate-400">Review Required / Failed</span>
              <div className="text-2xl font-bold text-slate-300">{reviewCount}</div>
              <span className="text-[11px] text-slate-400 font-mono">Captcha or complex ATS</span>
            </div>
          </div>

          {/* Table of Google Sheet Jobs */}
          <div className="glass-card rounded-2xl overflow-hidden border border-white/10">
            <div className="p-4 border-b border-white/10 flex items-center justify-between bg-slate-900/60">
              <div>
                <h3 className="font-bold text-sm text-white flex items-center gap-2">
                  <span>📋</span> Live Sheet Records: 'Apply Yourself' Tab
                </h3>
                <p className="text-[11px] text-slate-400 font-mono mt-0.5">Spreadsheet ID: 15EFmeEcqtEJNqYDSYdL755534yc9RHqIsiIm7COa94I</p>
              </div>
              <span className="text-xs text-slate-400 font-mono">Showing {jobs.length} total rows</span>
            </div>

            <div className="overflow-x-auto max-h-[520px] custom-scrollbar">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950 text-slate-400 font-mono sticky top-0 border-b border-white/5">
                  <tr>
                    <th className="px-4 py-3">Row</th>
                    <th className="px-4 py-3">Company &amp; Role</th>
                    <th className="px-4 py-3">Platform</th>
                    <th className="px-4 py-3">Status (Col 10)</th>
                    <th className="px-4 py-3">Reason / Details</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {jobs.map((j, i) => (
                    <tr key={i} className="hover:bg-white/[0.02]">
                      <td className="px-4 py-2.5 font-mono text-slate-500">#{j.row_index || i + 2}</td>
                      <td className="px-4 py-2.5">
                        <div className="font-semibold text-white">{j.job_title}</div>
                        <span className="text-slate-400">{j.company}</span>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-slate-400">{j.platform || 'external'}</td>
                      <td className="px-4 py-2.5">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                          j.status === 'APPLIED' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                          j.status === 'PENDING' ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20' :
                          j.status === 'REVIEW_REQUIRED' ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20' :
                          'bg-slate-800 text-slate-400'
                        }`}>
                          {j.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 max-w-xs truncate">{j.reason || 'Queued for auto-apply'}</td>
                      <td className="px-4 py-2.5 text-right space-x-2 whitespace-nowrap">
                        {j.direct_apply_url && (
                          <a href={j.direct_apply_url} target="_blank" rel="noreferrer" className="text-brand-400 hover:underline font-mono text-[11px]">
                            URL ↗
                          </a>
                        )}
                        <button
                          onClick={() => handleApplySingleRow(j)}
                          className="px-2.5 py-1 rounded bg-brand-600 hover:bg-brand-500 text-white font-medium text-[11px]">
                          Apply
                        </button>
                        <button
                          onClick={() => setStatusOverrideModal({ open: true, row: j, status: j.status || 'APPLIED', reason: j.reason || '' })}
                          className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono">
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Status Override Modal */}
          {statusOverrideModal.open && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
              <div className="glass-card w-full max-w-md rounded-2xl p-6 border border-white/20 shadow-2xl space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-sm text-white">Update Sheet Status (Column 10)</h3>
                  <button onClick={() => setStatusOverrideModal({ open: false, row: null, status: 'APPLIED', reason: '' })} className="text-slate-400 hover:text-white">✕</button>
                </div>
                <div className="text-xs text-slate-300">
                  <strong>Job: </strong>{statusOverrideModal.row?.job_title} @ {statusOverrideModal.row?.company}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">New Status</label>
                  <select
                    value={statusOverrideModal.status}
                    onChange={e => setStatusOverrideModal({ ...statusOverrideModal, status: e.target.value })}
                    className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-white">
                    <option value="APPLIED">APPLIED</option>
                    <option value="PENDING">PENDING</option>
                    <option value="REVIEW_REQUIRED">REVIEW_REQUIRED</option>
                    <option value="FAILED">FAILED</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Reason / Notes</label>
                  <input
                    type="text"
                    value={statusOverrideModal.reason}
                    onChange={e => setStatusOverrideModal({ ...statusOverrideModal, reason: e.target.value })}
                    className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-white"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <button onClick={handleStatusOverride} className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs">
                    Save to Google Sheet
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      );
    }



export default GoogleSheetsBatchRunnerView;
