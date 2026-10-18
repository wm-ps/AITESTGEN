# Vantage Explorer: a smarter way to discover an app and write good tests

> **First implementation step:** save this plan into the repo as `docs/vantage-explorer/PLAN.md`. Then build stage by stage (section 9), starting with Stage 1. Intelligent exploration is the core of the work, and the UI must look rich and polished, in line with the existing Vantage style.

*Written in plain words. A short section for the engineers is at the very end.*

---

## 1. The problem today

Today, Vantage discovery works like a person who has never seen the app and just clicks every link, one by one, typing "Test value" into every box.

That causes three problems:

1. **It misses screens that only show up sometimes.** For example:
   - an "Approval" section that appears only when the amount is above 10,000;
   - a "Spouse details" step that appears only when you pick *Married*;
   - menus only an Admin can see;
   - the "No records found" screen;
   - error screens.
2. **It gets stuck on screens that need real business data**, like a valid policy number.
3. **The test cases it writes don't make sense.** It guesses what *should* happen instead of knowing.

## 2. What we will build

We will build a new helper called **Vantage Explorer**. It is a separate add-on, so **the current discovery keeps working exactly as it does today**. We only switch over once Explorer is clearly better.

Explorer behaves like a **sharp new QA engineer in their first week on the job**.

---

## 3. How Explorer works, step by step

### Step 1: It gets to know the app first
- It logs in and looks around the menus and main screens.
- It reads any documents you give it, such as requirement docs or manuals. These are optional.
- Then it writes a **one-page summary of the app**. For example: *"This is an insurance portal for agents. The main things are Customers, Quotes, Policies and Claims. The key tasks are: create a quote, turn it into a policy, file a claim."*
- **You read it and fix anything wrong.** This takes about 30 seconds.

### Step 2: It keeps a mental map, not a list of web pages
- It remembers what each screen **means**, for example "Quote list", "New quote form" or "Approved quote details".
- 1,000 different customer pages count as **one** screen called "Customer details", so it never gets lost.

### Step 3: It makes a to-do list of goals
- These are goals like *"Create a quote"*, *"File a claim on an active policy"* or *"Check what an Admin can see"*.
- It does the most important things first. You can add or remove goals.
- It works on several goals at the same time.

### Step 4: It explores like a scientist
It makes a guess, then tests it. Two examples:
- *"I think Age must be 18 or more."* It tries 17, then 18. **Confirmed.**
- *"I think choosing Married adds new fields."* It switches the choice and watches the screen. **Confirmed, and now it knows that hidden step exists.**

Every rule it learns gets a trust color (section 4). A rule the app shows, but that nobody has confirmed, is never treated as correct. It becomes a question for you.

### Step 5: It makes its own test data
- To test "File a claim", it knows it first needs a customer, then a quote, then a policy, so **it creates them itself, in order.**
- It only asks you for things it truly can't make up, like a real bank account number or a policy number from an old system.

### Step 6: It asks you smart questions
- **It asks only when the answer really matters.**
- **Every question is simple and multiple-choice, with a screenshot.** For example:
  > *"A claim of 50,000 went through with no approval step. Is that correct?"*
  > [Yes, there is no limit] · [No, approval is needed above ____]
- **Only that one task waits for your answer.** Everything else keeps going.
- **It remembers every answer and never asks the same thing twice**, not even on the next run.

### Step 7: It hunts for hidden screens on purpose
Explorer has **seven ways to find screens that only appear sometimes**, described in the next section.

### Step 8: It writes test cases that make sense, and proves them
- It writes tests in **only 5 kinds**, described in section 5.
- Every test:
  - says in one line **why it exists**;
  - **quotes the real message** the app showed, for example *"Applicant must be 18 or older"*, instead of guessing;
  - is based only on trusted rules (from you, your documents or common sense), **never on "the app did it, so it must be right"**;
  - is **run 3 times** and must give the same result every time;
  - is then run once with something deliberately broken, and **must fail**. This proves the test can actually catch a bug.
- **Tests that can't do all this are thrown away.** You only see good ones.
- If the app itself is wrong, the correct test is kept and labelled **"Known bug: expected to fail"**, together with a bug report (section 4).

