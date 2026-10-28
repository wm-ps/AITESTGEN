---
title: "Vantage (AITestGen) — Product Requirements"
status: final
created: 2026-07-13
updated: 2026-10-27
---

# PRD: Vantage (AITestGen)

## 0. Document Purpose

This PRD describes Vantage as it is built today, 2026-10-27. It is written for the people who build, test, sell and support it. It builds on the [Product Brief](../../briefs/brief-AITestGen-2026-07-12/brief.md). Competitive positioning and the longer-term vision are in `addendum.md` next to this file.

Functional requirements are grouped by the eight epics and their stories. Each requirement is numbered `FR-<epic>.<story>.<n>` so it can be referenced from the story files. Every requirement describes behaviour that exists today unless it is marked **Partly built** or appears in §7, *Not built / deferred*.

## 1. Vision

Vantage turns a deployed web application into a working, maintained Playwright test suite with very little hand-writing of tests.

A team adds an application with its URL and, if needed, a test login. Vantage can explore the application by itself. Its default discovery engine, Explorer, learns the application, has a person confirm what it learned, asks when it is unsure, and writes and proves scenarios; Vantage then writes tests for the proven ones. Teams can also describe a test in plain English, or record one by clicking through it. They run tests on demand or on a schedule. AI repairs failing tests without ever changing what they check. Results come with plain-language explanations, flaky flags, a branded report and an email.

The longer-term direction runs from coverage, to understanding the application, to predicting the impact of a change. It is described in `addendum.md` and is not part of the product today.

## 2. Users and Roles

### 2.1 Who uses it

- **QA leads and QA teams.** The main daily users. They add applications, curate journeys and scenarios, author and record tests, run and schedule suites, and read failures.
- **Engineering leaders.** They watch health across applications on the Overview and the Applications list.
- **Workspace admins.** They manage the team, roles, settings, saved credentials and the Activity history.

Accounts are invite-only and belong to exactly one organization. Nobody can sign themselves up.

### 2.2 Roles and permissions

There are three roles. The server enforces each permission, and the screens hide controls a role cannot use. **Explorer is the exception:** it refuses viewers' changes like everywhere else, but it does not limit admin-only actions to admins or refuse its downloads to viewers, and its buttons are not hidden from viewers.

| Capability | Admin | Member | Viewer |
|---|---|---|---|
| See every application, journey, scenario, test case, run and result in the organization | yes | yes | yes |
| Add an application; start, pause or resume Discovery | yes | yes | no |
| Use Explorer: start, pause, stop or resume a run, confirm the App Summary, answer questions, judge possible bugs | yes | yes | no (buttons shown, but refused) |
| Explorer: add or forget knowledge and documents, add other user types with their passwords | yes | **yes (gap: should be admin only)** | no |
| Download Explorer's tests, run report, mission recordings and highlight video | yes | yes | **yes (gap: refused to viewers elsewhere)** |
| Rename or delete an application | yes | no | no |
| Rename or delete journeys and scenarios, edit test data, generate scenarios and test cases, stop generation | yes | yes | no |
| Author a test case in plain English; Record and play | yes | yes | no |
| Run tests (all or selective), cancel a run, retry a failure with self-healing | yes | yes | no |
| Create, edit, turn on or off, delete and "run now" schedules | yes | yes | no |
| Open a run's HTML report | yes | yes | no |
| Download the project | yes | yes | no |
| Team members: invite, change a role, remove someone (revoking a pending invite works behind the scenes but has no screen) | yes | no | no |
| Activity history | yes | no | no |
| Settings, including saved credentials and each application's Sign-in switch | yes | no (sees the link, gets "Access denied") | no (link hidden) |

Rules:
- A viewer cannot change anything, Explorer included. Known gaps: viewers can download Explorer's results, and members can manage Explorer's user types and knowledge (see the table).
- Admins cannot remove themselves or change their own role. The last admin cannot be demoted.
- A role change takes effect on the user's next action.

## 3. Glossary

- **Application.** A deployed web application a team adds to Vantage, with a name, environment, URL and optional login.
- **Discovery.** Vantage exploring an application by itself in a real browser to find its journeys. Discovery is optional per application. It has two engines: **Explorer** (the default) and **classic discovery** (Epic 2), which now runs only for applications discovered before Explorer became the default, or when operations switch Explorer off.
- **Explorer.** The default discovery engine (Epic 8). It learns the application, has a person confirm an App Summary, asks questions, works through missions and writes and proves scenarios.
- **App Summary.** Explorer's one-page description of the application (name, one-liner, key tasks, its questions, screens to leave out), which a person checks and confirms before Explorer goes further.
- **Mission.** A goal Explorer works towards, such as "file a claim" or "try the 'someone hurt' branch".
- **Proven scenario.** An Explorer scenario that replays the same way every time and fails when its key step is removed on purpose. Only proven scenarios are handed on to test generation.
- **Possible bug.** An Explorer scenario where the application did something different from what should happen. It is kept for a person to judge, never handed on as a passing test.
- **Journey.** A named, business-language user flow found by Discovery, or named by a user when they author a test. It has a screenshot and page-by-page steps.
- **Scenario.** A test idea for a journey, made up of test steps, test data and an expected result.
- **Test case.** A runnable Playwright test. It can come from a scenario ("From discovery"), from a plain-English description ("Authored by prompt") or from a recording ("Recorded"). Every test case has a number.
- **Run.** One execution of all or some of an application's test cases. Every run has a number.
- **Self-healing.** AI repair of a failing test. It may change how the test finds things on the page, never what it asserts.
- **Flaky.** A test whose last 10 finished results include at least one pass and at least one failure.

## 4. Functional Requirements

### Epic 1 — Foundation, Sign-in & Application Onboarding

#### 1.1 Platform foundation
- **FR-1.1.1** Vantage runs as a web app backed by a server and separate background services for classic Discovery, Explorer, generation, test execution and recording. Each one can be deployed and restarted on its own. **Partly built:** Explorer's service has no deployment setup yet (see §10).
- **FR-1.1.2** When a background service needed for an action isn't running, the user sees a clear "service unavailable" message instead of a silent failure. When the server itself can't be reached, a "service unavailable" screen with a Retry button replaces the sign-in page.

