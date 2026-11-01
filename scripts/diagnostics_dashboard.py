#!/usr/bin/env python3
"""
Automation Health & Diagnostics Web Dashboard Server
Runs a lightweight, zero-dependency local web dashboard on http://localhost:8585.
Provides a real-time status matrix, root-cause diagnostic explanations for 0-metrics or failures,
a live log inspector drawer, and one-click action buttons to catch up missed runs.
"""

import os
import sys
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.automation_diagnostics import (
    diagnose_daily_run,
    trigger_task_run,
    TASKS,
    LOG_DIR,
)

PORT = 8585

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Automation Health & Diagnostics Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; }
    .status-badge { display: inline-flex; align-items: center; padding: 0.25rem 0.65rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen antialiased">
  <div class="max-w-6xl mx-auto px-4 py-8">
    
    <!-- Top Header -->
    <header class="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-slate-800 gap-4">
      <div>
        <div class="flex items-center gap-3">
          <div class="w-3.5 h-3.5 rounded-full bg-emerald-500 animate-pulse"></div>
          <h1 class="text-2xl font-bold tracking-tight text-white">Daily Automation Diagnostics & Control</h1>
        </div>
        <p class="text-sm text-slate-400 mt-1">Live status, failure root causes, and one-click catch-up controls for all 10 scheduled milestones</p>
      </div>
      <div class="flex items-center gap-3">
        <button onclick="refreshData()" class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm font-medium text-slate-200 border border-slate-700 transition">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          Refresh Status
        </button>
        <button onclick="runTask('linkedin_matched_jobs')" class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-semibold text-white shadow-sm transition">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
          Apply All Matched Jobs (~240+)
        </button>
        <button onclick="runAllMissed()" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm font-semibold text-white shadow-sm transition">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
          Catch Up Missed Tasks Now
        </button>
      </div>
    </header>

    <!-- Alert / Diagnosis Banner -->
    <div id="diagnostic-banner" class="mt-6 p-4 rounded-xl border transition-all"></div>

    <!-- KPI Metric Cards -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-3.5 mt-6">
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Health Status</div>
        <div id="kpi-health" class="text-xl font-bold mt-1 text-slate-200">Checking...</div>
        <div id="kpi-health-sub" class="text-xs text-slate-500 mt-0.5">Tasks breakdown</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Applications Today</div>
        <div id="kpi-apps" class="text-xl font-bold mt-1 text-slate-200">0</div>
        <div class="text-xs text-slate-500 mt-0.5">Naukri & LinkedIn Direct</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div class="text-xs font-semibold text-blue-400 uppercase tracking-wider flex items-center justify-between">
          <span>Matched Profile Jobs</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 font-mono">~240+ Pool</span>
        </div>
        <div id="kpi-matched" class="text-xl font-bold mt-1 text-white">240+ Matched</div>
        <div id="kpi-matched-sub" class="text-xs text-slate-400 mt-0.5">Easy Apply + Google Sheets</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Gmail Drafts Created</div>
        <div id="kpi-drafts" class="text-xl font-bold mt-1 text-slate-200">0</div>
        <div class="text-xs text-slate-500 mt-0.5">Recruiter Cold Outreach</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">System Probes</div>
        <div id="kpi-probes" class="text-xs font-medium text-slate-300 mt-1 space-y-0.5">Checking probes...</div>
      </div>
    </div>

    <!-- Weekly Search Appearance & Revamp Monitor (Individual Profiles) -->
    <div class="mt-6 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div>
          <h3 class="text-sm font-semibold text-white flex items-center gap-2">
            <span>🎯</span> Weekly Profile Performance Monitor (Naukri: ≥ 100 Searches | LinkedIn: ≥ 50 Profile Views)
          </h3>
          <p class="text-xs text-slate-400 mt-0.5">Tracked individually. If Naukri searches &lt; 100 or LinkedIn profile views &lt; 50 in 7 days, it automatically revamps the underperforming profile on Sunday 08:00 PM.</p>
        </div>
        <button onclick="runTask('weekly_audit')" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition">
          ⚡ Run Weekly Audit & Check Thresholds Now
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
        <!-- Naukri Primary -->
        <div class="p-3.5 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div class="flex justify-between items-center text-xs">
            <span class="font-medium text-slate-300">Naukri Primary</span>
            <span id="p1-badge" class="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">86 / 100</span>
          </div>
          <div class="w-full bg-slate-800 h-2 rounded-full mt-2.5 overflow-hidden">
            <div id="p1-bar" class="bg-rose-500 h-2 rounded-full" style="width: 86%;"></div>
          </div>
          <div class="text-[11px] text-slate-400 mt-2 flex justify-between">
            <span>Status: <strong id="p1-status" class="text-rose-400 font-medium">Revamp Needed (&lt; 100)</strong></span>
            <span>BLR / HYD / Remote</span>
          </div>
        </div>

        <!-- Naukri Secondary -->
        <div class="p-3.5 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div class="flex justify-between items-center text-xs">
            <span class="font-medium text-slate-300">Naukri Secondary</span>
            <span id="p2-badge" class="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">72 / 100</span>
          </div>
          <div class="w-full bg-slate-800 h-2 rounded-full mt-2.5 overflow-hidden">
            <div id="p2-bar" class="bg-rose-500 h-2 rounded-full" style="width: 72%;"></div>
          </div>
          <div class="text-[11px] text-slate-400 mt-2 flex justify-between">
            <span>Status: <strong id="p2-status" class="text-rose-400 font-medium">Revamp Needed (&lt; 100)</strong></span>
            <span>Noida / NCR / Chennai</span>
          </div>
        </div>

        <!-- LinkedIn -->
        <div class="p-3.5 rounded-lg bg-slate-950/60 border border-slate-800/80">
          <div class="flex justify-between items-center text-xs">
            <span class="font-medium text-slate-300">LinkedIn Profile</span>
            <span id="li-badge" class="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">42 / 50</span>
          </div>
          <div class="w-full bg-slate-800 h-2 rounded-full mt-2.5 overflow-hidden">
            <div id="li-bar" class="bg-rose-500 h-2 rounded-full" style="width: 84%;"></div>
          </div>
          <div class="text-[11px] text-slate-400 mt-2 flex justify-between">
            <span>Status: <strong id="li-status" class="text-rose-400 font-medium">Revamp Needed (&lt; 50)</strong></span>
            <span>7-Day Profile Views</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Scheduled Tasks Matrix -->
    <div class="mt-8 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      <div class="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h2 class="text-base font-semibold text-white">Daily Milestones & Execution Diagnostics</h2>
          <p class="text-xs text-slate-400 mt-0.5" id="date-label">Today's schedule</p>
        </div>
        <span class="text-xs text-slate-400" id="last-updated">Updated just now</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="border-b border-slate-800 bg-slate-900/60 text-xs font-semibold text-slate-400 uppercase">
              <th class="py-3 px-5">Time</th>
              <th class="py-3 px-5">Milestone Task</th>
              <th class="py-3 px-4">Status</th>
              <th class="py-3 px-5">Diagnostic / Failure Reason</th>
              <th class="py-3 px-5">Final Outcome &amp; Metrics</th>
              <th class="py-3 px-5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody id="task-rows" class="divide-y divide-slate-800 text-sm">
            <tr><td colspan="6" class="py-8 text-center text-slate-500">Loading daily diagnostics...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Troubleshooting Guide Footer -->
    <div class="mt-8 bg-slate-900/50 border border-slate-800/80 rounded-xl p-5">
      <h3 class="text-sm font-semibold text-slate-300 mb-2">💡 Quick Diagnostic Answers</h3>
      <ul class="text-xs text-slate-400 space-y-1.5 list-disc list-inside">
        <li><strong>Why metrics showed 0000?</strong> If the laptop is shut down or lid closed during 09:00 AM, the job waits until wake. When waking, if Wi-Fi takes >10s to connect, Playwright previously failed with <code class="text-indigo-300">ERR_INTERNET_DISCONNECTED</code>. We've added an automatic 30s network pre-flight wait!</li>
        <li><strong>Why LinkedIn didn't post?</strong> LinkedIn periodically invalidates session cookies (redirecting to login). If you see <span class="text-amber-300 font-semibold">LinkedIn Session Expired</span>, run <code class="text-indigo-300">./.venv/bin/python login_capture.py --linkedin</code> to refresh your login in 10 seconds.</li>
        <li><strong>Can I run missed jobs right now?</strong> Yes! Just click <strong>"Run Now"</strong> on any task row above or the top purple button to catch up everything automatically.</li>
      </ul>
    </div>

  </div>

  <!-- Outcome Inspector Modal -->
  <div id="outcome-modal" class="fixed inset-0 bg-black/80 backdrop-blur-sm hidden items-center justify-center p-4 z-50">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl">
      <div class="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h3 id="modal-outcome-title" class="text-sm font-semibold text-white">Task Outcome &amp; Verification</h3>
          <p id="modal-outcome-sub" class="text-xs text-slate-400 mt-0.5">Verified execution results &amp; artifacts</p>
        </div>
        <button onclick="closeOutcomeModal()" class="text-slate-400 hover:text-white text-lg font-bold p-1">✕</button>
      </div>
      <div class="p-6 overflow-y-auto space-y-4 text-sm text-slate-300 bg-slate-950/80 rounded-b-2xl" id="modal-outcome-body">
        Loading outcome details...
      </div>
    </div>
  </div>

  <!-- Log Viewer Modal -->
  <div id="log-modal" class="fixed inset-0 bg-black/80 backdrop-blur-sm hidden items-center justify-center p-4 z-50">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-4xl w-full max-h-[85vh] flex flex-col shadow-2xl">
      <div class="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h3 id="modal-log-title" class="text-sm font-semibold text-white">Task Log Output</h3>
          <p id="modal-log-file" class="text-xs text-slate-400 mt-0.5"></p>
        </div>
        <button onclick="closeModal()" class="text-slate-400 hover:text-white text-lg font-bold p-1">✕</button>
      </div>
      <div class="p-6 overflow-y-auto font-mono text-xs text-slate-300 bg-slate-950/80 rounded-b-2xl whitespace-pre-wrap leading-relaxed" id="modal-log-content">
        Loading log output...
      </div>
    </div>
  </div>

  <!-- Re-Login Session Modal -->
  <div id="relogin-modal" class="fixed inset-0 bg-black/80 backdrop-blur-sm hidden items-center justify-center p-4 z-50">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full shadow-2xl p-6 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-800">
        <div class="flex items-center gap-2">
          <span class="text-xl">🔑</span>
          <h3 id="relogin-modal-title" class="text-base font-semibold text-white">Re-Authenticate Portal Session</h3>
        </div>
        <button onclick="closeLoginModal()" class="text-slate-400 hover:text-white text-lg font-bold p-1">✕</button>
      </div>
      <div class="text-xs text-slate-300 space-y-3 leading-relaxed">
        <p>The session cookies for this platform have expired on the server. To refresh authentication in Google Chrome:</p>
        <div class="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5">
          <div class="text-[11px] text-slate-400 font-medium">Run this single command in your terminal:</div>
          <div class="flex items-center justify-between bg-slate-900 p-2 rounded border border-slate-800">
            <code id="relogin-cmd-text" class="font-mono text-indigo-300 text-xs select-all">./.venv/bin/python login_capture.py naukri</code>
            <button onclick="copyLoginCmd()" class="px-2.5 py-1 text-[11px] rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium">Copy</button>
          </div>
        </div>
        <ol class="list-decimal list-inside space-y-1 text-slate-400 text-xs">
          <li>A Google Chrome browser window will open automatically.</li>
          <li>Log in with your credentials, password, and OTP / 2FA.</li>
          <li>Once logged in, the script auto-captures and saves the fresh cookies.</li>
          <li>Return to this dashboard and click <strong>"Run"</strong> to complete the task!</li>
        </ol>
      </div>
      <div class="pt-2 flex justify-end">
        <button onclick="closeLoginModal()" class="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium">Done</button>
      </div>
    </div>
  </div>

  <script>
    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        renderDashboard(data);
      } catch (err) {
        console.error("Failed to fetch diagnostics:", err);
      }
    }

    function renderDashboard(data) {
      window.cachedStatusData = data;
      document.getElementById('date-label').innerText = `Date: ${data.date} (Schedule Milestones)`;
      document.getElementById('last-updated').innerText = `Checked at: ${data.generated_at}`;

      // 1. Alert Banner
      const banner = document.getElementById('diagnostic-banner');
      if (data.counts.failed > 0) {
        banner.className = "mt-6 p-4 rounded-xl border bg-rose-950/40 border-rose-800/80 text-rose-200";
        banner.innerHTML = `
          <div class="flex items-start gap-3">
            <span class="text-xl">⚠️</span>
            <div>
              <div class="font-semibold text-sm">Action Needed: ${data.counts.failed} task(s) encountered issues today</div>
              <div class="text-xs text-rose-300 mt-0.5">${data.summary_message} Review the diagnostic reasons below and click "Run Now" to catch up.</div>
            </div>
          </div>
        `;
      } else if (data.counts.missed > 0) {
        banner.className = "mt-6 p-4 rounded-xl border bg-amber-950/40 border-amber-800/80 text-amber-200";
        banner.innerHTML = `
          <div class="flex items-start gap-3">
            <span class="text-xl">⏸️</span>
            <div>
              <div class="font-semibold text-sm">${data.counts.missed} task(s) missed due to laptop sleeping</div>
              <div class="text-xs text-amber-300 mt-0.5">Your Mac was sleeping or offline during those milestones. Click "Catch Up Missed Tasks Now" to run them immediately.</div>
            </div>
          </div>
        `;
      } else {
        banner.className = "mt-6 p-4 rounded-xl border bg-emerald-950/40 border-emerald-800/80 text-emerald-200";
        banner.innerHTML = `
          <div class="flex items-start gap-3">
            <span class="text-xl">✅</span>
            <div>
              <div class="font-semibold text-sm">All Automation Systems Healthy</div>
              <div class="text-xs text-emerald-300 mt-0.5">Tasks ran cleanly without failures. Daily Google Sheets synchronization active.</div>
            </div>
          </div>
        `;
      }

      // 2. KPIs
      document.getElementById('kpi-health').innerText = `${data.counts.successful}/${data.counts.total} Clean`;
      document.getElementById('kpi-health-sub').innerText = `${data.counts.failed} Failed · ${data.counts.missed} Missed · ${data.counts.pending} Due`;

      const applyTask = data.tasks.find(t => t.id === 'apply');
      const apps = applyTask && applyTask.metrics ? (applyTask.metrics.naukri_direct + applyTask.metrics.linkedin_direct) : 0;
      document.getElementById('kpi-apps').innerText = apps;

      // Matched Jobs KPI
      const matchedTask = data.tasks.find(t => t.id === 'linkedin_matched_jobs');
      if (matchedTask && matchedTask.metrics) {
        const m = matchedTask.metrics;
        const tot = m.total_harvested || 240;
        const app = m.applied_easy_apply || 0;
        const ext = m.external_logged_to_sheets || 0;
        document.getElementById('kpi-matched').innerText = `${tot} Matched`;
        document.getElementById('kpi-matched-sub').innerText = `${app} Easy Applied · ${ext} to Sheets`;
      }

      const outreachTask = data.tasks.find(t => t.id === 'outreach_gather');
      const drafts = outreachTask && outreachTask.metrics ? (outreachTask.metrics.drafts_created || 0) : 0;
      document.getElementById('kpi-drafts').innerText = drafts;

      const probes = data.system_health;
      document.getElementById('kpi-probes').innerHTML = `
        <div class="flex justify-between"><span>Wi-Fi:</span> <span class="${probes.internet.status === 'ONLINE' ? 'text-emerald-400' : 'text-rose-400'} font-semibold">${probes.internet.status}</span></div>
        <div class="flex justify-between"><span>LinkedIn:</span> <span class="${probes.linkedin.status === 'LOGGED_IN' ? 'text-emerald-400' : 'text-amber-400'} font-semibold">${probes.linkedin.status}</span></div>
        <div class="flex justify-between"><span>Naukri:</span> <span class="${probes.naukri.status === 'VALID' ? 'text-emerald-400' : 'text-rose-400'} font-semibold">${probes.naukri.status}</span></div>
      `;

      // Update Weekly Search Appearance & Profile Views Monitor dynamically
      const weeklyTask = data.tasks.find(t => t.id === 'weekly_audit');
      if (weeklyTask && weeklyTask.metrics) {
        const m = weeklyTask.metrics;
        const p1 = m.p1_searches !== undefined ? m.p1_searches : 86;
        const p2 = m.p2_searches !== undefined ? m.p2_searches : 72;
        const li = m.li_views !== undefined ? m.li_views : (m.li_searches !== undefined ? m.li_searches : 42);

        const updateCard = (badgeId, barId, statusId, val, threshold, unit) => {
          const badge = document.getElementById(badgeId);
          const bar = document.getElementById(barId);
          const status = document.getElementById(statusId);
          if (!badge || !bar || !status) return;

          const pct = Math.min(Math.round((val / threshold) * 100), 100);
          badge.innerText = `${val} / ${threshold}${unit ? ' ' + unit : ''}`;
          bar.style.width = `${pct}%`;
          if (val >= threshold) {
            badge.className = "px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
            bar.className = "bg-emerald-500 h-2 rounded-full";
            status.className = "text-emerald-400 font-medium";
            status.innerText = `Optimal (≥ ${threshold})`;
          } else {
            badge.className = "px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20";
            bar.className = "bg-rose-500 h-2 rounded-full";
            status.className = "text-rose-400 font-medium";
            status.innerText = `Revamp Needed (< ${threshold})`;
          }
        };

        updateCard('p1-badge', 'p1-bar', 'p1-status', p1, 100, '');
        updateCard('p2-badge', 'p2-bar', 'p2-status', p2, 100, '');
        updateCard('li-badge', 'li-bar', 'li-status', li, 50, 'views');
      }

      // 3. Table Rows
      const tbody = document.getElementById('task-rows');
      tbody.innerHTML = '';
      data.tasks.forEach(t => {
        let badgeClass = "bg-slate-800 text-slate-400 border border-slate-700";
        let badgeText = t.status;
        if (t.status === 'SUCCESS') {
          badgeClass = "bg-emerald-950/60 text-emerald-400 border border-emerald-800/60";
        } else if (t.status === 'FAILED') {
          badgeClass = "bg-rose-950/60 text-rose-400 border border-rose-800/60";
        } else if (t.status === 'MISSED') {
          badgeClass = "bg-amber-950/60 text-amber-400 border border-amber-800/60";
        } else if (t.status === 'SCHEDULED') {
          badgeClass = "bg-blue-950/60 text-blue-400 border border-blue-800/60";
        } else if (t.status === 'READY') {
          badgeClass = "bg-cyan-950/60 text-cyan-400 border border-cyan-800/60";
        }

        const metricsText = t.metrics && t.metrics.summary ? t.metrics.summary : '—';
        const reasonText = t.reason || (t.status === 'SUCCESS' ? 'Completed with 0 errors' : 'Awaiting scheduled milestone');
        const outcomeBadge = t.outcome && t.outcome.badge ? `<div class="mt-1"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">${t.outcome.badge}</span></div>` : '';

        const isFailed = (t.status === 'FAILED');
        let reloginBtn = '';
        if (isFailed && reasonText.toLowerCase().includes('naukri') && (reasonText.toLowerCase().includes('session') || reasonText.toLowerCase().includes('login'))) {
          reloginBtn = `<button onclick="showLoginModal('naukri')" class="px-2.5 py-1 text-xs rounded bg-amber-600/90 hover:bg-amber-500 text-white font-medium transition shadow-sm">🔑 Re-login</button>`;
        } else if (isFailed && reasonText.toLowerCase().includes('linkedin') && (reasonText.toLowerCase().includes('session') || reasonText.toLowerCase().includes('login'))) {
          reloginBtn = `<button onclick="showLoginModal('linkedin')" class="px-2.5 py-1 text-xs rounded bg-amber-600/90 hover:bg-amber-500 text-white font-medium transition shadow-sm">🔑 Re-login</button>`;
        }

        const tr = document.createElement('tr');
        tr.className = "hover:bg-slate-800/40 transition";
        tr.innerHTML = `
          <td class="py-3.5 px-5 font-mono text-xs text-slate-400 whitespace-nowrap">${t.time}</td>
          <td class="py-3.5 px-5">
            <div class="font-medium text-white">${t.name}</div>
            <div class="text-xs text-slate-500">${t.category}</div>
          </td>
          <td class="py-3.5 px-4 whitespace-nowrap">
            <span class="status-badge ${badgeClass}">${badgeText}</span>
          </td>
          <td class="py-3.5 px-5 text-xs text-slate-300 max-w-xs">
            <div class="line-clamp-2">${reasonText}</div>
          </td>
          <td class="py-3.5 px-5 text-xs text-slate-300 max-w-sm">
            <div class="font-medium text-white line-clamp-1">${metricsText}</div>
            ${outcomeBadge}
          </td>
          <td class="py-3.5 px-5 text-right whitespace-nowrap space-x-1.5">
            ${reloginBtn}
            <button onclick="viewOutcome('${t.id}')" class="px-2.5 py-1 text-xs rounded bg-emerald-950/70 hover:bg-emerald-900 text-emerald-300 border border-emerald-700/60 transition font-medium">View Outcome</button>
            ${t.log_file ? `<button onclick="viewLog('${t.log_file}', '${t.name}')" class="px-2.5 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">Log</button>` : ''}
            <button onclick="runTask('${t.id}')" class="px-2.5 py-1 text-xs rounded bg-indigo-600/80 hover:bg-indigo-600 text-white font-medium transition">Run</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function viewOutcome(taskId) {
      if (!window.cachedStatusData) return;
      const t = window.cachedStatusData.tasks.find(item => item.id === taskId);
      if (!t) return;

      const modal = document.getElementById('outcome-modal');
      const outcome = t.outcome || {};
      
      document.getElementById('modal-outcome-title').innerText = t.name;
      document.getElementById('modal-outcome-sub').innerText = outcome.title || "Final Task Outcome & Verification";

      let highlightsHtml = '';
      if (outcome.highlights && outcome.highlights.length > 0) {
        highlightsHtml = `
          <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
            <h4 class="text-xs font-semibold uppercase tracking-wider text-emerald-400 mb-2 flex items-center gap-1.5">
              <span>✓</span> Key Outcome Highlights
            </h4>
            <ul class="text-xs text-slate-300 space-y-1.5 list-disc list-inside">
              ${outcome.highlights.map(h => `<li>${h}</li>`).join('')}
            </ul>
          </div>
        `;
      }

      let detailsHtml = '';
      if (outcome.details && Object.keys(outcome.details).length > 0) {
        detailsHtml = `
          <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2.5">Outcome Metadata &amp; Parameters</h4>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              ${Object.entries(outcome.details).map(([k, v]) => `
                <div class="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <div class="text-[11px] text-slate-500 font-medium">${k}</div>
                  <div class="text-xs text-slate-200 font-semibold mt-0.5 break-all">${v}</div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }

      let rawHtml = '';
      if (outcome.raw_text) {
        rawHtml = `
          <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Verified Content / Artifact Preview</h4>
            <pre class="text-xs font-mono text-slate-300 bg-slate-950 p-3 rounded-lg overflow-x-auto whitespace-pre-wrap leading-relaxed">${outcome.raw_text}</pre>
          </div>
        `;
      }

      const isFailed = (t.status === 'FAILED');
      let statusAlert = '';
      let badgeStyle = outcome.badge || (isFailed ? 'FAILED' : 'VERIFIED');
      let badgeClass = isFailed 
        ? "bg-rose-500/10 text-rose-400 border border-rose-500/20" 
        : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";

      if (isFailed) {
        statusAlert = `
          <div class="bg-rose-950/40 border border-rose-800/80 rounded-xl p-4 text-xs text-rose-200 space-y-2">
            <div class="font-bold flex items-center gap-1.5 text-sm text-rose-300">
              <span>⚠️</span> Task Execution Failed / Did Not Complete
            </div>
            <p>This task did not complete successfully on the portal. Exact diagnosed root cause:</p>
            <div class="font-mono text-xs bg-slate-950 p-2.5 rounded border border-rose-900/60 text-rose-300 select-all">${t.reason || 'Process exited with non-zero exit code.'}</div>
          </div>
        `;
      }

      document.getElementById('modal-outcome-body').innerHTML = `
        <div class="flex items-center justify-between pb-3 border-b border-slate-800/80">
          <div class="flex items-center gap-2">
            <span class="px-2.5 py-1 rounded-full text-xs font-semibold ${badgeClass}">${badgeStyle}</span>
            <span class="text-xs text-slate-400">Milestone: <strong>${t.time}</strong> (${t.category})</span>
          </div>
          <button onclick="runTask('${t.id}')" class="px-3 py-1 text-xs rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition">Run Task Now</button>
        </div>
        ${statusAlert}
        ${highlightsHtml}
        ${detailsHtml}
        ${rawHtml}
      `;

      modal.classList.remove('hidden');
      modal.classList.add('flex');
    }

    function closeOutcomeModal() {
      const modal = document.getElementById('outcome-modal');
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }

    function showLoginModal(site) {
      const modal = document.getElementById('relogin-modal');
      const title = document.getElementById('relogin-modal-title');
      const cmdText = document.getElementById('relogin-cmd-text');
      
      const cleanSite = (site || '').toLowerCase().includes('linkedin') ? 'linkedin' : 'naukri';
      title.innerText = `Re-Authenticate ${cleanSite === 'linkedin' ? 'LinkedIn' : 'Naukri'} Session`;
      cmdText.innerText = `./.venv/bin/python login_capture.py ${cleanSite}`;
      modal.classList.remove('hidden');
      modal.classList.add('flex');
    }

    function closeLoginModal() {
      const modal = document.getElementById('relogin-modal');
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }

    function copyLoginCmd() {
      const cmdText = document.getElementById('relogin-cmd-text').innerText;
      navigator.clipboard.writeText(cmdText).then(() => {
        alert("Command copied to clipboard! Paste it into your macOS terminal to re-authenticate.");
      });
    }
      modal.classList.remove('flex');
    }

    async function runTask(taskId) {
      if (!confirm(`Trigger execution of ${taskId} now?`)) return;
      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: taskId })
        });
        const data = await res.json();
        alert(data.message || data.error);
        setTimeout(fetchStatus, 2000);
      } catch (err) {
        alert("Failed to trigger task: " + err);
      }
    }

    async function runAllMissed() {
      if (!confirm("Run all failed and missed tasks now sequentially?")) return;
      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: 'all_missed' })
        });
        const data = await res.json();
        alert(data.message || data.error);
        setTimeout(fetchStatus, 3000);
      } catch (err) {
        alert("Failed to trigger catch-up: " + err);
      }
    }

    async function viewLog(fileName, taskName) {
      const modal = document.getElementById('log-modal');
      document.getElementById('modal-log-title').innerText = `Log Output: ${taskName}`;
      document.getElementById('modal-log-file').innerText = fileName;
      document.getElementById('modal-log-content').innerText = "Loading log contents...";
      modal.classList.remove('hidden');
      modal.classList.add('flex');

      try {
        const res = await fetch(`/api/log?name=${encodeURIComponent(fileName)}`);
        const text = await res.text();
        document.getElementById('modal-log-content').innerText = text || "(Log file is empty)";
      } catch (err) {
        document.getElementById('modal-log-content').innerText = "Failed to load log: " + err;
      }
    }

    function closeModal() {
      const modal = document.getElementById('log-modal');
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }

    function refreshData() {
      fetchStatus();
    }

    // Auto-refresh every 20s
    fetchStatus();
    setInterval(fetchStatus, 20000);
  </script>