### Step 9: It shows its work
- **Live screen while it runs:**
  - a picture of what the browser is doing right now;
  - a short line about what it's thinking (*"Checking if Age has a minimum… trying 17"*);
  - counters: screens understood · **hidden screens found** · rules confirmed · questions waiting · tests proven.
- **A map of the app** that grows while you watch. Hidden screens are marked with a note like *"Appears when amount is over 10,000"*.
- **A video recording** of every task it did.
- **A final report** with a coverage chart and a short highlight video you can share with your stakeholders.

---

## 4. Explorer never treats the app as "the truth"

The app might be buggy. If Explorer simply wrote down whatever the app does and called it correct, it would **turn bugs into "expected behavior"** and write tests that protect those bugs. So Explorer works like a good QA engineer: **it decides what *should* happen before it looks at what *does* happen.**

### 4.1 Where "the truth" comes from, most trusted first

| Trust level | Source | Example |
|---|---|---|
| 1. Highest | **You (or your team)** | "Claims above 50,000 need approval" |
| 2 | **Your documents**: requirements, user stories, acceptance criteria, manuals | "Password must be at least 8 characters" |
| 3 | **Common sense and industry rules** the AI already knows | An email needs an "@"; an end date can't be before the start date; a saved record should still be there after reload; nothing should show a raw error page |
| 4 | **The app agreeing with itself** | The list says 12 quotes, so the count badge should also say 12; the detail page shows the same amount as the list |
| 5. Lowest | **What the app actually did** | It accepted age 15. This is only *a fact about the app*, never proof that it's right. |

The app's behavior is **evidence**, not truth.

### 4.2 Guess first, then compare
Before every important action, Explorer first writes down **what it expects to happen**, based on trust levels 1-4. Then it acts and compares:

- **Matches:** good, the behavior is marked as checked.
- **Doesn't match:** flagged as a **"Possible bug"**, with the screenshot, the video moment and the reason. For example: *"Expected: age 15 is rejected (common sense: policy holders must be adults). Actual: accepted."*
- **No expectation possible:** marked **"Unconfirmed"**, and it becomes a question for you if it matters.

### 4.3 Every rule carries a trust color
Shown everywhere in Explorer:

| Color | Meaning |
|---|---|
| 🟢 **Confirmed** | Backed by you or your documents |
| 🔵 **Standard rule** | Common sense or an industry rule nobody has contradicted |
| 🟡 **Seen only** | The app does it, but nobody has said it's right |
| 🔴 **Looks wrong** | The app contradicts a trusted source |

Tests are only ever based on 🟢 and 🔵 rules. 🟡 and 🔴 turn into questions like: *"The app accepted age 15. Is that correct, or is it a bug?"* [It's correct] · [It's a bug: minimum should be ___]

### 4.4 Health check first
Before exploring deeply, Explorer does a quick **App Health Check**:
- pages that crash or never finish loading;
- broken links;
- error messages hidden in the background;
- server errors;
- very slow screens;
- spelling mistakes in labels.

You get a **health score** at the start:
- **Healthy app:** Explorer works normally.
- **Unhealthy app:** Explorer warns you up front (*"This app has 14 broken pages and frequent server errors"*) and switches to **requirements-first mode**. It leans much more on your documents and answers, asks more questions, and treats what it sees with extra suspicion.

### 4.5 Two kinds of results
1. **Proven tests:** the app behaves correctly, and the test passes and is proven.
2. **Bugs found:** the app does something different from what it *should* do. For each, Explorer still writes the correct test (it will fail until the bug is fixed) and labels it **"Known bug: expected to fail"**. It comes with a ready-to-share bug report: steps, expected vs actual, screenshot and video.

So a broken app gives you a **bug list plus correct tests**, not wrong tests. The final report shows both, side by side.

---

## 5. Finding hidden screens: the seven ways