#### 1.2 Sign in, password reset & organization-scoped workspace
- **FR-1.2.1** Users sign in with email and password.
- **FR-1.2.2** A session ends after 1 hour without activity, and any activity extends it. When it ends, the user returns to Sign in with "Your session expired from inactivity".
- **FR-1.2.3** "Forgot password?" sends a reset link that expires after 1 hour. The screen always says "Check your email", so it never reveals whether an account exists. A new password must be at least 8 characters and is entered twice.
- **FR-1.2.4** An invite link opens "Set up your account". The invitee enters a full name and a password, joins the inviting admin's organization and is signed in straight away. An invalid, expired or already-used link shows one generic error.
- **FR-1.2.5** Every piece of data belongs to one organization. Users only ever see their own organization's data.

#### 1.3 Add an application: basic details and connection test
- **FR-1.3.1** The form asks for an application name, an environment (staging, production, qa, or "other" with a custom name) and a URL.
- **FR-1.3.2** The URL must pass **Test connection** before the form submits. Trying to submit without it shows a reminder, and the server checks reachability again on submit.
- **FR-1.3.3** An "Autonomous discovery" checkbox, on by default, decides whether Discovery runs. With it on, the new application is discovered by Explorer (unless operations have switched Explorer off, in which case classic discovery runs). The submit button reads "Start discovery" or "Add application" to match.
- **FR-1.3.4** Once submitted, the form becomes a read-only record of what was submitted. The stored username and password are never shown there again.
- **FR-1.3.5** Each new application gets three schedules, all turned off: Nightly, Weekly and Monthly Regression.
- **FR-1.3.6** There is no limit on the number of applications.

#### 1.4 Application sign-in method
- **FR-1.4.1** A toggle, "This application requires sign-in", asks for an optional login URL, a username and a password or token. When it is off, the application is treated as needing no login.
- **FR-1.4.2** Credentials are stored encrypted and used only while Discovery or a run is happening. They are never shown again, except when an admin reveals one in Settings, and that reveal is logged.
- **FR-1.4.3** **Partly built.** Reusing a saved single sign-on browser session, and storing an MFA code seed when credentials are rotated, work on the server but have no screen.

#### 1.6 Dynamic browser tab branding
- **FR-1.6.1** **Superseded.** The browser tab always shows "Vantage" with the platform icon. The planned behaviour, where the tab showed each application's own name and icon, is not in the product.

#### 1.7 App shell, sidebar navigation & Overview dashboard
- **FR-1.7.1** A left sidebar has Overview; Applications, with a count; and Add application, which viewers don't see. When no application is open it also has a Configuration group: Team members and Activity for admins only, and Settings.
- **FR-1.7.2** When an application is open, the sidebar shows its name, an Exit link and these tabs in order: Overview, Journeys, Explorer, Scenarios, Test cases, Test runs, Record and play, Schedules, Download project.
  - Journeys, Explorer and Scenarios appear only when Discovery is on for the application.
  - For an application Explorer has discovered, Journeys and Scenarios are hidden; Explorer's own Scenarios sub-tab replaces them, and any link to them opens Explorer. Applications discovered by classic discovery keep Journeys and Scenarios and also get the Explorer tab. Once Explorer is started on such an application, it counts as an Explorer application from then on.
  - Record and play and Download project are hidden from viewers.
  - Tabs can be opened in any order.
- **FR-1.7.3** A top bar shows a breadcrumb, an Add application button and an account menu with Log out.
- **FR-1.7.4** The org-wide **Overview** shows:
  - Headline figures: applications tested, test cases generated, pass rate, failure rate, average run duration, self-healed locators and last discovery. Some figures cover the last 7 days.
  - Three charts: pass rate over time, latest run outcome and test cases per application.
  - An **Active pipelines** list of what is running now. Clicking an item opens that application.
  - Empty states when there are no applications or no runs yet.
- **FR-1.7.5** The **Applications list** has columns Application, Journeys, Tests, Pass rate, Last activity and Status, and is paginated.
  - Status shows the current stage: discovery, generation, "Ready to run" or "Running". After the first completed run it shows a health tier: Healthy, Needs attention or Critical.
  - A tooltip shows the percentage of journeys covered by scenarios.
  - Opening an application lands on its most useful tab: Test cases while tests are first being generated or when the application has no Discovery; Overview once a test suite exists; otherwise **Explorer** for an Explorer application, or Scenarios or Journeys for a classic one. Right after an application is added with Discovery on, it opens on Explorer.
- **FR-1.7.6** Admins have a ⋮ menu on each application:
  - Rename, done inline.
  - Delete, after a confirmation. Delete is blocked, with the reason shown, while Discovery, generation or a run is in progress.
  - Deletion hides the application at once and permanently removes its data after the retention period set in Settings. Its schedules stop.
- **FR-1.7.7** An application's own **Overview** tab is always listed; it shows "No test runs yet" until the first run finishes, then shows:
  - The health tier, the last run's pass rate with a link to that run, and a pass-rate trend.
  - Counts: journeys, test cases, open failures, and passed, failed and not run.
  - Quick-action cards for the other tabs. For an Explorer application, the Journeys and Scenarios cards are replaced by one **Open Explorer** card ("See what it learned and the scenarios it proved").

### Epic 2 — Runtime Discovery & AI Journey Inference

*Scope: everything in Epic 2 describes the **classic discovery engine**. It now runs only for applications discovered before Explorer became the default, or for new applications when operations switch Explorer off. Explorer is described in Epic 8. The login check (2.23) and optional discovery (2.24) apply to both engines.*

#### 2.1 Start a discovery run
- **FR-2.1.1** When classic discovery is in use, adding an application with Discovery on starts it straight away, after the login check in 2.23 has passed. Otherwise Explorer starts (FR-8.1.1).
- **FR-2.1.2** Discovery runs in the background. The Journeys tab fills in live without the user staying on the page.

#### 2.2 Autonomous exploration captures evidence
- **FR-2.2.1** Discovery explores in a real browser and records what it finds: pages, forms and their fields, actions, the application's own network calls and page-to-page transitions. It takes a screenshot of each page.
- **FR-2.2.2** It explores breadth-first and handles content inside frames, nested components, pop-ups and new tabs (new tabs are recorded, not explored further).

#### 2.3 Discovery stop conditions & completeness status
- **FR-2.3.1** Discovery stops when no new pages remain, or when it reaches the admin limit for maximum pages (500 by default) or maximum discovery time (30 minutes by default).
- **FR-2.3.3** Finishing Discovery does not start scenario or test generation by itself. The user starts each step (FR-3.1.3, FR-4.2.1).
- **FR-2.3.2** A run ends as finished, paused or failed, and the Journeys tab shows which.

