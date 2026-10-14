"""
Automated Daily LinkedIn Technical Thought-Leadership Generator and Publisher.

Generates deep-dive, layman-friendly frontend engineering posts designed to:
1. Maximize recruiter visibility & ranking via LinkedIn Creator activity signals.
2. Demonstrate technical depth (React internals, JS engine mechanics, web performance).
3. Position the author as a top-tier Frontend Engineer.

Usage:
    python linkedin_daily_post.py                 # Generates today's post and previews before publishing
    python linkedin_daily_post.py --dry-run       # Generates post and prints without opening browser
    python linkedin_daily_post.py --topic "React Fiber" # Explicit topic
    python linkedin_daily_post.py --unattended    # Publishes automatically (for cron / morning runner)
    python linkedin_daily_post.py --list-topics   # Lists all 60+ curated domain topics
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import random
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Import LLM clients
from common import gemini
from common import groq_llm

HISTORY_FILE = "linkedin_posts_history.json"
SESSION_FILE = "session_linkedin.json"
FEED_URL = "https://www.linkedin.com/feed/"

# 60+ Curated Deep-Dive Frontend & React Domain Topics
FRONTEND_TOPICS = [
    # Category 1: JavaScript Engine Internals & Execution
    {
        "id": "js_execution_context",
        "category": "JavaScript Internals",
        "title": "JavaScript Execution Context & Lexical Environments",
        "prompt": "Deep dive into what really happens when JavaScript executes code: Global Execution Context vs Function Execution Context, the Creation Phase (Variable Object, Scope Chain, this binding) vs Execution Phase, and why hoisting is just a byproduct of the creation phase. Explain it simply with a mental model of memory slots."
    },
    {
        "id": "js_event_loop_microtasks",
        "category": "JavaScript Internals",
        "title": "The Event Loop: Microtasks (Promises) vs Macrotasks (setTimeout)",
        "prompt": "Deep dive into why Promise.then() runs before setTimeout(..., 0). Explain the microtask queue starvation risk, how requestAnimationFrame fits in between rendering ticks, and a classic interview trick question output breakdown."
    },
    {
        "id": "js_closures_memory_leaks",
        "category": "JavaScript Internals",
        "title": "Closures, Lexical Scope & How Memory Leaks Happen",
        "prompt": "Explain closures not just as 'a function inside a function', but through the lens of memory retention in the heap. Show how accidental closures in event listeners or long-lived caches retain entire parent lexical environments and leak memory."
    },
    {
        "id": "js_v8_hidden_classes",
        "category": "JavaScript Internals",
        "title": "How the V8 Engine Optimizes Objects: Hidden Classes & Inline Caching",
        "prompt": "Explain why adding properties to objects in different orders degrades V8 optimization (monomorphic vs polymorphic inline cache). Give a practical code example of fast vs de-optimized object shapes in high-frequency functions."
    },
    {
        "id": "js_weakmap_garbage_collection",
        "category": "JavaScript Internals",
        "title": "WeakMap and WeakSet: Why Weak References Prevent Memory Leaks",
        "prompt": "Explain the exact difference between Map and WeakMap. Why can't WeakMap keys be primitives? How does the Mark-and-Sweep garbage collector treat weak references, and how do modern libraries use WeakMap to attach metadata to DOM nodes without leaking?"
    },
    {
        "id": "js_prototype_chain",
        "category": "JavaScript Internals",
        "title": "Prototypal Inheritance vs ES6 Classes Under the Hood",
        "prompt": "Demystify __proto__ vs prototype. Explain why ES6 class syntax is largely syntactic sugar over prototype delegation, and how property lookup walks the prototype chain until Object.prototype.__proto__ === null."
    },
    {
        "id": "js_debounce_throttle_raf",
        "category": "JavaScript Internals",
        "title": "Debounce vs Throttle vs requestAnimationFrame",
        "prompt": "Compare debounce and throttle with real-world frontend scenarios (search autocomplete vs scroll tracking vs window resize). Explain why requestAnimationFrame throttling is superior for 60fps animations."
    },

    # Category 2: React Core & Internals
    {
        "id": "react_fiber_architecture",
        "category": "React Internals",
        "title": "React Fiber Architecture: Why React Stopped Using the Call Stack",
        "prompt": "Explain why React rewrote its reconciler into Fiber. Contrast the old recursive Stack Reconciler (uninterruptible blocking) with Fiber's linked-list work loop (cooperative multitasking, requestIdleCallback concept, render phase vs commit phase)."
    },
    {
        "id": "react_diffing_heuristics",
        "category": "React Internals",
        "title": "React Reconciliation & The Diffing Algorithm (O(n) Heuristics)",
        "prompt": "Explain why tree diffing is normally O(n^3) and how React achieves O(n) using two heuristics: different component types produce different trees, and key props identify elements across renders. Explain why array index as key breaks state."
    },
    {
        "id": "react_concurrent_mode_transitions",
        "category": "React Internals",
        "title": "Concurrent Rendering: useTransition and useDeferredValue Explained",
        "prompt": "Explain what 'concurrent' actually means in single-threaded JavaScript (time-slicing). Show how useTransition demotes urgent state updates to background priority so high-frequency keystrokes never freeze the UI."
    },
    {
        "id": "react_synthetic_events",
        "category": "React Internals",
        "title": "React Synthetic Event System vs Native DOM Events",
        "prompt": "Explain why React wraps browser events in SyntheticEvent (cross-browser normalization and pooled events history). Explain event delegation on the root container in React 17+ vs document in React 16."
    },
    {
        "id": "react_useeffect_vs_uselayouteffect",
        "category": "React Internals",
        "title": "useEffect vs useLayoutEffect: The Painting Boundary",
        "prompt": "Deep dive into the browser paint cycle: when does useEffect fire (asynchronous, post-paint) vs useLayoutEffect (synchronous, pre-paint). Explain why useLayoutEffect is necessary to avoid visual layout flashes during DOM measurements."
    },
    {
        "id": "react_stale_closures",
        "category": "React Internals",
        "title": "Stale Closures in React Hooks & How to Fix Them",
        "prompt": "Explain why functional components capture state at the time the function is created. Walk through a real-world setInterval or event listener bug where state never updates, and show the functional updater (prev => prev + 1) or useRef fix."
    },
    {
        "id": "react_custom_hooks_patterns",
        "category": "React Internals",
        "title": "Clean Custom Hook Design: Separation of Logic from UI",
        "prompt": "Discuss best practices for architecting production-grade custom hooks: returning tuple vs object, encapsulating cleanup logic, and avoiding unnecessary re-renders with stable callback references."
    },
    {
        "id": "react_19_actions_server_actions",
        "category": "React Internals",
        "title": "React 19 Actions & useActionState: The Future of Form Handling",
        "prompt": "Break down what React 19 brings with Actions, useActionState, useOptimistic, and Server Actions. Explain how it eliminates manual isPending/isLoading states and error handling boilerplate."
    },

    # Category 3: State Management & Data Fetching
    {
        "id": "tanstack_query_cache_lifecycle",
        "category": "State Management",
        "title": "TanStack Query: Fresh vs Stale vs Inactive Cache Lifecycles",
        "prompt": "Break down staleTime vs gcTime (formerly cacheTime) in TanStack Query. Many engineers confuse them. Explain how stale-while-revalidate serves instant cached data while fetching fresh data in the background."
    },
    {
        "id": "optimistic_ui_updates",
        "category": "State Management",
        "title": "Architecting Optimistic UI Updates with Error Rollback",
        "prompt": "Explain how optimistic updates work in modern frontend applications (like Twitter likes or Slack messages). Walk through onMutate snapshotting, updating the local cache immediately, and rolling back in onError if the network fails."
    },
    {
        "id": "context_api_vs_redux_zustand",
        "category": "State Management",
        "title": "Context API vs Redux Toolkit vs Zustand: The Re-Render Dilemma",
        "prompt": "Clarify that React Context is a dependency injection tool, not a full state management solution. Explain why updating Context triggers re-renders across all consumers, and how selector-based state stores like Zustand or Redux Toolkit prevent unnecessary renders."
    },
    {
        "id": "redux_toolkit_immer_magic",
        "category": "State Management",
        "title": "How Redux Toolkit & Immer Enable 'Mutable' Syntax Safely",
        "prompt": "Explain how Immer uses JavaScript Proxies under the hood to produce immutable copies while letting developers write state.items.push(item). Contrast this with manual spread operator anti-patterns in deep nested state."
    },

    # Category 4: Web Performance & Browser Internals
    {
        "id": "core_web_vitals_inp_deepdive",
        "category": "Web Performance",
        "title": "Mastering Interaction to Next Paint (INP): Replacing FID",
        "prompt": "Deep dive into Google's INP metric: what it measures (input delay + processing time + presentation delay), why FID was flawed, and actionable techniques to optimize long tasks (breaking tasks with scheduler.yield() or setTimeout)."
    },
    {
        "id": "critical_rendering_path",
        "category": "Web Performance",
        "title": "The Critical Rendering Path: DOM, CSSOM, Layout, Paint & Composite",
        "prompt": "Explain the journey of HTML/CSS bytes to pixels on the screen. Why is CSS render-blocking? What triggers a reflow (Layout) vs a repaint vs compositing, and why should animations stick to transform and opacity?"
    },
    {
        "id": "ssr_ssg_isr_hydration_mismatch",
        "category": "Web Performance",
        "title": "Next.js Rendering Modes: SSR vs SSG vs ISR & Solving Hydration Mismatch",
        "prompt": "Explain Server-Side Rendering (SSR), Static Site Generation (SSG), and Incremental Static Regeneration (ISR). Then explain what hydration is (attaching event listeners to server HTML) and why hydration mismatch errors occur (e.g. window !== undefined checks, timestamps)."
    },
    {
        "id": "code_splitting_bundle_optimization",
        "category": "Web Performance",
        "title": "Code Splitting & Bundle Optimization in Modern React Apps",
        "prompt": "Explain route-based vs component-based code splitting using React.lazy and dynamic imports. How do modern bundlers (Vite / Webpack) split vendor chunks, and how does tree-shaking eliminate dead code via ES Modules?"
    },
    {
        "id": "virtualized_lists_dom_bloat",
        "category": "Web Performance",
        "title": "Virtual DOM is Not Enough: Why 10,000 DOM Nodes Need Virtualization",
        "prompt": "Explain why having 5,000+ DOM nodes causes severe memory and reflow lag regardless of React. Walk through windowing algorithms (@tanstack/react-virtual) that only render visible rows plus a small overscan buffer."
    },
    {
        "id": "web_workers_multithreading",
        "category": "Web Performance",
        "title": "Web Workers: Unlocking True Multithreading in Browser Applications",
        "prompt": "Explain how Web Workers run heavy CPU computations (data parsing, image manipulation, sorting 100k items) on a background thread without dropping 60fps UI frames. How postMessage structured cloning works vs SharedArrayBuffer."
    },

    # Category 5: Modern UI Engineering & CSS
    {
        "id": "css_stacking_context_zindex",
        "category": "CSS Architecture",
        "title": "Why z-index: 999999 Fails: Mastering CSS Stacking Contexts",
        "prompt": "Demystify CSS Stacking Contexts. Explain why a child with z-index: 9999 can never appear above a sibling if its parent has a lower stacking context. List the triggers that create a new stacking context (opacity < 1, transform, filter, will-change, isolation: isolate)."
    },
    {
        "id": "tailwind_jit_vs_runtime_css_in_js",
        "category": "CSS Architecture",
        "title": "The Death of Runtime CSS-in-JS: Why Tailwind & Zero-Runtime Won",
        "prompt": "Explain why styled-components / emotion suffered performance degradation at scale (runtime style injection, serializing styles on every render, React 18 concurrent bottlenecks) and how Tailwind JIT compiles static atomic CSS at build time."
    },

    # Category 6: APIs & Modern Network Protocols
    {
        "id": "websockets_vs_sse_vs_polling",
        "category": "Networking & APIs",
        "title": "Real-Time Web: WebSockets vs Server-Sent Events (SSE) vs Polling",
        "prompt": "Compare WebSockets (full-duplex TCP), Server-Sent Events (unidirectional over HTTP, automatic reconnects), and Short/Long Polling. When should a frontend engineer pick SSE (AI streaming, notifications) over WebSockets (chat, gaming)?"
    },
    {
        "id": "rest_vs_graphql_n_plus_one",
        "category": "Networking & APIs",
        "title": "GraphQL vs REST: Over-fetching, Under-fetching & the N+1 Problem",
        "prompt": "Explain the architectural trade-offs between REST and GraphQL. Discuss the client perspective (single query for nested resources vs multiple roundtrips) and the backend challenge of the N+1 query problem and how DataLoader solves it."
    }
]


def load_history() -> list:
    if Path(HISTORY_FILE).exists():
        try:
            return json.loads(Path(HISTORY_FILE).read_text())
        except Exception:
            return []
    return []


def save_history(history: list):
    Path(HISTORY_FILE).write_text(json.dumps(history, indent=2))


def pick_next_topic(override_topic: str | None = None) -> dict:
    if override_topic:
        # Match from topics or create a custom topic dict
        for t in FRONTEND_TOPICS:
            if override_topic.lower() in t["title"].lower() or override_topic.lower() in t["id"].lower():
                return t
        return {
            "id": "custom_" + str(int(time.time())),
            "category": "Frontend Engineering",
            "title": override_topic,
            "prompt": f"Deep dive into {override_topic} for senior frontend engineers, explaining the concept in layman terms, followed by under-the-hood mechanics, interview tips, and a clean code snippet."
        }

    history = load_history()
    posted_ids = {entry.get("topic_id") for entry in history if entry.get("status") == "posted"}

    # Find unposted topics
    unposted = [t for t in FRONTEND_TOPICS if t["id"] not in posted_ids]
    if unposted:
        return unposted[0]

    # If all posted, cycle randomly from pool
    return random.choice(FRONTEND_TOPICS)


def generate_post_content(topic: dict) -> str:
    """Uses Gemini (with automatic Groq fallback) to draft a high-engagement LinkedIn technical post."""
    system_prompt = """\
