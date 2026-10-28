---
name: Vantage (AITestGen)
status: final
updated: 2026-10-27
---

# Vantage — Experience Spine

This document covers the experience as it ships today: screens, navigation, flows, roles, states and copy rules. `DESIGN.md` is the visual reference and wins on any visual question.

## Foundation

- **Platform.** Vantage is a desktop web app for QA and engineering teams. It turns a deployed web application into a maintained Playwright test suite, written in TypeScript, with very little hand-writing of tests. There is no mobile or tablet layout.
- **Accounts.** Accounts are invite-only and scoped to one organization; nobody can sign themselves up. Everything a user sees belongs to their organization.
- **Main objects:**
  - Application: the app under test.
  - Journey: a real user flow that Vantage discovered.
  - Scenario: a test idea for a journey, with its steps, test data and expected result.
  - Test case: a runnable Playwright test.
  - Test run: one execution of some or all test cases, with its results.
- **Three ways to get test cases:**
  - Autonomous Discovery, then scenarios, then generated tests. Discovery has two engines: **Explorer**, the default, which writes and proves scenarios itself; and **classic discovery**, which finds journeys for the user to turn into scenarios. Classic discovery now runs only for applications discovered before Explorer became the default, or when operations switch Explorer off.
  - **Author a test case** in plain English.
  - **Record and play** in a remote browser.
- **Accessibility.** WCAG 2.1 AA is the floor. Every interactive element shows a visible teal focus ring, tab order follows visual order, and form controls are keyboard-operable.

## Roles and what each one sees

There are three roles. The server enforces them, and the interface hides controls a role cannot use.

| Capability | Admin | Member | Viewer |
|---|---|---|---|
| See every application, journey, scenario, test case, run and result | yes | yes | yes |
| Add an application; start, pause or resume Discovery | yes | yes | no |
| Explorer tab: start, pause, stop, resume, confirm the summary, answer questions, judge bugs | yes | yes | no (buttons shown, but refused) |
| Explorer tab: knowledge and other user types | yes | yes (gap: should be admin only) | no (buttons shown, but refused) |
| Download Explorer's tests, report, recordings and highlight video (no screen yet) | yes | yes | yes (gap) |
| Rename or delete an application (⋮ on the Applications list) | yes | no | no |
| Rename/delete journeys and scenarios, edit test data, generate scenarios and test cases | yes | yes | no |
| Author a test case; Record and play | yes | yes | no (Record and play tab hidden) |
| Run tests, cancel a run, retry a failure with self-healing | yes | yes | no |
| Manage schedules | yes | yes | no |
| Open a run's HTML report | yes | yes | no ("Reports aren't available for view-only access") |
| Download the project | yes | yes | no (tab hidden) |
| Team members, Activity | yes | no | no |
| Settings, including each application's Sign-in switch | yes | sees the link, gets "Access denied" | link hidden |

Rules:
- A viewer cannot change anything, Explorer included. On the Explorer tab the buttons are not hidden from viewers; the platform refuses them instead.
- Admins cannot remove themselves or change their own role, and the last admin cannot be demoted.
- A role change applies on the user's next action.

The invite dialog describes the roles like this:
- **Member:** "Can onboard applications, review scenarios and trigger runs."
- **Admin:** "Everything a member can do, plus saved credentials and discovery limits."
- **Viewer:** "Can view applications, test cases and run results — no changes."

## Information Architecture

### Before sign-in
- **Sign in.** A split screen. The left side is a marketing image panel. The right side is the sign-in card ("Welcome back — Sign in to your Vantage account"), with a "Forgot password?" link and "An initiative of Omnewave".
- **Forgot / reset password.**
  - The screen always says "Check your email", whether or not the address has an account.
  - The reset link lasts 1 hour.
  - A new password needs at least 8 characters and must be entered twice.
- **Accept invite ("Set up your account").**
  - The invitee enters a full name and a password, and is signed in straight away.
  - An invalid, expired or already-used link shows one generic error.
- **Service unavailable.** If the backend cannot be reached, this screen replaces sign-in, with a Retry button.

### After sign-in: the shell
The shell has a **left sidebar** and a top bar. The top bar holds a breadcrumb, an "Add application" button (a "View only" badge for viewers) and an account menu with Log out. There is **no step-by-step wizard**: every area is a sidebar destination and can be opened in any order.