| # | Why a screen is hidden | Example | How Explorer finds it |
|---|---|---|---|
| 1 | **It depends on a choice on the same form** | Picking *Married* shows a "Spouse" step | Changes one choice at a time and watches what appears or disappears |
| 2 | **It depends on the record's status or amount** | "Approve" button only on submitted quotes; approval section above 10,000 | Creates records itself, moves them through each status, and tries amounts to find the exact cut-off |
| 3 | **It depends on what data comes back** | "No results" screen, very long lists, error messages, loading screens | Pretends inside its own browser that the server sent back "nothing", "a lot" or "an error", so the app shows those screens. **The real server and real data are never touched.** |
| 4 | **It depends on who is logged in** | Admin-only menu, read-only screens for viewers | Explores once per user type and compares. You get a "who can see what" chart. |
| 5 | **It depends on a switch or a date** | A new feature turned on for some users; "Renew" only shows in the last 30 days | Pretends the feature is turned on, or that it's a different date, and looks again |
| 6 | **Nothing links to it** | A page you only reach from an email link | Reads the app's own website files (the ones every browser downloads anyway) to find a list of all its pages, then visits the ones nobody links to |
| 7 | **Anything still missed** | Unknown | Checks which parts of the app have never been shown yet, and sends a task to go look there |