You are a Principal Frontend Engineer and technical thought leader known for explaining complex web concepts with surgical clarity and zero fluff.
You write daily LinkedIn posts read by tech leads, hiring managers, and senior engineers.

Follow this exact structure:
1. THE HOOK: 1-2 punchy lines challenging a common misconception or asking a provocative question. No generic greetings ("Hello connections", "Happy Monday").
2. THE ANALOGY (Layman Terms): Explain the concept using a vivid, intuitive real-world analogy that anyone can visualize.
3. UNDER THE HOOD (The Engineering Deep-Dive): Clear explanation of how the browser/engine/React actually executes it step-by-step.
4. CODE SNIPPET (ASCII / Clean Code): A clean, minimal code illustration showing the trap vs the correct approach. Keep it readable in LinkedIn plain text.
5. SENIOR INTERVIEW TIP: Exactly what hiring managers want to hear when they ask this in a technical interview.
6. THOUGHT-PROVOKING QUESTION: A 1-line question inviting engineers to share their production experiences (boosts algorithmic engagement).
7. HASHTAGS: Exactly 4-5 relevant hashtags (e.g. #ReactJS #JavaScript #WebDevelopment #Frontend #SoftwareEngineering).

Tone rules:
- Authoritative, educational, passionate, humble.
- Avoid emoji spam (use at most 3-4 tasteful bullet emojis like 💡, ⚙️, 🚀, 📌).
- Never sound robotic or like marketing fluff. Use human engineering voice.
- Keep total post length between 180 and 320 words (optimal LinkedIn read time).
"""

    prompt = f"""\
TOPIC: {topic['title']}
CATEGORY: {topic['category']}
SPECIFIC FOCUS: {topic['prompt']}

Draft the complete LinkedIn post following all guidelines now.
"""

    # Try Gemini first
    try:
        client = gemini._get_client()
        resp = client.models.generate_content(
            model=gemini.MODEL,
            contents=prompt,
            config=gemini.types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )
        if resp.text:
            return resp.text.strip()
    except Exception as e:
        print(f"  (Gemini unavailable: {e}. Falling back to Groq...)")

    # Fallback to Groq
    try:
        client = groq_llm._get_client()
        chat_completion = client.chat.completions.create(
            model=groq_llm.MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=800,
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"  (Groq also unavailable: {e}. Generating fallback masterclass template...)")

    # Ultimate fallback template if offline
    return f"""💡 Most developers write {topic['title']} every day, but few understand what actually happens under the hood.

Here is the mental model in simple terms:
Think of this like an air traffic control system. If an incoming high-priority flight (user click or typing) arrives, the system shouldn't be blocked by a delayed baggage transfer (background data parsing).

⚙️ Under the Hood:
In the runtime execution pipeline:
1. The engine sets up the execution context with its variable environment.
2. Microtasks get processed immediately after the current macrotask stack clears.
3. React's Fiber reconciler schedules updates based on priority lanes.

📌 Senior Interview Tip:
When asked about {topic['title']}, don't just quote the API syntax. Explain the architectural trade-offs: why this was introduced, what bottleneck it solves, and how it impacts Core Web Vitals (especially INP and main-thread responsiveness).

💬 What's your go-to strategy when debugging {topic['title']} in production?

#ReactJS #JavaScript #Frontend #WebDevelopment #SoftwareEngineering"""


def publish_to_linkedin(post_text: str, headless: bool = False, dry_run: bool = False) -> bool:
    if dry_run:
        print("\n=== DRY RUN: LinkedIn Post Preview ===")
        print(post_text)
        print("======================================\n")
        return True

    session_path = Path(SESSION_FILE)
    if not session_path.exists():
        print(f"ERROR: Session file {SESSION_FILE} not found. Please run login_capture.py first.")
        return False

    print("\n[LinkedIn Post] Launching browser to publish post...")
    with sync_playwright() as p:
        browser_args = []
        if not headless:
            browser_args.append("--start-minimized")

        try:
            browser = p.chromium.launch(headless=headless, args=browser_args)
        except Exception:
            browser = p.chromium.launch(headless=False)

        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()

        try:
            print("[LinkedIn Post] Navigating to LinkedIn feed...")
            page.goto(FEED_URL, wait_until="load", timeout=60000)
            time.sleep(3)

            # Check if logged in
            if "login" in page.url.lower():
                print("ERROR: LinkedIn session expired.")
                return False

            # Click "Start a post"
            print("[LinkedIn Post] Looking for 'Start a post' trigger...")
            start_post_btn = page.locator('button:has-text("Start a post")').first
            if start_post_btn.count() == 0:
                start_post_btn = page.locator('.share-box-feed-entry__trigger').first

            if start_post_btn.count() == 0:
                print("ERROR: Could not locate 'Start a post' button.")
                page.screenshot(path="debug_screenshots/post_trigger_error.png")
                return False

            start_post_btn.click()
            time.sleep(2.5)

            # Locate post editor
            editor = page.locator('.editor-content [contenteditable="true"]').first
            if editor.count() == 0:
                editor = page.locator('div[role="textbox"]').first
            if editor.count() == 0:
                editor = page.locator('.ql-editor').first

            if editor.count() == 0:
                print("ERROR: Could not locate post content editor.")
                page.screenshot(path="debug_screenshots/post_editor_error.png")
                return False

            print("[LinkedIn Post] Typing post content into editor...")
            editor.click()
            time.sleep(0.5)

            # Fast insertion via keyboard/clipboard or sequential typing
            # Using press_sequentially with small delay ensures all formatting & line breaks are preserved
            editor.press_sequentially(post_text, delay=8)
            time.sleep(2)

            # Locate Post button
            post_btn = page.locator('button:has-text("Post")').last
            if post_btn.count() == 0:
                post_btn = page.locator('.share-actions__primary-action').first

            if post_btn.count() == 0:
                print("ERROR: Could not locate 'Post' submit button.")
                page.screenshot(path="debug_screenshots/post_button_error.png")
                return False

            print("[LinkedIn Post] Clicking Post button...")
            post_btn.scroll_into_view_if_needed()
            time.sleep(1)
            post_btn.click()
            time.sleep(5)

            print("✓ [LinkedIn Post] Post published successfully to LinkedIn feed!")
            return True

        except PWTimeout:
            print("ERROR: Timeout during LinkedIn post creation.")
            page.screenshot(path="debug_screenshots/post_timeout.png")
            return False
        except Exception as e:
            print(f"ERROR: Unexpected exception during post: {e}")
            page.screenshot(path="debug_screenshots/post_exception.png")
            return False
        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="Generate and publish daily technical LinkedIn posts.")
    parser.add_argument("--dry-run", action="store_true", help="Draft and preview post without opening browser")
    parser.add_argument("--topic", type=str, default=None, help="Specific topic title or ID to post about")
    parser.add_argument("--unattended", action="store_true", help="Publish automatically without prompting")
    parser.add_argument("--list-topics", action="store_true", help="List all available curated topics")
    args = parser.parse_args()

    if args.list_topics:
        print(f"\nCurated Frontend Domain Topics ({len(FRONTEND_TOPICS)} total):\n")
        for i, t in enumerate(FRONTEND_TOPICS, 1):
            print(f"  {i:2d}. [{t['category']}] {t['title']} (id: {t['id']})")
        print()
        sys.exit(0)

    # Pick topic
    topic = pick_next_topic(args.topic)
    print(f"\n=======================================================")
    print(f"Selected Topic: [{topic['category']}] {topic['title']}")
    print(f"=======================================================")

    print("\nGenerating deep-dive technical post with AI...")
    post_text = generate_post_content(topic)

    # In interactive mode (not dry run and not unattended), show preview and ask confirmation
    if not args.dry_run and not args.unattended:
        print("\n--- GENERATED POST PREVIEW ---")
        print(post_text)
        print("------------------------------\n")
        choice = input("Publish this post to LinkedIn now? [Y/n]: ").strip().lower()
        if choice in ("n", "no"):
            print("Publication cancelled by user. Post saved as draft in history.")
            history = load_history()
            history.append({
                "timestamp": datetime.now().isoformat(),
                "topic_id": topic["id"],
                "topic_title": topic["title"],
                "content": post_text,
                "status": "draft"
            })
            save_history(history)
            sys.exit(0)

    # Publish
    success = publish_to_linkedin(post_text, headless=args.unattended, dry_run=args.dry_run)

    # Record history
    history = load_history()
    history.append({
        "timestamp": datetime.now().isoformat(),
        "topic_id": topic["id"],
        "topic_title": topic["title"],
        "content": post_text,
        "status": "posted" if success and not args.dry_run else "draft"
    })
    save_history(history)

    if success:
        print(f"\n✓ Completed for topic: '{topic['title']}'")
        sys.exit(0)
    else:
        print(f"\n❌ Failed to publish post.")
        sys.exit(1)


if __name__ == "__main__":
    main()