#### 2.4 Session expiry handling
- **FR-2.4.1** If the application logs Discovery out partway through, Discovery logs in again and carries on. It gives up after a few attempts in a row.
- **FR-2.4.2** When it can't recover, the Journeys tab shows a "session expired" banner. The run does not silently produce an empty or partial result.

#### 2.5 Application model builder
- **FR-2.5.1** After exploring, Vantage merges duplicate captures of the same page, form or network call, within a run and across runs, into one record per application.
- **FR-2.5.2** Every element that can be automated gets a preferred way to find it and fallback ways. Expected outcomes are derived for use in tests.

#### 2.6 AI journey and capability inference
- **FR-2.6.1** AI groups the explored pages into business-language journeys with descriptions, not raw page addresses.
- **FR-2.6.2** Each journey has a stable identity, so running Discovery again does not create duplicates of journeys already found.

#### 2.7 Business-oriented progress display
- **FR-2.7.1** While Discovery runs, the Journeys tab shows plain-language stages: Exploring pages, Capturing screenshots, Grouping flows, Mapping journeys. It adds the note "Discovery runs in the background — this list updates automatically". No technical crawl terms appear.

#### 2.8 Cloud storage for screenshots and evidence
- **FR-2.8.1** Discovery screenshots and run evidence (screenshots, traces) are kept in durable cloud storage and survive restarts and redeployments.

#### 2.9 Page readiness, infinite scroll & pagination
- **FR-2.9.1** Before capturing a page, Discovery waits for it to settle: network activity quiet, ignoring analytics and polling, the layout stable and content present.
  - The wait is capped by the admin's navigation timeout. A per-application override exists, but it has no screen.
  - A page that never settles is noted, and Discovery moves on.
- **FR-2.9.2** For infinite scroll and "load more", Discovery samples a few rounds and then stops, rather than paging forever.

#### 2.10 State identity engine
- **FR-2.10.1** Each new view is judged as the same as one already seen, a variant of one, or new. A record page that differs only by its data (for example, two claims in the same status) is explored once. A record page that offers different actions is kept as a separate variant.

#### 2.11 Exploration planner & action priority
- **FR-2.11.1** On each page, Discovery tries the actions inside the page, including tabs, before following navigation links elsewhere. It tries one action per distinct button label, with no per-page cap.
- **FR-2.11.2** When it loses its place, Discovery returns to the application's start page and continues.

#### 2.12 Safety engine
- **FR-2.12.1** Every action is classed as safe, clearly destructive or ambiguous. Clearly destructive actions, such as delete, payment or transfer, are never performed. Ambiguous actions, such as submit or approve, are skipped or deferred according to the application's safety setting.
- **FR-2.12.2** The admin's interaction level (Passive, Normal or Aggressive) controls how far Discovery goes in interacting with the application.
- **FR-2.12.3** Classification is rule-based. AI-assisted classification is built but switched off; see §7.

#### 2.13 Data resolver
- **FR-2.13.1** When a form needs input, Discovery tries these sources in order:
  - the application's test data pool,
  - a value it already used earlier in the run,
  - safe made-up data for generic fields.
  If none fits, it defers that form rather than guessing. Every value used is recorded.
- **FR-2.13.2** **Partly built.** Reusing a value visible on the current page is not built.

#### 2.14 Widget coverage
- **FR-2.14.1** Discovery recognizes tab groups and dialogs from their accessibility roles, explores each tab and closes dialogs safely to get back to the page underneath. New tabs and pop-ups that open from the application are recorded as linked pages (address and title) but not explored further.

#### 2.15 Blocked frontier
- **FR-2.15.1** A deferred action or form never stops the run. Requests that need the same missing data are merged into one.
- **FR-2.15.2** **Partly built.** There is no screen to see or answer these requests.

#### 2.16 Blocked mid-exploration persistence & resume
- **FR-2.16.1** **Partly built.** Vantage records the path that led to a blocked point. Resuming from that point once the data is supplied is built but not connected to any screen.

#### 2.17 Pause and resume a discovery effort
- **FR-2.17.1** For classic applications, **Pause Discovery** and **Resume Discovery** buttons are on the Journeys tab. For any application that has ever had an Explorer run they are refused with "Explorer discovers this application: pause or resume it from the Explorer tab." (FR-8.1.4). Resume continues from where Discovery stopped and does not re-explore what was already captured. A "Paused" banner shows the state.
- **FR-2.17.2** **Partly built.** There is no summary of confirmed, blocked and remaining work for a paused run.

#### 2.18 Crash recovery & error taxonomy
- **FR-2.18.1** If the Discovery service restarts mid-run, the run recovers by itself, and a "recovered and resuming" banner says so.
- **FR-2.18.2** Problems are recorded as one of a small fixed set:
  - restarted after a crash,
  - session expired,
  - application unreachable after retries,
  - page did not settle in time,
  - lost its place after a form submit,
  - form field lookup timed out.
  An unreachable page is retried a few times, then skipped.

#### 2.19 Loop prevention
- **FR-2.19.1** Before each action, Discovery checks for repeated views, actions it already performed from the same place and back-and-forth cycles, so it never clicks the same thing forever.

#### 2.20 Test data pool
- **FR-2.20.1** **Partly built.** Each application has a pool of test data values that Discovery uses first when filling forms. The pool can only be managed outside the screens; there is no screen for it.

#### 2.21 Locator durability
- **FR-2.21.1** Every captured element has a preferred locator and fallback locators, each rated for how likely it is to survive changes to the application. Generated tests use the most durable one. Locators that rely only on placeholder text are treated as fragile.

#### 2.22 Coverage report & diagnostics
- **FR-2.22.1** **Partly built.** For each run, Vantage builds a coverage report showing what was reached, blocked, skipped, errored or never reached, along with diagnostic detail. There is no screen for it.

#### 2.23 Validate login before discovery starts
- **FR-2.23.1** If Discovery is on and the application needs a login, Vantage first logs in with the given credentials in a real browser.
  - Wrong credentials show "The username or password is incorrect…".
  - A result it can't confirm, such as a timeout, shows "We couldn't confirm these credentials…".
- **FR-2.23.2** Discovery never starts on a login that hasn't been proven to work.

#### 2.24 Optional autonomous discovery
- **FR-2.24.1** Clearing "Autonomous discovery" adds the application without exploring it. The Journeys, Explorer and Scenarios tabs are hidden, and the team builds tests by authoring or recording them.

