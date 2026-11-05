import React, { useState, useEffect, useRef } from "react";

    function DirectApplyView({ runStatus }: any) {
      const logs = (runStatus && Array.isArray(runStatus.logs)) ? runStatus.logs : [];
      const isRunning = Boolean(runStatus && runStatus.is_running);

      const [intakeMode, setIntakeMode] = useState('feed'); // 'feed' | 'url' | 'session'
      const [feedText, setFeedText] = useState('');
      const [feedResult, setFeedResult] = useState(null);
      const [analyzingFeed, setAnalyzingFeed] = useState(false);

      const [url, setUrl] = useState('');
      const [urlResult, setUrlResult] = useState(null);
      const [analyzingUrl, setAnalyzingUrl] = useState(false);

      const [importPortal, setImportPortal] = useState('indeed');
      const [importRawText, setImportRawText] = useState('');
      const [importing, setImporting] = useState(false);
      const [importSuccess, setImportSuccess] = useState(null);

      const [visible, setVisible] = useState(false);
      const [detectedPortal, setDetectedPortal] = useState('Universal ATS');
      const [currentStage, setCurrentStage] = useState(1);
      const [executionStatus, setExecutionStatus] = useState(null);
      const logContainerRef = useRef(null);

      useEffect(() => {
        const u = (url || '').toLowerCase();
        if (u.includes('indeed')) setDetectedPortal('Indeed India / Global');
        else if (u.includes('greenhouse')) setDetectedPortal('Greenhouse ATS');
        else if (u.includes('lever.co')) setDetectedPortal('Lever ATS');
        else if (u.includes('workday')) setDetectedPortal('Workday ATS');
        else if (u.includes('ashby')) setDetectedPortal('Ashby ATS');
        else if (u.includes('smartrecruiters')) setDetectedPortal('SmartRecruiters ATS');
        else if (u.includes('instahyre')) setDetectedPortal('Instahyre');
        else if (u.includes('naukri')) setDetectedPortal('Naukri Direct Apply');
        else if (u.includes('linkedin')) setDetectedPortal('LinkedIn Direct Apply');
        else setDetectedPortal('Universal ATS / Corporate Career Page');
      }, [url]);

      // Stage tracking based on logs
      useEffect(() => {
        if (isRunning && logs.length > 0) {
          const allText = logs.join(' ').toLowerCase();
          if (allText.includes('confirm') || allText.includes('receipt') || allText.includes('successfully applied')) {
            setCurrentStage(5);
            setExecutionStatus({ status: 'APPLIED', message: 'Application submitted and verified successfully!' });
          } else if (allText.includes('upload') || allText.includes('resume attached') || allText.includes('file')) {
            setCurrentStage(4);
          } else if (allText.includes('question') || allText.includes('screening') || allText.includes('solving')) {
            setCurrentStage(3);
          } else if (allText.includes('tailor') || allText.includes('generating') || allText.includes('pdf')) {
            setCurrentStage(2);
          } else {
            setCurrentStage(1);
          }
        }
      }, [logs, isRunning]);

      useEffect(() => {
        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
      }, [logs]);

      const handleAnalyzeFeed = async () => {
        if (!feedText.trim()) return alert("Please paste a job alert message, email body, or notification snippet.");
        setAnalyzingFeed(true);
        setFeedResult(null);
        try {
          const res = await fetch('/api/intake/analyze-feed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ feed_text: feedText })
          });
          const d = await res.json();
          if (d.success) {
            setFeedResult(d);
            if (d.extracted?.job_url) {
              setUrl(d.extracted.job_url);
            }
          } else {
            alert(d.error || "Analysis failed");
          }
        } catch (e) {
          alert("Error analyzing feed: " + e);
        } finally {
          setAnalyzingFeed(false);
        }
      };

      const handleAnalyzeUrl = async () => {
        if (!url.trim()) return alert("Please enter a valid job URL to analyze.");
        setAnalyzingUrl(true);
        setUrlResult(null);
        try {
          const res = await fetch('/api/intake/analyze-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url.trim() })
          });
          const d = await res.json();
          if (d.success) {
            setUrlResult(d);
          } else {
            alert(d.error || "URL Analysis failed");
          }
        } catch (e) {
          alert("Error inspecting URL: " + e);
        } finally {
          setAnalyzingUrl(false);
        }
      };

      const handleApply = async (targetUrl) => {
        const toApply = targetUrl || url;
        if (!toApply) return alert("Please enter a job URL or analyze a feed containing a link");
        setExecutionStatus(null);
        setCurrentStage(1);
        try {
          const res = await fetch('/api/intake/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: toApply, visible })
          });
          const d = await res.json();
          if (!d.success) alert(d.error);
        } catch (e) {
          alert("Error: " + e);
        }
      };

      const handleImportSession = async () => {
        if (!importRawText.trim()) return alert("Please paste a cURL command or Cookie JSON");
        setImporting(true);
        setImportSuccess(null);
        try {
          const res = await fetch('/api/session/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portal: importPortal, data: importRawText.trim() })
          });
          const d = await res.json();
          if (d.success) {
            setImportSuccess(`Verified & imported ${d.cookie_count} cookies for ${d.portal.toUpperCase()}!`);
            setImportRawText('');
          } else {
            alert(d.error || "Import failed");
          }
        } catch (e) {
          alert("Error: " + e);
        } finally {
          setImporting(false);
        }
      };

      const stages = [
        { id: 1, name: "Detecting Portal / ATS", desc: "Indeed / Greenhouse / Lever / Workday" },
        { id: 2, name: "Tailoring Resume", desc: "Dynamic PDF matching JD keywords" },
        { id: 3, name: "Answering Questions", desc: "Smart screening & compliance solver" },
        { id: 4, name: "Uploading Resume", desc: "ATS-validated PDF attachment" },
        { id: 5, name: "Verified Receipt", desc: "Strict proof of application submission" }
      ];

      return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Controls & Mode Switcher */}
          <div className="glass-card p-6 rounded-2xl space-y-5 lg:col-span-1">
            <div>
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-base text-white flex items-center gap-2">
                  <span>🎯</span> Indeed &amp; Direct Intake Hub
                </h3>
                <span className="text-[10px] px-2 py-0.5 rounded bg-brand-500/20 text-brand-300 font-mono">
                  AI Fit Evaluator
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Drop raw notification messages or direct job URLs for suitability analysis and 1-click apply.
              </p>
            </div>

            {/* Mode Switcher Tabs */}
            <div className="flex rounded-xl bg-slate-900/90 p-1 border border-white/10">
              <button
                onClick={() => setIntakeMode('feed')}
                className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition ${
                  intakeMode === 'feed' ? 'bg-brand-600 text-white shadow' : 'text-slate-400 hover:text-white'
                }`}>
                💬 Message Feed
              </button>
              <button
                onClick={() => setIntakeMode('url')}
                className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition ${
                  intakeMode === 'url' ? 'bg-brand-600 text-white shadow' : 'text-slate-400 hover:text-white'
                }`}>
                🔗 Direct Job URL
              </button>
              <button
                onClick={() => setIntakeMode('session')}
                className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition ${
                  intakeMode === 'session' ? 'bg-brand-600 text-white shadow' : 'text-slate-400 hover:text-white'
                }`}>
                🍪 Import Session
              </button>
            </div>

            {/* MODE 1: MESSAGE / EMAIL / NOTIFICATION FEED */}
            {intakeMode === 'feed' && (
              <div className="space-y-3.5">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Paste Job Notification / Recruiter Message
                  </label>
                  <textarea
                    rows={4}
                    value={feedText}
                    onChange={e => setFeedText(e.target.value)}
                    placeholder="Paste hiring alert, email body, in-app notification snippet, or WhatsApp alert here... e.g.: Hiring React Developer (3-5 Yrs) at Razorpay in Bengaluru. Apply at https://in.indeed.com/viewjob?jk=..."
                    className="w-full bg-slate-900 border border-white/10 rounded-xl p-3 text-xs text-slate-200 focus:outline-none focus:border-brand-500 font-mono resize-none"
                  />
                </div>

                <div className="flex gap-2">
                  <button
                    disabled={analyzingFeed || !feedText.trim()}
                    onClick={handleAnalyzeFeed}
                    className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold text-xs shadow transition flex items-center justify-center gap-1.5">
                    <span>{analyzingFeed ? '⏳' : '🔍'}</span>
                    <span>{analyzingFeed ? 'Analyzing Suitability...' : 'Analyze Message & Check Fit'}</span>
                  </button>
                  {feedText && (
                    <button
                      onClick={() => { setFeedText(''); setFeedResult(null); }}
                      className="px-3 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 text-xs font-mono">
                      Clear
                    </button>
                  )}
                </div>

                {/* Analysis Outcome Card */}
                {feedResult && (
                  <div className="bg-slate-950 p-3.5 rounded-xl border border-white/10 space-y-2.5 text-xs font-mono">
                    <div className="flex items-center justify-between border-b border-white/10 pb-2">
                      <div>
                        <span className="font-bold text-white block text-sm">{feedResult.extracted?.role_title}</span>
                        <span className="text-slate-400 text-[11px]">{feedResult.extracted?.company} · {feedResult.extracted?.location}</span>
                      </div>
                      <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                        feedResult.evaluation?.recommendation === 'APPLY' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                        feedResult.evaluation?.recommendation === 'REVIEW' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' :
                        'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                      }`}>
                        {feedResult.evaluation?.score}% {feedResult.evaluation?.recommendation}
                      </span>
                    </div>

                    <p className="text-[11px] text-slate-300 leading-relaxed">
                      {feedResult.evaluation?.verdict}
                    </p>

                    {feedResult.evaluation?.matched_skills?.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {feedResult.evaluation.matched_skills.map((s, idx) => (
                          <span key={idx} className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 text-[10px] border border-emerald-500/30">
                            ✓ {s}
                          </span>
                        ))}
                      </div>
                    )}

                    {feedResult.extracted?.job_url ? (
                      <div className="pt-2 border-t border-white/10 space-y-2">
                        <div className="text-[10px] text-slate-400 truncate">
                          <span className="text-slate-500">Target URL:</span> {feedResult.extracted.job_url}
                        </div>
                        <button
                          disabled={runStatus.is_running}
                          onClick={() => handleApply(feedResult.extracted.job_url)}
                          className="w-full py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition shadow flex items-center justify-center gap-1.5">
                          <span>🚀</span> Apply to This Opportunity Now
                        </button>
                      </div>
                    ) : (
                      <div className="text-[10px] text-amber-400 pt-1">
                        ⚠️ No direct URL found in message. Paste the job URL in the 'Direct Job URL' tab to apply.
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* MODE 2: DIRECT JOB URL */}
            {intakeMode === 'url' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">Direct Job URL</label>
                  <div className="relative">
                    <input
                      type="text"
                      value={url}
                      onChange={e => setUrl(e.target.value)}
                      placeholder="https://in.indeed.com/viewjob?jk=... or https://jobs.lever.co/..."
                      className="w-full bg-slate-900 border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-brand-500 font-mono pr-24"
                    />
                    {url && (
                      <span className="absolute right-2.5 top-2.5 px-2 py-0.5 rounded bg-brand-500/20 text-brand-300 text-[10px] font-mono border border-brand-500/30">
                        {detectedPortal}
                      </span>
                    )}
                  </div>
                </div>

                {/* Quick Presets */}
                <div className="space-y-1.5">
                  <span className="text-[11px] text-slate-400 font-medium">Quick Presets:</span>
                  <div className="flex flex-wrap gap-1.5">
                    <button onClick={() => setUrl('https://in.indeed.com/jobs?q=React+Developer&l=Bengaluru')} className="px-2 py-1 rounded bg-indigo-950/80 hover:bg-indigo-900 text-indigo-300 text-[10px] font-mono border border-indigo-500/30">Indeed India</button>
                    <button onClick={() => setUrl('https://boards.greenhouse.io/example/jobs/12345')} className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono">Greenhouse</button>
                    <button onClick={() => setUrl('https://jobs.lever.co/example/abcdef')} className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono">Lever</button>
                    <button onClick={() => setUrl('https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/India-Bengaluru/Senior-Frontend-Engineer_JR198542')} className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono">Workday (NVIDIA)</button>
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    disabled={analyzingUrl || !url}
                    onClick={handleAnalyzeUrl}
                    className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition border border-white/10 flex items-center justify-center gap-1.5">
                    <span>{analyzingUrl ? '⏳' : '🔍'}</span>
                    <span>{analyzingUrl ? 'Inspecting Page...' : 'Inspect Page & Check Fit'}</span>
                  </button>
                </div>

                {/* Live URL Inspection Outcome */}
                {urlResult && (
                  <div className="bg-slate-950 p-3 rounded-xl border border-white/10 space-y-2 text-xs font-mono">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white truncate max-w-[180px]">{urlResult.details?.title}</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        urlResult.evaluation?.score >= 70 ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300'
                      }`}>
                        {urlResult.evaluation?.score}% Match
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-400">
                      {urlResult.details?.company} · {urlResult.details?.location}
                    </div>
                    <div className="text-[10px] text-indigo-300 bg-indigo-950/40 p-1.5 rounded border border-indigo-500/20">
                      Mode: {urlResult.apply_mode || "Automated Flow"}
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-2 pt-1">
                  <input type="checkbox" id="visibleDirect" checked={visible} onChange={e => setVisible(e.target.checked)} className="rounded border-white/10 text-brand-600 focus:ring-0" />
                  <label htmlFor="visibleDirect" className="text-xs text-slate-300">Visible Browser (Watch stealth form filling)</label>
                </div>

                <button
                  disabled={runStatus.is_running || !url}
                  onClick={() => handleApply(url)}
                  className="w-full py-3.5 rounded-xl bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 disabled:opacity-50 text-white font-bold text-xs shadow-lg shadow-brand-500/25 transition flex items-center justify-center gap-2">
                  <span>⚡</span>
                  <span>Launch Direct Application</span>
                </button>
              </div>
            )}

            {/* MODE 3: DIRECT SESSION / COOKIE IMPORTER */}
            {intakeMode === 'session' && (
              <div className="space-y-4">
                <div className="bg-slate-950 p-3.5 rounded-xl border border-white/10 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                      <span>🍪</span> 100% Anti-Bot Cloudflare Bypass Importer
                    </span>
                    <select
                      value={importPortal}
                      onChange={e => setImportPortal(e.target.value)}
                      className="bg-slate-900 border border-white/10 rounded px-2 py-1 text-xs text-white font-mono">
                      <option value="indeed">Indeed</option>
                      <option value="naukri">Naukri</option>
                      <option value="linkedin">LinkedIn</option>
                      <option value="instahyre">Instahyre</option>
                    </select>
                  </div>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Cloudflare or Captchas blocking automated login? Import your active session directly from your normal browser in 3 easy steps:
                  </p>
                  <ol className="text-[10px] text-slate-400 space-y-1 list-decimal list-inside font-mono">
                    <li>In your regular Chrome, log in to <b>{importPortal}.com</b> normally.</li>
                    <li>Press <span className="text-white bg-slate-900 px-1 rounded">Cmd + Opt + I</span> → <b>Network</b> tab → Refresh page (<span className="text-white bg-slate-900 px-1 rounded">Cmd + R</span>).</li>
                    <li>Right-click the top network request → <b>Copy</b> → <b>Copy as cURL</b>.</li>
                  </ol>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Paste cURL or Cookie-Editor JSON:
                  </label>
                  <textarea
                    rows={4}
                    value={importRawText}
                    onChange={e => setImportRawText(e.target.value)}
                    placeholder="Paste full 'curl https://...' command or Cookie-Editor JSON array here..."
                    className="w-full bg-slate-900 border border-white/10 rounded-xl p-3 text-xs text-slate-200 focus:outline-none focus:border-brand-500 font-mono resize-none"
                  />
                </div>

                <button
                  disabled={importing || !importRawText.trim()}
                  onClick={handleImportSession}
                  className="w-full py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold text-xs shadow-lg shadow-emerald-500/20 transition flex items-center justify-center gap-2">
                  <span>📥</span>
                  <span>{importing ? 'Importing Session...' : `Save Authenticated ${importPortal.toUpperCase()} Session`}</span>
                </button>

                {importSuccess && (
                  <div className="bg-emerald-950/80 p-3 rounded-xl border border-emerald-500/30 text-emerald-300 text-xs font-mono flex items-center gap-2">
                    <span>✓</span>
                    <span>{importSuccess}</span>
                  </div>
                )}
              </div>
            )}

            {/* Active Stepper Visualizer */}
            <div className="border-t border-white/10 pt-4 space-y-3">
              <h4 className="text-xs font-semibold text-slate-300">Execution Stepper (5 Stages):</h4>
              <div className="space-y-2">
                {stages.map(s => {
                  const isActive = runStatus.is_running && currentStage === s.id;
                  const isDone = currentStage > s.id;
                  return (
                    <div key={s.id} className={`p-2.5 rounded-xl border flex items-center gap-3 transition ${
                      isActive ? 'bg-brand-950/60 border-brand-500/60 stepper-active text-white' :
                      isDone ? 'bg-emerald-950/30 border-emerald-500/30 text-emerald-300' :
                      'bg-slate-900/40 border-white/5 text-slate-500'
                    }`}>
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center font-mono text-xs font-bold ${
                        isActive ? 'bg-brand-500 text-white animate-pulse' :
                        isDone ? 'bg-emerald-500 text-slate-950' :
                        'bg-slate-800 text-slate-400'
                      }`}>
                        {isDone ? '✓' : s.id}
                      </div>
                      <div className="flex-1">
                        <div className="font-semibold text-xs">{s.name}</div>
                        <div className="text-[10px] text-slate-400">{s.desc}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Real-Time Live Streaming Console */}
          <div className="glass-card rounded-2xl flex flex-col overflow-hidden lg:col-span-2 border border-white/10">
            <div className="px-5 py-3 border-b border-white/10 flex items-center justify-between bg-slate-900/60">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${isRunning ? 'bg-emerald-400 animate-ping' : 'bg-slate-500'}`}></span>
                <h4 className="font-mono text-xs text-slate-300 font-semibold">Live Direct Apply Console</h4>
              </div>
              <span className="text-[11px] text-slate-500 font-mono">{logs.length} lines logged</span>
            </div>

            <div ref={logContainerRef} className="p-5 flex-1 max-h-[520px] overflow-y-auto custom-scrollbar font-mono text-xs text-slate-300 whitespace-pre-wrap leading-relaxed bg-slate-950/80">
              {logs.length === 0 ? (
                <div className="text-slate-600 italic">No direct apply task active. Enter a URL or paste a feed above and click Launch to watch real-time steps...</div>
              ) : (
                logs.map((l, i) => (
                  <div key={i} className="py-0.5">{l}</div>
                ))
              )}
            </div>

            {/* Verified Outcome Pill Banner */}
            {executionStatus && (
              <div className={`px-5 py-3 border-t text-xs font-semibold flex items-center justify-between ${
                executionStatus.status === 'APPLIED' ? 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300' : 'bg-amber-950/80 border-amber-500/40 text-amber-300'
              }`}>
                <span>{executionStatus.message}</span>
                <span className="px-2 py-0.5 rounded font-mono text-[11px] bg-slate-900 border border-white/10">{executionStatus.status}</span>
              </div>
            )}
          </div>
        </div>
      );
    }



export default DirectApplyView;