Sidebar, when no application is open:
- **Overview**, the organization-wide dashboard and the landing page after sign-in.
- **Applications**, with a count badge.
- **Add application** (hidden for viewers).
- **Configuration** group (hidden for viewers):
  - **Team members** (admin only)
  - **Activity** (admin only)
  - **Settings**

When an application is open, the sidebar switches to an **Application** section. It shows the app's name, an Exit link and these tabs, in order:

**Overview · Journeys · Explorer · Scenarios · Test cases · Test runs · Record and play · Schedules · Download project**

- Journeys, Explorer (compass icon) and Scenarios appear only if the application was added with Autonomous discovery turned on.
- For an application **Explorer has discovered**, Journeys and Scenarios are hidden; Explorer's own Scenarios sub-tab replaces them, and any link to them opens Explorer. Classic applications keep Journeys and Scenarios and also get Explorer. Once someone starts Explorer on a classic application, it counts as an Explorer application from then on.
- Record and play and Download project are hidden for viewers. Overview and Download project are always listed; until there is something to show they display an empty state ("No test runs yet", "No test cases generated yet").
- Opening an application from the list lands on the most useful tab:
  - **Test cases** while tests are first being generated, or for an app without Discovery.
  - **Overview** once a test suite exists.
  - Otherwise **Explorer** for an Explorer application, or **Scenarios** or **Journeys** for a classic one.
- Right after an application is added with Discovery on, it opens on **Explorer**.

## Screens

**Overview (organization dashboard)**
- Headline numbers: applications tested, test cases generated, pass rate, failure rate, average run duration, self-healed locators and last discovery. Some are marked "in the last 7 days".
- Charts: Pass rate over time, Latest run outcome and Test cases per application.
- An **Active pipelines** list shows what is running right now: discovery in progress, generating test cases, authoring from a prompt, or a run in progress. Each item opens its application.

**Applications**
- A paginated table with these columns: Application, Journeys, Tests, Pass rate, Last activity, Status.
- Status shows one of:
  - the Discovery or generation stage
  - "Ready to run"
  - "Running"
  - after the first completed run, a health tier: Healthy, Needs Attention or Critical
- Hovering coverage shows the "% of journeys covered by scenarios".
- **Admins** have a ⋮ menu with two items:
  - **Rename** works inline.
  - **Delete** asks for confirmation. It is blocked, with the reason shown, while Discovery, generation or a run is in progress.
- A deleted application disappears at once. Its data is purged after the retention period set in Settings.

**Add application**
- Fields:
  - Application name
  - Environment: staging, production, qa, or "other" with a custom name
  - URL, with a **Test connection** button
  - A toggle, **"This application requires sign-in"**. When it is on, the form asks for an optional login URL, a username and a password or token, with a note that credentials are stored encrypted and used only during discovery and runs.
  - An **Autonomous discovery** checkbox, on by default.
- The URL must pass Test connection before the form will submit; clicking submit too early shows a reminder.
- If Discovery is on and the app needs sign-in, Vantage first **signs in for real** to check the credentials:
  - Wrong credentials show "The username or password is incorrect…".
  - An unconfirmed result shows "We couldn't confirm these credentials…".
  - Discovery never starts on a login that hasn't been proven to work.
- The submit button reads "Start discovery" or "Add application", depending on the checkbox. With discovery on, the new application is discovered by Explorer. If Explorer's service is not running, the application's discovery shows as failed and Explorer can be started later from its tab.
- After submit, the page becomes a read-only "Connected application" summary. The password is never shown again.

**Explorer**
- **Header:** the application name, a one-line status of what Explorer is doing ("Reading the Quotes screen"), and these buttons:
  - **Questions**, with a count. It pulses when Explorer is waiting on the user and opens the "Questions for you" panel.
  - **Pause** and **Stop** while a run is going.
  - **Resume** for a paused, stopped or failed run; it carries on from the step it reached.
  - **New run** otherwise.