### Epic 3 — Journey Curation

#### 3.1 Discover Journeys: candidate list and detail
- **FR-3.1.1** Journeys appear as cards. Each card shows a screenshot, which can be clicked to enlarge, and the journey's page-by-page steps. Repeated steps on the same page are collapsed into one business step.
- **FR-3.1.2** Journeys can be searched.
- **FR-3.1.3** **Review scenarios** starts scenario generation and moves to the Scenarios tab. Journeys do not need approval first.
- **FR-3.1.4** Banners cover a session expired during Discovery, a failed run, a paused run, and recovery after a restart.
- **FR-3.1.5** For an Explorer application (where the tab is hidden from the sidebar), the Journeys page shows an **Open Explorer** button and "Explorer is finding this app's journeys. They appear here when it has finished." It has no Pause or Resume and no classic progress view.

#### 3.4 Rename and delete a journey
- **FR-3.4.1** Members and admins can rename a journey.
- **FR-3.4.2** Deleting a journey excludes it, and anything generated from it, from later generation and from counts.
- **FR-3.4.3** Merging, splitting or editing a journey's steps is not supported.

### Epic 4 — Scenario & Test Case Generation

#### 4.1 Generate scenarios for a journey
- **FR-4.1.1** Scenarios are drafted for each journey and grouped by journey. Progress shows Reading journeys, Drafting scenarios and Deriving test data.
- **FR-4.1.2** Each scenario shows its test steps, its test data fields and its expected result. Each field is marked "Required for this scenario" or "Optional — auto-filled if left blank".
- **FR-4.1.3** Users can rename or delete a scenario, edit test data inline, **Auto-generate** test data and clear values.
- **FR-4.1.4** If one journey's scenarios fail to generate, the others carry on. Failed journeys are listed with the reason; there is no way to retry them.
- **FR-4.1.5** Admin limits cap the number of scenarios per journey and the number of test cases per application.
- **FR-4.1.6** There is no approve or reject step for scenarios.
- **FR-4.1.7** For an Explorer application, the Review scenarios page keeps **Generate test cases** and adds "Explorer worked these out by using the app. Generate test cases to turn them into tests.", with its own empty-state message. Explorer's scenarios are not drafted here; they arrive already proven (FR-8.5.1).

#### 4.2 Generate Playwright test cases from scenarios
- **FR-4.2.1** **Generate test cases** writes a TypeScript Playwright test for each scenario and opens a progress screen. The screen shows:
  - Stages: Resolving locators, Writing test cases, Generating fixtures.
  - Counts: test cases, journeys covered and estimated runtime.
  - Each journey's status, including "Incomplete" when some scenarios could not be generated after retries, and "Terminated".
- **FR-4.2.2** Users can **Terminate** generation for a journey, **Retry Generation**, **Download Test Cases** or **Run Test Cases** from that screen.
- **FR-4.2.3** Every generated test is type-checked and automatically repaired if it does not compile. Tests with lint concerns are flagged for review rather than rejected.
- **FR-4.2.4** For a scenario handed on by Explorer, the test Explorer already wrote and proved is used as-is if it compiles; the AI writes a new one only if it does not.

#### 4.3 Download a generated test project
- **FR-4.3.1** The Download project tab shows the project structure:
  - one test file per test case, grouped in a folder per journey,
  - shared fixtures and utilities,
  - a Playwright configuration file and a README.
- **FR-4.3.2** **Download project** produces a .zip of a runnable TypeScript Playwright project. The project reads the application's login from environment settings rather than containing it.
- **FR-4.3.3** The tab appears only once at least one test exists, and never for viewers.

#### 4.4 Author a test case in plain English
- **FR-4.4.1** In the "Author a test case" panel on Test cases, the user picks an existing journey or names a new one, then describes in plain language what to do and what to check.
- **FR-4.4.2** A live AI agent explores the running application, with no prior Discovery needed, then writes the test, checks it by running it and adds it to the list. Progress reads "Exploring the live application…" and then "Generating the test case…".
- **FR-4.4.3** Any steps it could not perform are listed under "Not generated — Vantage couldn't do these in the application".
- **FR-4.4.4** This works for applications with or without Discovery.

#### 4.5 Test case library & source filters
- **FR-4.5.1** Test cases has a paginated list of every test case. Each row shows a number, a name, a journey and a source badge: From discovery, Authored by prompt or Recorded.
- **FR-4.5.2** Filter chips with counts (All, Author test cases, Record-and-play test cases) and a search by number, name or journey narrow the list.
- **FR-4.5.3** Expanding a row offers **View code**, which shows the test's code, and **Test data**, an inline form. Saving the form updates that one test to match.
- **FR-4.5.4** Scenario-type badges (happy path, negative, edge case) are hidden on request.

### Epic 5 — Record and Play

#### 5.1 Record a test in a remote browser
- **FR-5.1.1** On the Record and play tab, the user enters a flow name and picks a mode:
  - **Record a login flow** starts logged out, so the login becomes part of the test.
  - **Record an authenticated flow** starts already signed in as the application's saved user.
- **FR-5.1.2** **Record a flow** opens a separate browser tab streaming a real remote browser, and the user clicks through the flow there.
  - A warning says "Anything you type — including passwords — is recorded into the generated test."
  - If the browser blocks the pop-up, a link opens it manually. Dropped connections reconnect.
- **FR-5.1.3** A recording link expires after 30 minutes. A recording can last up to 60 minutes. A limited number of recordings can run at once.

#### 5.2 Save, cancel and replay recorded tests
- **FR-5.2.1** **Stop and Save** turns the recording into a Playwright test. Vantage then moves to Test cases and highlights the new row. **Discard** throws the recording away. A failed save offers Try again.
- **FR-5.2.2** Recorded tests are tidied up and type-checked. They then run, self-heal and report exactly like generated ones.

### Epic 6 — Test Execution & Reporting

#### 6.1 Run tests: all or a named selective run
- **FR-6.1.1** **Run tests** offers two options:
  - **All test cases.**
  - **Selective run**: a required Run Name and a searchable journey list with Select all and Clear. Each journey can be expanded to pick individual test cases.
