import React, { useState } from "react";

    function AiScannerView({ runStatus }: any) {
      const [mode, setMode] = useState('text');
      const [text, setText] = useState('');
      const [analyzing, setAnalyzing] = useState(false);
      const [result, setResult] = useState(null);
      const [applyingDirect, setApplyingDirect] = useState(false);
      const [directApplyReceipt, setDirectApplyReceipt] = useState(null);

      const [emailTo, setEmailTo] = useState('');
      const [emailSubject, setEmailSubject] = useState('');
      const [emailBody, setEmailBody] = useState('');
      const [savingDraft, setSavingDraft] = useState(false);
      const [draftResult, setDraftResult] = useState(null);
      const [sendingEmail, setSendingEmail] = useState(false);
      const [sendResult, setSendResult] = useState(null);

      const sampleCielsaPost = `🚀 HIRING: Frontend Developer (React.js / Next.js) at Cielsa Technologies!
Location: Bengaluru / Remote | Exp: 3-5 Years | Immediate Joiners Preferred.
We are looking for a strong React developer with experience in TypeScript, Tailwind CSS, Jest, and Redux Toolkit.
Direct Application Link: https://cielsa.com/careers/frontend-developer
Or send your CV to hr@cielsatech.com with subject 'Application - Frontend Developer'.`;

      const applyAnalysisData = (analysis) => {
        setResult(analysis);
        const contactEmail = analysis.contact_email || analysis.email_draft?.to_email || '';
        setEmailTo(contactEmail);
        setEmailSubject(analysis.email_draft?.subject || `Application for ${analysis.role_title || 'Frontend Developer'} - Abhishek Anand`);
        setEmailBody(analysis.email_draft?.body || '');
        setDraftResult(null);
        setSendResult(null);
        setDirectApplyReceipt(null);
      };

      const analyzeText = async (customText?: string) => {
        const targetText = customText || text;
        if (!targetText) return alert("Enter post text");
        setAnalyzing(true);
        try {
          const res = await fetch('/api/analyze-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: targetText })
          });
          const d = await res.json();
          if (d.success) applyAnalysisData(d.analysis);
          else alert(d.error);
        } catch (e) {
          alert("Error: " + e);
        } finally {
          setAnalyzing(false);
        }
      };

      const handleImageUpload = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onloadend = async () => {
          setAnalyzing(true);
          try {
            const res = await fetch('/api/analyze-image', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ image: reader.result, mime_type: file.type })
            });
            const d = await res.json();
            if (d.success) applyAnalysisData(d.analysis);
            else alert(d.error);
          } catch (err) {
            alert("Error: " + err);
          } finally {
            setAnalyzing(false);
          }
        };
        reader.readAsDataURL(file);
      };

      // ⚡ APPLY NOW BUTTON (Universal ATS Trigger)
      const handleApplyNow = async () => {
        const jobUrl = result?.application_link || result?.apply_url || (text.match(/https?:\/\/[^\s]+/)?.[0] || '');
        if (!jobUrl) {
          alert("No direct apply link detected in this post. You can use 'Prepare & Save Application Email Draft to Gmail' below to email the recruiter!");
          return;
        }

        setApplyingDirect(true);
        setDirectApplyReceipt({
          status: 'RUNNING',
          message: `Launching Universal ATS engine for: ${jobUrl}`,
          url: jobUrl,
          company: result?.company || 'Company'
        });

        try {
          const res = await fetch('/api/apply-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: jobUrl, visible: true })
          });
          const d = await res.json();
          if (d.success) {
            setDirectApplyReceipt({
              status: 'LAUNCHED',
              message: `🚀 Universal ATS application launched in background! Watch the live console banner above for real-time progress.`,
              url: jobUrl,
              pid: d.pid
            });
          } else {
            setDirectApplyReceipt({
              status: 'ERROR',
              message: d.error || 'Failed to trigger application'
            });
          }
        } catch (e) {
          setDirectApplyReceipt({
            status: 'ERROR',
            message: 'Network error: ' + e
          });
        } finally {
          setApplyingDirect(false);
        }
      };

      const handleOpenInChrome = async () => {
        const jobUrl = result?.application_link || result?.apply_url || (text.match(/https?:\/\/[^\s]+/)?.[0] || '');
        if (!jobUrl) return alert("No link found to open.");
        try {
          await fetch('/api/chrome/open-portal', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: jobUrl })
          });
        } catch (e) {
          window.open(jobUrl, '_blank');
        }
      };

      const handleSaveDraftToGmail = async () => {
        if (!emailTo) {
          alert("Please enter the recruiter email address in the 'To' field below.");
          return;
        }
        setSavingDraft(true);
        setDraftResult(null);
        try {
          const res = await fetch('/api/save-draft', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              to_email: emailTo,
              subject: emailSubject,
              body: emailBody,
              company: result?.company || '',
              role: result?.role_title || ''
            })
          });
          const d = await res.json();
          if (d.success) {
            setDraftResult(d.result || { message: "Draft saved directly into Gmail Drafts!" });
          } else {
            alert("Failed to save draft to Gmail: " + (d.error || d.message));
          }
        } catch (err) {
          alert("Network error: " + err);
        } finally {
          setSavingDraft(false);
        }
      };

      const handleSendEmailNow = async () => {
        if (!emailTo) return alert("Please enter the recruiter email address.");
        if (!confirm(`Are you sure you want to directly send this application email to ${emailTo}?`)) return;
        setSendingEmail(true);
        setSendResult(null);
        try {
          const res = await fetch('/api/send-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              to_email: emailTo,
              subject: emailSubject,
              body: emailBody,
              company: result?.company || '',
              role: result?.role_title || ''
            })
          });
          const d = await res.json();
          if (d.status === 'SENT' || d.success) {
            setSendResult({ success: true, message: `Application email sent successfully to ${emailTo}!` });
          } else {
            alert("Failed to send email: " + (d.message || d.error));
          }
        } catch (err) {
          alert("Error sending email: " + err);
        } finally {
          setSendingEmail(false);
        }
      };

      const detectedUrl = result?.application_link || result?.apply_url || (text.match(/https?:\/\/[^\s]+/)?.[0] || '');

      return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Input Section */}
          <div className="glass-card p-6 rounded-2xl space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-base text-white flex items-center gap-2">
                  <span>🧠</span> Gemini AI Post &amp; Flyer Evaluator
                </h3>
                <p className="text-xs text-slate-400 mt-1">Extract roles, eligibility scores, direct apply URLs, and 1-click apply</p>
              </div>
              <div className="flex bg-slate-900 rounded-lg p-0.5 border border-white/10 text-xs">
                <button onClick={() => setMode('text')} className={`px-3 py-1.5 rounded-md ${mode === 'text' ? 'bg-brand-600 text-white font-semibold' : 'text-slate-400'}`}>Text</button>
                <button onClick={() => setMode('image')} className={`px-3 py-1.5 rounded-md ${mode === 'image' ? 'bg-brand-600 text-white font-semibold' : 'text-slate-400'}`}>Flyer Image</button>
              </div>
            </div>

            {mode === 'text' ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-slate-400">Paste job post below:</span>
                  <button onClick={() => { setText(sampleCielsaPost); analyzeText(sampleCielsaPost); }} className="text-[11px] text-brand-400 hover:text-brand-300 font-mono underline">
                    📝 Load Cielsa Sample Post
                  </button>
                </div>
                <textarea rows={8} value={text} onChange={e => setText(e.target.value)} placeholder="Paste any LinkedIn, Slack, Telegram, or X hiring post here..." className="w-full bg-slate-900 border border-white/10 rounded-xl p-3.5 text-xs text-white focus:outline-none focus:border-brand-500 font-mono"></textarea>
                <button disabled={analyzing || !text} onClick={() => analyzeText()} className="w-full py-3 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-semibold text-xs shadow-lg shadow-brand-500/25 transition">
                  {analyzing ? 'Analyzing with Gemini NLP...' : 'Evaluate Post with Gemini'}
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="border-2 border-dashed border-brand-500/40 rounded-xl p-8 text-center bg-slate-900/40 space-y-2">
                  <span className="text-3xl block">🖼️</span>
                  <p className="text-xs text-slate-300">Drag &amp; drop recruiter flyer or screenshot image here</p>
                  <input type="file" accept="image/*" onChange={handleImageUpload} className="text-xs text-slate-500" />
                </div>
                {analyzing && <div className="text-xs text-brand-300 font-mono text-center">Performing Gemini Vision OCR...</div>}
              </div>
            )}
          </div>

          {/* Results Analysis & ⚡ Apply Now Actions */}
          <div className="space-y-6">
            {/* Eligibility & ⚡ Apply Now Card */}
            <div className="glass-card p-6 rounded-2xl space-y-4 border border-brand-500/20">
              <h4 className="font-bold text-sm text-white flex items-center gap-2">
                <span>📊</span> Eligibility &amp; Match Analysis
              </h4>
              {result ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between bg-slate-900/80 p-4 rounded-xl border border-white/5">
                    <div>
                      <div className="font-bold text-base text-white">{result.role_title}</div>
                      <div className="text-xs text-slate-400">{result.company} · {result.location}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xl font-bold text-brand-400">{result.eligibility_score}%</div>
                      <span className="text-[10px] text-emerald-400 font-semibold">{result.verdict}</span>
                    </div>
                  </div>

                  <div className="space-y-2 text-xs">
                    <div className="text-slate-300"><span className="text-slate-500 font-medium">Summary:</span> {result.summary}</div>
                    <div className="text-slate-300"><span className="text-slate-500 font-medium">Experience Req:</span> {result.experience_required}</div>
                    <div className="text-slate-300"><span className="text-slate-500 font-medium">Skills:</span> {result.skills_required?.join(', ')}</div>
                    
                    {detectedUrl && (
                      <div className="p-3 rounded-xl bg-brand-950/40 border border-brand-500/30 text-xs space-y-1">
                        <div className="font-semibold text-brand-300 flex items-center gap-1.5">
                          <span>🔗</span> Direct Apply Link Detected:
                        </div>
                        <div className="font-mono text-[11px] text-slate-300 break-all">{detectedUrl}</div>
                      </div>
                    )}

                    {result.contact_email ? (
                      <div className="text-emerald-400 font-mono font-medium">Recruiter Email: {result.contact_email}</div>
                    ) : (
                      <div className="text-amber-400 text-[11px] font-mono">No direct email detected. You can enter it in the composer below.</div>
                    )}
                  </div>

                  {/* ⚡ Prominent Action Buttons: Apply Now & Open in Chrome Profile */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                    <button
                      onClick={handleApplyNow}
                      disabled={applyingDirect || !detectedUrl}
                      className="py-3 px-4 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-emerald-950/40 transition">
                      <span>⚡</span>
                      <span>{applyingDirect ? 'Launching Universal ATS...' : 'Apply Now via Universal ATS'}</span>
                    </button>

                    <button
                      onClick={handleOpenInChrome}
                      disabled={!detectedUrl}
                      className="py-3 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 font-semibold text-xs flex items-center justify-center gap-2 border border-white/10 transition">
                      <span>↗</span>
                      <span>Open in Chrome Profile</span>
                    </button>
                  </div>

                  {/* Direct Apply Execution Stepper / Receipt */}
                  {directApplyReceipt && (
                    <div className="p-4 rounded-xl bg-slate-950 border border-brand-500/40 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-white flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                          Application Execution Status
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-500/20 text-emerald-300">
                          {directApplyReceipt.status}
                        </span>
                      </div>
                      <p className="text-slate-300 font-mono text-[11px]">{directApplyReceipt.message}</p>
                    </div>
                  )}

                  <button
                    onClick={handleSaveDraftToGmail}
                    disabled={savingDraft}
                    className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow transition">
                    <span>💾</span>
                    <span>{savingDraft ? 'Saving Draft directly to Gmail [Gmail]/Drafts...' : 'Prepare & Save Application Email Draft to Gmail'}</span>
                  </button>
                </div>
              ) : (
                <div className="text-slate-600 text-xs italic p-12 text-center">
                  Paste a post on the left (or click 'Load Cielsa Sample Post') to evaluate eligibility and trigger 1-click application.
                </div>
              )}
            </div>

            {/* Email Draft Composer Card */}
            {result && (
              <div className="glass-card p-6 rounded-2xl space-y-4 border border-emerald-500/20">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-sm text-white flex items-center gap-2">
                    <span>✉️</span> Recruiter Email Draft &amp; Gmail Sync
                  </h4>
                  <span className="text-[11px] text-slate-400 font-mono">From: abhishek.anand.7601@gmail.com</span>
                </div>

                {draftResult && (
                  <div className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 text-xs flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">✅</span>
                      <div>
                        <div className="font-semibold text-white">Draft Saved Directly to Gmail!</div>
                        <div className="text-[11px] text-emerald-300">Saved in [Gmail]/Drafts with Abhishek_Anand_Resume.pdf attached.</div>
                      </div>
                    </div>
                    <a
                      href="https://mail.google.com/mail/#drafts"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-[11px] transition inline-flex items-center gap-1">
                      Open Drafts ↗
                    </a>
                  </div>
                )}

                {sendResult && (
                  <div className="p-3 rounded-xl bg-blue-950/60 border border-blue-500/40 text-blue-300 text-xs flex items-center gap-2">
                    <span>🚀</span>
                    <span>{sendResult.message}</span>
                  </div>
                )}

                <div className="space-y-3 text-xs">
                  <div>
                    <label className="block text-slate-400 font-medium mb-1">To (Recruiter / Hiring Email):</label>
                    <input
                      type="email"
                      value={emailTo}
                      onChange={e => setEmailTo(e.target.value)}
                      placeholder="e.g. careers@company.com or recruiter@company.com"
                      className="w-full bg-slate-900 border border-white/10 rounded-xl p-2.5 text-white focus:outline-none focus:border-brand-500 font-mono text-xs"
                    />
                  </div>

                  <div>
                    <label className="block text-slate-400 font-medium mb-1">Subject:</label>
                    <input
                      type="text"
                      value={emailSubject}
                      onChange={e => setEmailSubject(e.target.value)}
                      className="w-full bg-slate-900 border border-white/10 rounded-xl p-2.5 text-white focus:outline-none focus:border-brand-500 text-xs font-semibold"
                    />
                  </div>

                  <div className="flex items-center gap-2 p-2 rounded-xl bg-slate-900/80 border border-white/5 text-[11px] text-emerald-400 font-mono">
                    <span>📎</span>
                    <span>Attached: Abhishek_Anand_Resume.pdf (ATS Validated, 3.5+ Yrs Frontend)</span>
                  </div>

                  <div>
                    <label className="block text-slate-400 font-medium mb-1">Email Body (Tailored Cover Letter):</label>
                    <textarea
                      rows={7}
                      value={emailBody}
                      onChange={e => setEmailBody(e.target.value)}
                      className="w-full bg-slate-900 border border-white/10 rounded-xl p-3 text-white focus:outline-none focus:border-brand-500 text-xs font-mono leading-relaxed custom-scrollbar"
                    ></textarea>
                  </div>
                </div>

                <div className="flex items-center gap-3 pt-1">
                  <button
                    onClick={handleSaveDraftToGmail}
                    disabled={savingDraft || !emailTo}
                    className="flex-1 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs flex items-center justify-center gap-2 transition">
                    <span>💾</span>
                    <span>{savingDraft ? 'Saving to Gmail...' : 'Save to Gmail Drafts'}</span>
                  </button>

                  <a
                    href="https://mail.google.com/mail/#drafts"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition inline-flex items-center gap-1.5 border border-white/10">
                    <span>↗</span>
                    <span>Open Gmail</span>
                  </a>

                  <button
                    onClick={handleSendEmailNow}
                    disabled={sendingEmail || !emailTo}
                    className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs flex items-center gap-1.5 transition">
                    <span>🚀</span>
                    <span>{sendingEmail ? 'Sending...' : 'Send Now'}</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      );
    }


export default AiScannerView;