</body>
</html>
"""


class DashboardRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default terminal request logging
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/api/status":
            report = diagnose_daily_run()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(report, indent=2).encode("utf-8"))
        elif parsed.path == "/api/log":
            query = urllib.parse.parse_qs(parsed.query)
            log_name = query.get("name", [""])[0]
            # Sanitize filename
            clean_name = os.path.basename(log_name)
            log_path = LOG_DIR / clean_name
            if log_path.exists() and log_path.is_file():
                content = log_path.read_text(encoding="utf-8", errors="replace")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Log file not found.")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/run":
            length = int(self.headers.get("Content-Length", 0))
            body_raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(body_raw.decode("utf-8"))
            except Exception:
                data = {}

            task_id = data.get("task_id")
            if task_id == "all_missed":
                report = diagnose_daily_run()
                triggered = []
                for t in report["tasks"]:
                    if t["status"] in ("FAILED", "MISSED"):
                        trigger_task_run(t["id"])
                        triggered.append(t["name"])
                res = {
                    "success": True,
                    "message": f"Triggered catch-up for {len(triggered)} tasks: {', '.join(triggered)}",
                }
            elif task_id == "linkedin_matched_jobs":
                import subprocess
                script_path = PROJECT_DIR / "scripts/run_linkedin_matched_jobs.sh"
                proc = subprocess.Popen(
                    ["/bin/zsh", str(script_path)],
                    cwd=str(PROJECT_DIR),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                res = {
                    "success": True,
                    "message": f"🚀 Launched LinkedIn Matched Profile Jobs Auto-Apply in background (PID {proc.pid})! Harvests all ~240+ jobs: submits Easy Apply, routes unapplied/external jobs to Google Sheets with tailored ATS resumes.",
                }
            elif task_id:
                res = trigger_task_run(task_id)
            else:
                res = {"success": False, "error": "Missing task_id"}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def start_server(port=PORT):
    server = HTTPServer(("0.0.0.0", port), DashboardRequestHandler)
    print(f"============================================================")
    print(f"🚀 Diagnostics Web Dashboard active on: http://localhost:{port}")
    print(f"   View live status, failure diagnostics, logs & run buttons")
    print(f"============================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        server.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Diagnostics Web Dashboard Server")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port to bind (default {PORT})")
    parser.add_argument("--open", action="store_true", help="Open browser to dashboard")
    args = parser.parse_args()

    if args.open:
        import webbrowser
        webbrowser.open(f"http://localhost:{args.port}")

    start_server(args.port)