- **FR-6.1.2** Every run gets its own Run number. Manual runs can overlap. Within a run, tests run 5 at a time, except that a run containing any test from an application that keeps progress per login (saved drafts, a cart, "resume where you left off") runs **all** its tests one at a time. Explorer marks such tests when it hands them on, based on a keyword guess from screen names and descriptions.
- **FR-6.1.3** The runs list has summary tiles: latest pass rate, average pass rate, median duration and open failures. Each row shows the run number, who or what triggered it, the date, duration, results and pass rate. The list uses Prev and Next buttons.
- **FR-6.1.4** A run's detail page shows:
  - a status pill,
  - a "Results by journey" chart,
  - results grouped as Passed, Self-healed, Flaky and Failed,
  - a row for each test case with its status. A test deliberately skipped in its code (for example one recording a known bug) shows as **Skipped** with its reason ("Known bug — should: … The app currently: …"), not as errored. This applies to every test, not only Explorer's.
- **FR-6.1.5** A check every 15 minutes automatically closes out any run that has been stuck for more than 6 hours.

#### 6.2 Cancel a run
- **FR-6.2.1** **Cancel run** stops the running tests, marks unfinished ones as cancelled and keeps the finished results. No report and no email are produced for a cancelled run.

#### 6.3 Self-healing of failing tests
- **FR-6.3.1** After a failure, Vantage tries to heal the test automatically, up to 2 attempts. A **Retry** chip lets a user heal it again, up to the admin's "maximum self-heal attempts" (3 by default). Operations can turn automatic healing off with a server setting (it is on by default); the manual Retry works either way.
- **FR-6.3.2** Each attempt runs the same steps:
  - The AI diagnoses the failure from the error, the console and a screenshot.
  - For locator problems, it may look at the live page.
  - It makes a targeted fix, checks it compiles and runs the test again.
  - It stops early if the same failure repeats.
- **FR-6.3.3** A failed assertion is never healed, and any fix that changes an assertion is rejected. A failure caused by the environment or infrastructure gets one plain re-run with no AI. A test that records a known bug is never healed, because healing would rewrite away the bug it records.
- **FR-6.3.4** Rows show chips for the outcome:
  - **Self-healed**: "Failed on first run — automatically remediated by self-healing".
  - **Heal exhausted**: no attempts left.
  - A pulsing "Self-healing" status while a heal is in progress.

#### 6.4 Flaky test flags
- **FR-6.4.1** A test is marked **Flaky**, with the tooltip "Inconsistent results across this test", when its last 10 finished results, this run included, contain at least one pass and at least one failure.
  - Cancelled runs and internal check runs don't count.
  - A test is never flaky on its first run.

#### 6.5 Failure explanations & evidence
- **FR-6.5.1** Each failed test has a **Summary** tab with a plain-language explanation and a **Raw error** tab.
  - Known errors are explained by fixed rules.
  - Unknown ones are explained by AI, labelled "Explained by AI — may not be exact", and the explanation is reused for the same error.
- **FR-6.5.2** Failed tests include a screenshot and a Playwright trace. Which screenshots are kept follows the Screenshot capture setting.
- **FR-6.5.3** When most failures in a run share one cause, such as sign-in failing, a banner for the whole run names it.

#### 6.6 HTML test report
- **FR-6.6.1** **View report** opens a Vantage-branded HTML report built on Allure, at a stable link for each run.
- **FR-6.6.2** Viewers can't open it. Very large runs don't get a report.

#### 6.7 Run-completed email
- **FR-6.7.1** When a run completes, the person who started it gets an email. For a scheduled run, including "Run now", it goes to the person who created the schedule.
- **FR-6.7.2** The email shows the pass or fail outcome, up to 10 failures, a "View report" link and an "Open in Vantage" link that opens the run after sign-in.
- **FR-6.7.3** The email is sent at most once per run. It is not sent for cancelled runs, or for runs closed out automatically.

#### 6.8 Scheduled test runs
- **FR-6.8.1** The Schedules tab lists each schedule's name, cadence, next run and an Enabled toggle. A ⋮ menu offers Run now, Edit and Delete.
- **FR-6.8.2** A schedule's cadence can be:
  - **Daily**, at a time chosen in 15-minute steps.
  - **Weekly**, on chosen days at a time chosen in 15-minute steps.
  - **Monthly**, on day 1 to 28 at a time chosen in 15-minute steps.
  - **Custom**, a 5-part cron expression in the server's time zone.
- **FR-6.8.3** Schedules run **tests only**. The dialog text "Run discovery or test cases automatically on a cadence" overstates this and needs correcting.
- **FR-6.8.4** If a run is already in progress for the application, a scheduled run is skipped, not queued, and "Run now" shows "already in progress".

### Epic 7 — Workspace Administration

#### 7.1 Team members, roles & invites
- **FR-7.1.1** The Team members page, for admins only, lists each member's name, email, role, and last active time or "Never signed in". A ⋮ menu offers Change role and Remove.
- **FR-7.1.2** **Invite member** takes one email address and a role (Member, Admin or Viewer), and sends an email invitation. **Partly built:** revoking a pending invite works on the server, but pending invites are not listed on any screen.
- **FR-7.1.3** Invites expire after **72 hours**. The screen's "Invitation expires in 7 days" text is wrong and needs correcting.
- **FR-7.1.4** If email isn't configured, the invite link is written to the server log so an operator can pass it on.

#### 7.2 Settings
- **FR-7.2.1** Admins set these limits:
  - Discovery: maximum discovery time, maximum pages, maximum journeys, navigation timeout, interaction level (Passive, Normal or Aggressive).
  - Generation: maximum scenarios per journey, maximum test cases per application.
  - Healing: maximum self-heal attempts.
- **FR-7.2.2** **Screenshot capture** keeps screenshots for failed test cases (the default), for passed ones, or for all.
- **FR-7.2.3** **Auto-clean up removed projects** is always on. The admin chooses when deleted applications are purged: after 1 day, 1 week or 1 month (the default).
- **FR-7.2.4** **Saved credentials** lists applications that use a username and password, and applications with no login (shown as "No login"). An admin can reveal a password, which is logged in Activity, or add or rotate a username and password. Credentials saved here are not re-checked.
- **FR-7.2.5** Settings apply across the whole deployment.
- **FR-7.2.6** A **Sign-in** column in Saved credentials has an on/off switch per application, for admins only and only for username-and-password or no-login applications. **Off** means the application has no login: its saved login is cleared, and Discovery, Explorer and test runs open it directly. **On** cannot be set from the switch alone; saving a username and password with "Add credentials" turns sign-in back on.