- **Start card** (before the first run, or after New run): explains what Explorer does, with an **"Other kinds of users"** panel to add a user type with its username and password, then **Start exploring**. Only one run can be active per application.
- Four sub-tabs on a segmented bar:
  - **Live** (the default):
    - a pulsing **"Waiting for you"** box: either "Explorer has learned the app. Check its summary and confirm…" with **Check the summary**, or the first open blocking question with **Answer now**;
    - a live frame with the latest screenshot and a trail of the last 6, any of which can be pinned;
    - an Activity log of the last 80 things Explorer did or thought;
    - a Progress panel with four stages (Learning the app → Your check → Trying every path → Writing scenarios) and a missions list (first 3, then "show all"), each with **Skip**.
  - **What it learned:**
    - The **App Summary**: app name, one-liner, key tasks, questions for the user with answer options, an optional "Goal for this run" and screens to leave out. While it is waiting, the user can **Edit**, **Save changes** and **"Looks right — confirm"**. Confirm is disabled until every question is answered.
    - A **Knowledge** panel: add a fact or test data, upload a document (PDF, Word, text, Markdown or CSV, up to 15 MB), or forget an item. Knowledge belongs to the application and carries over to later runs.
    - Last and folded: **"Things that look wrong"**, each with a thumbnail, a false-alarm action and its "is this a bug?" question, plus **Download CSV**.
  - **Screens:** a searchable, paged screenshot grid. Choosing a screen shows its actions and where each leads. There is no map view.
  - **Scenarios:**
    - Counts: "work as they should", "possible bugs to check", "still being tried" and "from what you told Explorer".
    - Kind filter chips. Groups show whole journeys first, then one group per screen.
    - Each scenario can open a **proof video**.
    - A possible bug offers **"Not a bug, keep as a test"** or **Ignore**.
    - A pulsing **Generate tests** button appears once the run has finished testing and at least one scenario works.
- **Questions for you** panel: blocking questions ("I need this to continue", "May I press Send?", clarifications) and their answer controls. Only the mission that asked waits, for 10 minutes by default. "Is this a bug?" questions never block and sit with their finding. Every answer becomes knowledge for the application, so the same question is not asked twice. The person who started the run is emailed when the summary is ready and when a blocking question is asked.
- **Expired run:** if the App Summary is not confirmed within 14 days, a banner says the run is over and cannot be resumed. **Start a new run** begins from what was already learned and keeps the user's answers.
- Explorer never deletes data, moves money, makes a business decision or signs out on its own; it asks first.
- Not on any screen yet: adding your own mission, per-mission recordings, the highlight video, the run report, downloading Explorer's tests, and re-writing scenarios without exploring again.

**Journeys (Discover Journeys)**
- *Classic discovery only.* For an Explorer application this page (hidden from the sidebar) shows **Open Explorer** and "Explorer is finding this app's journeys. They appear here when it has finished.", with no Pause or Resume.
- While Discovery runs, a progress view walks through four stages: Exploring pages, Capturing screenshots, Grouping flows and Mapping journeys. It notes "Discovery runs in the background — this list updates automatically".
- **Pause Discovery** and **Resume Discovery** buttons are available. Resuming continues from where it stopped. For an application that has ever had an Explorer run they are refused with "Explorer discovers this application: pause or resume it from the Explorer tab."
- Banners cover these situations:
  - the session expired mid-discovery
  - the run failed
  - Discovery is paused
  - Discovery recovered after a restart and is resuming
- Each discovered journey is a card with a screenshot (click to enlarge) and its page-by-page steps. Repeated steps on one page are merged into one business step.
- Users can search journeys, rename them and delete them.
- **Review scenarios** starts scenario writing and moves to Scenarios.

**Scenarios (Review Scenarios)**
- Scenarios are grouped by journey. While they are being written, progress shows Reading journeys, Drafting scenarios and Deriving test data.
- Each scenario shows its test steps, its test data fields and its expected result. Each field is marked "Required for this scenario" or "Optional — auto-filled if left blank".
- Users can rename or delete a scenario, edit test data inline, **Auto-generate** test data, or clear values.
- If one journey's scenarios fail, the rest carry on, and the failed journeys are listed with the reason. There is no retry button for them.
- There is no approve or reject step.
- **Generate test cases** starts writing tests and moves to Test cases.
- For an Explorer application this page adds "Explorer worked these out by using the app. Generate test cases to turn them into tests." Explorer's proven tests are reused as-is when they compile.