**Always honest:** screens found with the "pretend" methods (#3 and #5) carry a **"Simulated"** label, so everyone knows what was real and what was forced.

---

## 6. The 5 kinds of test cases

| Kind | What it checks | Example |
|---|---|---|
| **Navigation** | Every menu and link goes to the right place, and people without permission are kept out | "Viewer opens the Admin page and is sent to 'Not authorised'" |
| **Validation** | Every rule on every form field | "Age 17 shows 'Applicant must be 18 or older'. Age 18 is accepted." |
| **Error states** | What the user sees when something goes wrong | "Saving a customer that already exists shows 'Customer already exists'" |
| **Data load** | Lists, searches and details show the right information | "Search for the policy just created: exactly one result, all details match" |
| **Form submission** | Saving works, and the data is really kept | "Submit a quote of 12,000: status becomes 'Pending approval', and after reload every field is still there" |

At the end you see a **simple grid**:
- one row per business area (Customers, Quotes, Policies, Claims);
- one column per kind of test;
- each box is either filled with proven tests or explains why it's empty, for example *"waiting for your answer"* or *"doesn't apply"*.

---

## 7. Where you'll see it in Vantage

A new **"Explorer"** item (tagged **Beta**) appears in each application's left menu, right next to **Journeys**. It uses the same colors, fonts, cards and buttons as the rest of Vantage, so it feels like part of the product.

The Explorer tab has these screens:

| Screen | What it shows |
|---|---|
| **Start** | Pick the user types and logins to use, optionally upload documents, and press Start |
| **App summary** | The one-page summary from Step 1, which you can edit and confirm |
| **Live** | Three side-by-side areas: goals (waiting, running, needs you, done), what the browser is showing right now, and what Explorer is thinking. Counters across the top. |
| **Questions** | Explorer's questions, each with a screenshot and answer buttons. A small badge shows how many are waiting. |
| **App map** | The map of all screens. Hidden screens have a dotted border and a note on why they appear. Click any screen to see its details. |
| **Health** | The health score and problems found at the start (broken pages, server errors, slow screens) |
| **Rules** | Every business rule learned, with its trust color and where it came from: told by you, from a document, common sense, or only seen in the app |
| **Bugs found** | Places where the app does something different from what it should, each with expected vs actual, a screenshot and a video, ready to share |
| **Test cases** | Grouped into the 5 kinds, with the grid on top. Click a test to see its steps, the real message it checks, a screenshot and the proof video. |
| **Report** | A summary, the "who can see what" chart and the shareable highlight video |

---

## 8. The AI we use

Explorer uses **GPT-5.6 models only**:
- the strongest GPT-5.6 model for understanding the app, planning, reading screenshots and writing test cases;
- a smaller GPT-5.6 model for quick, simple checks, to keep it fast.

Cost is not a concern, so we always pick quality first.

---

## 9. How we'll build it: one demo at a time

Each stage ends with something you can show a client.

| Stage | What gets built | What you can demo |
|---|---|---|
| 1 | Explorer tab, health check, app summary, live screen | "It understood my business correctly, and told me how healthy the app is" |
| 2 | Goals, exploring, app map, recordings | Watch it work and the map grow live |
| 3 | Scientist mode, own test data, hidden-screen hunting (ways 1-3) | "It found the approval screen nobody found before" |
| 4 | Questions and answers, memory, document upload | Answer one question and watch that task continue |
| 5 | Trust colors, guess-then-compare, bugs found, proven test cases in 5 kinds, the grid | Correct tests plus a bug list, even on a buggy app |
| 6 | Hidden-screen hunting ways 4-7, re-runs that only check what changed | "Who sees what" chart; second run is much faster |
| 7 | Final report and highlight video | A shareable video for stakeholders |
| 8 | *(only after you approve)* Explorer replaces the old discovery | One single product |

## 10. How we'll know it's better before we switch

We build 2 small sample business apps where **we already know the answers**: which hidden screens exist, which rules exist and which user types exist. We run the old discovery and Explorer on both and compare:
- how many hidden screens each found;
- how many rules each confirmed;
- **how many planted bugs each caught.** The sample apps contain deliberate bugs. Explorer must report them as "Bugs found" and must **not** write tests that treat them as correct.
- how many questions it asked (fewer and sharper is better);
- how many tests are proven;
- a QA lead blindly rating 20 random tests for "does this make sense?".

**We switch only when Explorer wins clearly.**

## 11. Safety

- Explorer only does its experiments on **test environments, never live production.**
- It **always asks before** pressing anything like Delete, Approve or Pay.
- **Passwords and private data are hidden** in videos and screenshots.
- Anything that was "pretended" is labelled **Simulated**.

---

## For the engineers (short version)

- **Standalone:**
  - new worker `apps/workers/explorer`;
  - new shared package `packages/explorer_core`, which holds the app map, AI prompts, browser control, hidden-screen finders and test builder;
  - new API section `/explorer`;
  - new web folder `apps/web/src/explorer`.

  The old discovery, generation and live-exploration code is not imported or changed.
- **Existing code touched (wiring only):**
  - one line in `apps/api/src/api/main.py` to add the routes;
  - the tab entry in `apps/web/src/App.tsx`;
  - the workspace entry in the root `pyproject.toml`.
- **Shared servers only:**
  - Postgres: own `explorer` schema, plus the pgvector extension for memory search;
  - Temporal: own task queue. Each question pauses only its own task until the answer arrives.
  - Vault: own `explorer/` path for logins;
  - file storage: own `explorer/` folder.
- **AI:** GPT-5.6 through an OpenAI-compatible client owned by the explorer package. The current LiteLLM gateway is used only as the network endpoint, if the company requires it.
- **Live screen:** a one-way event stream from the API, with roughly one screenshot per second per task. **App map:** React Flow.
- **UI rules:**
  - V2 colors and fonts from `apps/web/src/tokens.css`;
  - the glass card style;
  - `StatusPill`, the ring `Spinner`, `EmptyState`, `Pagination` and `Toast`;
  - vertical ⋮ menus;
  - placeholders that tell the user what to do.
- **Tests:** run only the narrow tests for each new piece (`pytest apps/workers/explorer/tests/test_<area>.py`, `vitest run <file>`, `tsc --noEmit -p tsconfig.app.json`). No full suite runs.
- **End-to-end check:** start everything with `/test` plus the explorer worker. Then run on a sample app and confirm:
  1. the Married/Spouse step and the over-10,000 approval screen are found and marked as hidden on the map;
  2. a question pauses only one task, and answering it resumes that task;
  3. a second run asks nothing new;
  4. every test shows its kind, the quoted message and a proof video.

  Then check in the browser that the Explorer tab looks native next to Journeys.
- **Research behind this design:**
  - AutoE2E and VISCA: understand features first;
  - LLM-Explorer and AutoDroid: keep a compact app map;
  - Skyvern and Agent-E: separate planner, doer and checker;
  - FormNexus and Black Widow: learn form rules and data chains;
  - Temac and FEEDEX: aim at unexplored code;
  - Meta ACH: prove tests by breaking things;
  - SAGE-Agent: ask only valuable questions.