#### 7.3 Activity history
- **FR-7.3.1** The Activity page, for admins only, is a timeline for the whole organization with Time, Event, By and Result columns. It covers:
  - Discovery runs and test runs, each as one row that updates as it progresses,
  - scenario and test case generation,
  - changes to settings, credentials, the team, applications and schedules.
- **FR-7.3.2** The list can be filtered by:
  - type: Discovery, Scenarios, Test cases, Test runs, or Settings & team,
  - application,
  - result,
  - time range: 24 hours, 7, 30 or 90 days.
  It can also be searched and sorted newest or oldest first.
- **FR-7.3.3** A detail drawer shows:
  - what happened, why something could not run and a suggested next step,
  - before and after values for settings changes, with credentials never shown,
  - for failed tests, the screenshot, trace, exact error and error log.
  **Open application** jumps to the related tab or run.
- **FR-7.3.4** Activity history is kept for 90 days, then deleted automatically.
- **FR-7.3.5** **Gap:** Explorer actions (starting, pausing or stopping a run, confirming the App Summary, answering questions, judging possible bugs, changing knowledge or other user types) are not recorded in Activity. An Explorer application's progress shows only through its single Discovery row.

### Epic 8 — Explorer Discovery

Explorer is the default discovery engine. It learns an application the way a new QA engineer would, has a person confirm what it learned, asks when it is unsure, and writes and proves scenarios. It does not treat the application as the source of truth: it judges what it sees against common sense, the user's answers and any documents the user uploads, and it never confirms or answers anything on the user's behalf.

#### 8.1 Start Explorer and watch it live
- **FR-8.1.1** Adding an application with Autonomous discovery on starts Explorer. This is the only place discovery starts automatically. If Explorer's background service is not running at that moment, the application's discovery is marked failed ("worker unavailable") and the user can start Explorer later from the Explorer tab. Operations can switch new applications back to classic discovery with a server setting; no user can change this.
- **FR-8.1.2** Before the first run, or after **New run**, the Explorer tab shows a start card explaining what Explorer does, with an **"Other kinds of users"** panel where the user adds a user type with its username and password. **Start exploring** begins a run. Only one run can be active per application.
- **FR-8.1.3** The tab header shows the application name and a one-line status of what Explorer is doing ("Reading the Quotes screen"), a **Questions** button with a count, and the run controls.
- **FR-8.1.4** **Pause** and **Stop** are offered while a run is going. **Resume** continues a paused, stopped or failed run from the step it reached, without redoing finished work; otherwise **New run** is offered. The application's discovery status follows the run: running, paused, failed ("Explorer was stopped before it finished"), and complete after the hand-off.
- **FR-8.1.5** The **Live** sub-tab (the default) shows:
  - a pulsing **"Waiting for you"** box when Explorer needs the user: either a request to check and confirm the App Summary (**Check the summary**) or the first open blocking question (**Answer now**);
  - a live frame with the latest screenshot and a trail of the last 6 screenshots, any of which can be pinned;
  - an Activity log of the last 80 things Explorer did or thought;
  - a Progress panel with four stages (Learning the app, Your check, Trying every path, Writing scenarios) and the missions list, where each mission can be **Skipped**.
- **FR-8.1.6** Explorer never deletes data, moves money, makes a business decision or signs out on its own, in any environment; it asks first. It presses a final Save, Submit or Create by itself only when the application is marked as a non-production environment, and never presses Send twice.
- **FR-8.1.7** **Gap:** viewers can't change anything in Explorer, but members (not just admins) can manage its other user types and knowledge, viewers can download its tests, run report, recordings and highlight video, and no Explorer action is recorded in Activity.

#### 8.2 Review and confirm the App Summary
- **FR-8.2.1** After a first pass through the application, Explorer writes an **App Summary**: the application name, a one-liner, key tasks, questions for the user with answer options, an optional "Goal for this run" and screens to leave out. It then stops and waits for a person.
- **FR-8.2.2** On the **What it learned** sub-tab, while the summary is waiting, the user can **Edit**, **Save changes** and **"Looks right — confirm"**. Confirm stays disabled until every question in the summary is answered. Answers given there become knowledge for the application.
- **FR-8.2.3** The person who started the run gets an email when the summary is ready. Without mail settings on the server, nothing is sent.
- **FR-8.2.4** If the summary is not confirmed within 14 days, the run expires and cannot be resumed. A banner explains this, and **Start a new run** begins from what was already learned, keeping the user's answers.

#### 8.3 Answer Explorer's questions
- **FR-8.3.1** Explorer asks **blocking questions** when it needs something to continue (such as test data), before a risky action ("May I press Send?") or to clarify something. Only the mission that asked waits, for 10 minutes by default, and then carries on without the answer; everything else keeps running.
- **FR-8.3.2** **"Is this a bug?"** questions never block. They do not count as "Waiting for you" and sit with the finding they are about.
- **FR-8.3.3** The **Questions** header button opens a "Questions for you" panel. It pulses when Explorer is waiting on the user. The person who started the run is emailed when a blocking question is asked.
- **FR-8.3.4** Every answer becomes trusted knowledge for that application, for this run and later ones. Explorer checks what it already knows before asking, so the same question is not asked twice, and similar open questions are merged.
- **FR-8.3.5** A **Knowledge** panel on What it learned lets the user add a fact or test data, upload a document (PDF, Word, plain text, Markdown or CSV, up to 15 MB) or forget an item. Knowledge belongs to the application and carries over to every later run.

#### 8.4 Missions, screens and findings
- **FR-8.4.1** After the summary is confirmed, Explorer plans up to 15 missions (goals such as "file a claim" or "try a branch") and works through up to 3 at a time.
- **FR-8.4.2** Explorer names each screen by what it means, so many records of the same kind count as one screen. It also hunts for screens that only appear sometimes: it tries each option in dropdowns and radio groups, tries small and large amounts, and fakes empty or failing server replies inside its own browser.
- **FR-8.4.3** The **Screens** sub-tab is a searchable, paged screenshot grid. Choosing a screen shows its actions and where each one leads. There is no map view.
- **FR-8.4.4** Along the way Explorer notes health problems: broken screens, server errors, broken links, slow pages, wording mistakes and things that "look wrong". They appear, folded, as **"Things that look wrong"** on What it learned, each with a thumbnail, a way to mark it a false alarm and its "is this a bug?" question, plus **Download CSV**.
- **FR-8.4.5** **Partly built.** Explorer also works out which screens each extra user type can reach, finds pages nothing links to, measures how much of the application it exercised and computes an application health score. These, adding your own mission and per-mission screen recordings are stored but have no screen.