**Test cases**
- **While generating,** a one-time progress screen shows:
  - Stages: Resolving locators, Writing test cases and Generating fixtures.
  - Counts: test cases, journeys covered and estimated runtime.
  - Status for each journey, including "Incomplete" and "Terminated".
  - Actions: **Terminate** (per journey), **Retry Generation**, **Download Test Cases** and **Run Test Cases**.
- **Normal view:** a paginated list. Each row shows a test case number, name, journey and a source badge: From discovery, Authored by prompt or Recorded.
  - Filter chips with counts (All, Author test cases, Record-and-play test cases) and a search box.
  - Expanding a row offers **View code** and an inline **Test data** editor. Saving the test data rewrites that one test.
- **Author a test case:**
  - The user picks an existing journey or names a new one.
  - They describe in plain English what to do and what to check.
  - Vantage explores the live app ("No prior discovery is needed"), writes the test and adds it to the list. Progress reads "Exploring the live application…" and then "Generating the test case…".
  - Steps it could not perform are listed under "Not generated — Vantage couldn't do these in the application".

**Record and play**
- The user enters a flow name and chooses **Record a login flow** (start signed out) or **Record an authenticated flow** (start signed in as the app's saved user).
- **Record a flow** opens a separate tab that streams a real remote browser. A warning says: "Anything you type — including passwords — is recorded into the generated test."
- **Stop and Save** turns the recording into a test, jumps to Test cases and highlights the new row. **Discard** throws the recording away.
- Edge cases are handled:
  - a blocked pop-up, with a link to open the tab manually
  - a dropped connection, which reconnects
  - a save failure, with Try again
- A recording link expires after 30 minutes.

**Test runs**
- **Run tests** offers two choices:
  - **All test cases.**
  - **Selective run:** a dialog with a required Run Name and a searchable journey list (Select all / Clear). Journeys expand to show individual test cases.
- Every run gets its own **Run #**. Runs can overlap. Tests run 5 at a time, except that a run including tests for an application that keeps progress per login (saved drafts, a cart) runs them one at a time.
- **Runs list:**
  - Summary tiles: latest pass rate, average pass rate, median duration and open failures.
  - Each row shows Run #, who or what triggered it ("Manual run by …" or "Scheduled run — …"), the date, duration, results and pass rate.
  - The list pages with Prev/Next.
- **Run detail:**
  - A status pill, **View report** and **Cancel run**.
  - A "Results by journey" chart and a breakdown into Passed, Self-healed, Flaky and Failed.
  - Each test row may show these chips:
    - **Self-healed:** "Failed on first run — automatically remediated by self-healing".
    - **Flaky:** "Inconsistent results across this test".
    - **Retry:** retry with self-healing.
    - **Heal exhausted.**
    - A pulsing **Self-healing** status while a heal runs.
    - **Skipped** (amber) for a test deliberately skipped in its code, with its reason (for example "Known bug — should: … The app currently: …").
  - Failure details offer a plain-language **Summary**, a **Raw error** tab, a screenshot and a trace. Explanations written by AI are labelled "Explained by AI — may not be exact".
- **Cancel run** stops running tests, marks unfinished ones Cancelled and keeps finished results. No report or email is produced for a cancelled run.
- **Flaky** means a test's last 10 finished results contain at least one pass and at least one fail. A test's first run is never flaky.
- **Self-healing** runs automatically after a failure, within a fixed limit, unless operations have switched automatic healing off. Tests that record a known bug are never healed. The manual Retry uses the admin's attempts setting (default 3). It repairs how a test finds and drives the page; **it never changes what a test checks**, and a failed check is never "healed".
- **View report** opens a Vantage-branded HTML report for the run.
- When a run finishes, **an email** goes to the person who started it (for a schedule, its creator). It lists the outcome and up to 10 failures, with "View report" and "Open in Vantage" links.

**Schedules**
- A table with Schedule, Cadence, Next run and an Enabled toggle. A ⋮ menu offers Run now, Edit and Delete.
- The New/Edit dialog has these fields:
  - **Name.**
  - **Cadence:** Daily, Weekly (pick days), Monthly (day 1–28) or Custom (cron).
  - **Time:** hour and minute pickers in 15-minute steps.
- Schedules **run tests only**; Discovery is not scheduled.
- A scheduled run is skipped if a run is already going; "Run now" then says one is already in progress.
- Every new application starts with three disabled schedules: Nightly, Weekly and Monthly Regression.

**Download project**
- Shows the project structure: one test file per journey, plus fixtures, utilities, the Playwright configuration and a readme.
- **Download project** gives a .zip of a runnable TypeScript Playwright project.

**Application Overview**
- Always listed in the sidebar. Until the first run finishes it shows "No test runs yet".
- Shows the health tier, last run pass rate (with View run), "Pass rate by run" bars, and counts: journeys mapped, test cases, pass rate, open failures, and passed/failed/not run.
- Quick-action cards lead to each tab. The Record and play and Download cards are hidden for viewers. For an Explorer application, the Journeys and Scenarios cards become one **Open Explorer** card: "See what it learned and the scenarios it proved."

**Team members (admin)**
- A table showing name, email, role and last active (or "Never signed in"). A ⋮ menu offers Change role and Remove.
- **Invite member** takes one email address and a role, then sends an email invitation.
- **Invitations expire after 72 hours.** The dialog's current "7 days" wording is wrong and should be corrected.

**Activity (admin)**
- An organization-wide timeline with these columns: Time, Event, By, Result.
- It covers:
  - Discovery runs and test runs, each as a single row that updates in place.
  - Scenario and test case generation.
  - Changes to settings, credentials, the team, applications and schedules.
- Filters: type, application, result, time range (24 hours, 7, 30 or 90 days) and search. The list sorts newest or oldest first.
- A detail drawer explains what happened, why it could not run and the next step. It also shows before and after values for settings changes (credentials are never shown), and screenshots, traces and errors for failed tests.
- **Open application** jumps to the related place.
- History is kept for 90 days.
- Explorer actions are not recorded here; an Explorer application appears only through its single Discovery row.

**Settings (admin)**
- **Discovery limits:**
  - maximum discovery time
  - maximum pages
  - maximum journeys
  - navigation timeout
  - interaction level (Passive, Normal or Aggressive)
  - maximum scenarios per journey
  - maximum test cases per application
  - maximum self-heal attempts
- **Screenshot capture:** for failed test cases (the default), for passed ones, or for all.
- **Auto-clean up removed projects:** after 1 day, 1 week or 1 month (default 1 month).
- **Saved credentials:** reveal a password (the reveal is recorded in Activity) or add and rotate an app's username and password. Apps with no login are listed as "No login".
  - A **Sign-in** column has an on/off switch per app (username-and-password or no-login apps only). Off means the app has no login, and discovery, Explorer and test runs open it directly. Turning it back on needs a username and password saved with **Add credentials**.
- Settings apply to the whole workspace.

## Key Flows

**1. First application, with Discovery.**
1. An admin invites teammates, and each invitee sets a password.
2. A member signs in and lands on Overview, then chooses **Add application**.
3. They enter the name, environment and URL, click Test connection, turn on sign-in and enter credentials, keep Autonomous discovery on, and click **Start discovery**.
4. Vantage proves the login, then Explorer starts and the application opens on **Explorer › Live**.
5. When the "Waiting for you" box pulses, the member clicks **Check the summary**, answers its questions, edits it if needed and clicks **"Looks right — confirm"**.
6. Explorer works through its missions. Blocking questions make the Questions button pulse; the member answers them in the panel.
7. On **Scenarios**, the member watches proof videos and judges each possible bug ("Not a bug, keep as a test" or Ignore), then clicks **Generate tests**.
8. The progress screen finishes, and they choose **Run Test Cases**.
9. They review results, flaky flags and failure explanations, retry with self-healing where useful, open the report, and get the run-completed email.

**1b. Classic discovery** (applications discovered before Explorer, or with Explorer switched off). Discovery starts after the login check and Journeys fill in live. The member renames or deletes journeys, clicks **Review scenarios**, tidies the scenarios and test data, then clicks **Generate test cases** and continues as in steps 8–9.

**2. Application without Discovery.**
1. The member unchecks Autonomous discovery and clicks **Add application**.
2. The app opens on Test cases, without the Journeys, Explorer and Scenarios tabs.
3. They build tests with **Author a test case** or **Record and play**, then run them as in Flow 1.

**3. Keeping it running.** The team turns on a schedule (daily, weekly, monthly or cron) and watches pass rates on Overview and the Applications list. Admins use Activity to see what happened and why, and adjust Settings. Anyone except a viewer can download the project to run it outside Vantage.

**4. Viewer.** A viewer signs in and browses Overview, Applications, journeys, scenarios, test cases and run results. They see no Add, Run, Record, Download, Schedule-edit or menu actions, and reports explain that they aren't available for view-only access. The Explorer tab is the exception: its controls are shown to viewers, but every change they try is refused.

## State Patterns

| State | Treatment |
|---|---|
| Loading content | Grey skeleton blocks in the shape of the content |
| Busy button | The label followed by trailing bouncing dots; the button is disabled while busy |
| Running operation | A status pill with trailing bouncing dots (Discovery, generation, run, self-healing) plus a stage list where relevant |
| Empty | A factual heading, one line and at most one action: "Add your first application", "No applications yet", "No test runs yet" |
| Background services down | A plain message saying the service is unavailable and to try again; nothing is half-started |
| Whole app unreachable | The "service unavailable" screen with Retry |
| Session expired | Return to Sign in with "Your session expired from inactivity" (after 1 hour idle) |
| Validation errors | Inline under the field, in plain words: wrong credentials, unreachable URL, missing Run Name |
| Blocked action | The control is disabled or the menu item explains why (for example, Delete while a run is going) |
| Discovery paused / failed / session expired / recovering | A banner on Journeys explains the situation, with Resume where it applies (classic discovery) |
| Waiting on the user (Explorer) | The thing being waited on pulses: the "Waiting for you" box, the Questions button, Generate tests once it is available |
| Explorer run paused / stopped / failed / expired | The header offers Resume (paused, stopped, failed) or New run; an expired run shows a banner and "Start a new run" |
| Partial generation | The affected journey is marked "Incomplete", the others carry on, and Retry Generation is offered |
| Run failures | A plain-language Summary first, the raw error on its own tab; a run-wide banner when most failures share one cause |
| Cancelled | Shown in neutral grey, never as a failure |
| Viewer access | Write controls are hidden; a report or Settings link shows a short "not available" message (not yet on the Explorer tab, where controls are shown and the platform refuses them) |

## Voice and Copy Rules

- Plain, factual and calm. No exclamation points, no emoji and no hype. Status messages report counts and outcomes.
- The sign-in screen speaks to buyers in plain business language and uses no technical terms.
- Errors say what went wrong and what to do next, in everyday words. Raw technical detail stays behind a "Raw error" tab.
- **Placeholders are instructions, never fake examples:** "Enter the application name", not an invented company or email. The custom cron field is the only exception, where the real format is shown.
- **Busy labels** read as a verb with trailing bouncing dots ("Saving", "Running"), never a spinner or a bare "…".
- More-options menus are always the vertical ⋮.
- Anything written by AI and possibly imprecise is labelled as such ("Explained by AI — may not be exact").
- There are no AI confidence or risk scores anywhere.

## Interaction Primitives

- Single click to open, select and act. There is no drag-and-drop or double-click.
- Row menus (⋮) are always visible, never shown only on hover.
- Rename happens inline. Deletes always ask for confirmation.
- Lists that change in the background (Discovery, generation, runs, Activity) update themselves without a reload.
- Dialogs close with Escape or Cancel.
- Screenshots enlarge on click.

## Not built / deferred

- Scheduling Discovery. Only test runs can be scheduled, even though the schedule dialog's wording suggests otherwise; that wording should be corrected.
- Signing into the app under test with a saved single-sign-on session or a one-time-code (MFA) seed. There is no screen for either. API-key and OAuth sign-in methods do not exist.
- For classic discovery: a screen for its coverage report, and a way to answer questions it gets stuck on. Explorer asks and takes answers through its Questions panel.
- Explorer screens for: adding your own mission, per-mission recordings, the shareable highlight video, the run report, downloading Explorer's proven tests, and re-writing scenarios without exploring again.
- Hiding Explorer's controls from viewers, admin-only Explorer user types and knowledge, and Activity entries for Explorer actions.
- Delivering tests into a CI/CD pipeline, and bringing your own AI model.
- Blocking risky actions during test runs.
- Regenerating journeys or scenarios.
- Scenario type badges (Happy / Negative / Edge), which are hidden.
- Dark mode, which was dropped.