#### 8.5 Proven scenarios and hand-off to test cases
- **FR-8.5.1** Explorer writes scenarios in seven kinds: five it plans with AI (Getting around, Input rules, Error handling, Data shown, Saving a form) plus **Whole journey** (an end-to-end business flow from a completed mission, up to 8, built first) and **Page quality** (browser-measured checks on each screen, skipped for applications that keep progress per login). A run makes up to 150 scenarios, scaled to the application's size.
- **FR-8.5.2** Each scenario is proven: it must replay the same way every time and fail when its key step is removed on purpose. Each is marked as working as it should (proven), a **possible bug**, or dropped with a reason (hidden). Each records where "what should happen" came from: the user or their documents, common sense, or the application itself.
- **FR-8.5.3** The **Scenarios** sub-tab shows counts (work as they should, possible bugs to check, still being tried, from what you told Explorer), kind filter chips, and groups with whole journeys first and then one group per screen. Each scenario can open a **proof video**. A possible bug offers **"Not a bug, keep as a test"** or **Ignore**.
- **FR-8.5.4** When a run finishes testing, only proven scenarios are handed on: each screen tested becomes a journey with its screenshot as the step, and each whole-journey scenario becomes its own journey. Possible bugs are never handed on; one marked "Not a bug" is handed on by itself, and "Ignore" leaves it out. Running Explorer again replaces its own earlier results, while older records stay for run history.
- **FR-8.5.5** A pulsing **Generate tests** button appears once the run has finished testing and at least one scenario works. It uses the same generation as Epic 4 (FR-4.2.4).
- **FR-8.5.6** **Partly built.** A shareable highlight video, the run report and its download, downloading Explorer's proven tests as a ready-to-run project, and re-writing the scenarios without exploring again are built behind the scenes with no screen.
- **FR-8.5.7** **Unconfirmed.** On an application first discovered by classic discovery, starting Explorer retires only Explorer's own earlier journeys, so Generate tests may cover both the classic journeys and Explorer's.

## 5. Non-Functional Requirements

- **Security and privacy.**
  - Logins for applications under test are stored encrypted in a dedicated secrets store. They are handed to a test only while it runs and never shown back, except through the logged admin reveal.
  - Accounts are invite-only, and every organization's data is kept separate.
  - The server enforces roles; hiding controls on screen is only a convenience. **Gap:** Explorer refuses viewers' changes, but lets members (not just admins) store other user types' passwords and change knowledge, and lets viewers download its results.
  - Reset and invite links are single-use and short-lived.
- **Reliability.**
  - Discovery recovers by itself from a service restart, and failing pages are retried a bounded number of times. An Explorer run whose step stops responding is marked failed and can be resumed from where it reached.
  - Stuck test runs are closed out automatically.
  - A scheduled run never piles up behind one already running.
  - The run email is sent at most once.
- **Honesty of results.**
  - Self-healing cannot weaken a test's assertions.
  - AI-written explanations are labelled as such.
  - Discovery never starts on an unproven login.
  - Explorer never hands on a scenario it has not proven, and keeps behaviour that looks wrong as a possible bug for a person to judge.
- **Performance and limits.**
  - Within a run, tests run 5 at a time, or one at a time for applications that keep progress per login.
  - Explorer runs up to 3 missions or scenario checks at a time, at most 15 missions and 150 scenarios per run.
  - Discovery is bounded by the admin limits for time, pages and journeys, plus per-page sampling.
  - Recording sessions are capped in number and length.
- **Data retention.**
  - Deleted applications are purged after the admin-chosen period.
  - Activity history is kept for 90 days.
  - Which test screenshots are kept follows the Screenshot capture setting.
  - Explorer's screenshots and videos are kept in the main database, not in cloud file storage, and have no retention limit.
- **Usability.**
  - Plain language throughout: progress stages, error messages and failure summaries.
  - Every in-progress state shows the label followed by bouncing dots. (The Explorer tab still uses ring spinners in a few places.)
  - Anything Explorer is waiting on the user for pulses so it is not missed.
  - Placeholders tell the user what to enter, not made-up examples.
  - Light mode only.
- **Availability feedback.** When a needed background service is down, the user is told so plainly. The app shows a Retry screen when the server can't be reached.

## 6. End-to-End User Flow

1. An admin, the first one set up by the operator, invites teammates with roles. Invitees accept by email and set a password.
2. A user signs in and lands on **Overview**.
3. **Add application**:
   1. Enter the name, environment and URL, then run Test connection.
   2. Turn on sign-in and enter the login, if the application needs one.
   3. Choose whether to run Autonomous discovery.
4. **With Discovery on (Explorer, the default):**
   1. The login is proven in a real browser, then Explorer starts and the application opens on the Explorer tab.
   2. The user watches Live, then checks the App Summary on What it learned, answers its questions and confirms it.
   3. Explorer works through its missions and asks blocking questions, which the user answers from the Questions panel.
   4. On Explorer's Scenarios sub-tab the user watches proof videos, judges possible bugs, then presses **Generate tests**.
5. **With classic discovery** (applications discovered before Explorer, or with Explorer switched off):
   1. The login is proven in a real browser, then Discovery starts.
   2. Journeys fill in live; Discovery can be paused or resumed. The user renames or deletes journeys, then clicks **Review scenarios**.
   3. The user renames or deletes scenarios and fills or auto-generates test data, then clicks **Generate test cases**.
   4. Generation progress is tracked per journey and can be terminated or retried. The progress screen ends with Run and Download options.
6. **With Discovery off:** the user goes straight to Test cases and adds tests with **Author a test case** or **Record and play**.
7. **Run tests**, all or selectively. Failures are healed automatically within limits. The user then:
   - reviews flaky flags and failure explanations, with screenshots and traces,
   - retries with self-healing where needed,
   - opens the report.
   The run-completed email arrives.
8. **Schedule** runs: daily, weekly, monthly or custom.
9. **Download the project** to run the tests outside Vantage.
10. Admins watch **Activity**, adjust **Settings** and manage **Team members**. Overview and the Applications list show health across applications.

## 7. Not Built / Deferred

| Item | State |
|---|---|
| Delivery into a customer's CI/CD pipeline or repository | Not built |
| Bring-your-own or on-premise AI model; on-premise deployment | Not built |
| Business capability map, risk or confidence scorecard, change-impact analysis | Not built |
| Reading source code to inform Discovery | Not built |
| Scheduling Discovery | Not built (only test runs can be scheduled) |
| Single sign-on session reuse and MFA codes for the application under test | Works on the server only, no screen |
| API-key and OAuth sign-in for the application under test | Not built |
| Answering classic Discovery's "I need data to continue" requests, and resuming from a blocked point | Built on the server, not connected to any screen (Explorer asks and takes answers) |
| Explorer: adding your own mission | Built behind the scenes, no screen |
| Explorer: per-mission screen recordings and the shareable highlight video | Built behind the scenes, no screen |
| Explorer: run report and its download | Built behind the scenes, no screen |
| Explorer: downloading its proven tests as a ready-to-run project | Built behind the scenes, no screen |
| Explorer: re-writing scenarios without exploring again ("Regenerate") | Built behind the scenes, no screen |
| Explorer: other user types' access, unlinked pages, how much of the app was exercised, app health score | Computed and stored, no screen |
| Admin-only Explorer user types and knowledge, viewer-refused Explorer downloads, and Activity entries for Explorer actions | Not built |
| Choosing the discovery engine from the screens | Not built (a server setting only operations can change) |
| Classic discovery coverage report and diagnostics screen | Not built (the server produces the report) |
| Test data pool screen | Not built |
| AI-assisted safety classification during Discovery | Built, switched off |
| Blocking destructive actions during test runs | Removed so that "Run tests" needs no setup |
| Regenerating a journey's scenarios from scratch | Removed from scope |
| Per-application browser tab branding | Superseded; the tab always shows "Vantage" |
| Scenario-type badges (happy, negative, edge) | Hidden on request |
| Merging, splitting or editing journeys; marking business importance | Not built |
| Mobile and native applications; frameworks other than Playwright | Out of scope |
| Dark mode | Dropped |

## 8. Success Metrics

No numeric coverage or time-saved target is set yet. Thresholds should come from real usage data.

- **SM-1.** Teams keep using Vantage into a second and third release cycle without being pushed to.
- **SM-2.** Discovered journeys need light correction (renames, a few deletions) rather than heavy rework.
- **SM-3.** Teams trust generated, authored and recorded tests enough to put them into their real regression process, scheduled and run regularly.
- **SM-4.** A meaningful share of failures is either healed or explained in a way a user can act on, and flaky tests are visible rather than ignored.
- **Counter-metric.** Healed-test counts must never be raised by loosening assertions. The product prevents this by design.

## 9. Open Questions

1. How long does Discovery take on a typical enterprise application? This needs measuring across real customers before it is quoted externally.
2. Should Vantage technically prevent Discovery against a production environment? Today that is the customer's responsibility, softened by the safety rules.
3. When should the server-only capabilities get screens: single sign-on session reuse, MFA, the test data pool, blocked-request answers and the coverage report?
4. Should Discovery be schedulable, as the schedule dialog's wording suggests?
5. What usage evidence counts as "proven" before the next phase of work (connecting journeys to code, change impact) is started?
6. Which Explorer features built behind the scenes (own missions, recordings, highlight video, report, tests download, regenerate) should get screens, and which should be dropped?
7. Should Explorer's user types and knowledge be admin only, should its downloads be refused to viewers, and should its actions appear in Activity?

## 10. Risks and Mitigations

1. **Discovery side effects.** Discovery could trigger real side effects if pointed at a production environment.
   - *Mitigation:* clearly destructive actions are never taken, and ambiguous ones follow the application's safety setting.
   - *Residual:* where Discovery runs is not verified.
2. **Wrong or fragmented journeys.** AI may misjudge or over-split journeys.
   - *Mitigation:* journeys can be renamed and deleted, and deletion removes their downstream tests from counts.
   - *Residual:* generation work may already have been spent on them.
3. **Healing hides real bugs.**
   - *Mitigation:* assertions are protected, and failed assertions are never healed.
4. **Single-instance operation.** Each service currently runs as a single instance. The background job engine keeps its history in memory, so a restart can lose in-flight history and may require schedules to be recreated.
   - *Mitigation:* stuck runs are closed out automatically. Production-grade persistence is still to be added.
5. **Production hardening gaps.**
   - The sign-in page's development shortcut, which fills in a test login when the "Welcome back" heading is clicked, is enabled in production. It fills the form only and does not bypass sign-in.
   - Secure-cookie and certificate settings in the hosted environment need tightening.
6. **Explorer cannot be deployed yet.** Explorer is the default, but its background service has no deployment setup. In a deployed environment, adding an application with Discovery on would mark discovery failed.
   - *Mitigation:* ship the Explorer service, or have operations switch new applications back to classic discovery until it is shipped.
7. **Explorer's role rules are looser than the rest of the product.** Viewers can't change anything there, but any member can store other user types' passwords and change knowledge, and viewers can download Explorer's tests, run report, recordings and highlight video. None of Explorer's actions appear in Activity.
   - *Mitigation:* none yet.
8. **Explorer media in the main database.** Explorer keeps its screenshots and videos (1 to 6 MB per mission) in the main database, which will grow quickly.
   - *Mitigation:* none yet; moving them to cloud file storage is the planned path.
9. **Starting Explorer on a classic application is one-way.** Its Journeys and Scenarios pages disappear and the classic Pause and Resume are refused for good, although the start card says "Your current Journeys are not affected". Generate tests may then cover both sets of journeys (unconfirmed).
10. **Guessed one-at-a-time runs.** Whether an application keeps progress per login is a keyword guess. A wrong guess either slows runs or lets parallel tests interfere with shared state.
11. **Commoditization.** Free framework agents (see `addendum.md`) make "explore and generate tests" table stakes.
   - *Mitigation:* compete on the complete, trustworthy loop rather than on generation alone.

## 11. Integrations and Dependencies

- **AI provider.** A hosted AI model, reached through the operator's AI gateway, is used for journey inference, scenario writing, test writing and repair, plain-English authoring and explaining unknown errors. Explorer uses its own connection to the same gateway, with a "thinking" model for understanding screens and writing the summary and a faster one for quick choices; operations choose both.
- **Email.** An outgoing mail service sends invites, password resets, run-completed emails, and Explorer's "summary ready" and "question waiting" emails.
- **Cloud file storage.** Holds screenshots, traces and reports.
- **Secrets store.** Holds the logins for applications under test.
