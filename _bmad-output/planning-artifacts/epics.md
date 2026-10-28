---
stepsCompleted: [1, 2, 3, 4]
date: 2026-10-27
lastUpdated: 2026-10-27
status: current-state
---

# Vantage (AITestGen) - Epic Breakdown

## Overview

This document lists every epic and story for Vantage (AITestGen) as the product stands on 2026-10-27, along with what each one does today and whether it is done, in progress or not started. It describes the current product, not its change history.

Vantage is a web app for QA and engineering teams. It turns a deployed web application into a working, maintained Playwright test suite with very little hand-writing of tests. A team adds an application. Vantage can then explore it on its own in a real browser, find the real user journeys, draft test scenarios and write Playwright tests in TypeScript. By default that exploring is done by Explorer, which learns the application like a new QA engineer, has a person confirm its understanding, asks when unsure, and proves each scenario before it can become a test. Teams can also describe a test in plain English, or record one by clicking through a flow. Tests run on demand or on a schedule. Failing tests are repaired by AI without ever changing what they check. Results come with flaky-test flags, plain-language failure explanations, a branded HTML report and a "run finished" email.

Status key:
- **done**: fully built and working as described.
- **in-progress**: partly built; the missing part is named under "Gaps".
- **not-started**: not built in the current product.
- **dropped (reversed)**: was built, then deliberately removed.

## Requirements Inventory

### Functional Requirements

**Accounts and workspace**
- FR-1: Accounts are invite-only and belong to one organization. Nobody can sign up on their own, and no one ever sees another organization's data.
- FR-2: A user signs in with email and password. The session ends after 1 hour without activity, and the user is told why they were signed out.
- FR-3: A user who forgets their password can request a reset link by email. The link works once and expires after 1 hour. The screen never reveals whether an account exists.
- FR-4: There are three roles: admin, member and viewer. Viewers can see everything but change nothing. Members can do all day-to-day work. Admins can also manage the team, settings, saved credentials, activity history and application rename/delete.

**Applications**
- FR-5: A user can add an application by giving its name, environment and URL. The URL must pass a connection test before the application can be added.
- FR-6: If the application needs a login, the user gives a username and a password or token. These are stored encrypted, used only while exploring and running tests, and never shown again on that screen.
- FR-7: Before exploration starts, Vantage proves the login works by signing in for real. Exploration never starts on a login that hasn't been confirmed.
- FR-8: Autonomous exploration ("Discovery") is optional for each application. Without it, the team builds tests by describing or recording them.
- FR-9: An admin can rename or delete an application. Deleting is blocked while exploration, generation or a test run is still going. A deleted application's data is removed for good after the clean-up period chosen in Settings.
- FR-10: The home Overview and the Applications list show, across every application, what is running now, recent pass rates and each application's health.

**Discovery (classic engine; Explorer is covered by FR-35 to FR-39)**
- FR-11: Vantage explores the application by itself in a real browser. It signs in, signs in again if the session runs out, and records pages, forms, actions and screenshots.
- FR-12: Exploration stops when there is nothing new to find, or when it reaches the admin limits for pages (500 by default) or time (30 minutes by default). The reason it stopped is recorded. Finishing exploration doesn't start scenario or test generation; the user starts that.
- FR-13: Exploration never performs clearly destructive actions, and it avoids getting stuck in loops.
- FR-14: Exploration can be paused and resumed, and it picks up again on its own after a background restart.
- FR-15: AI groups what was found into named business journeys. Each journey shows a screenshot and its steps.
- FR-16: While exploring, Vantage shows progress in plain stages rather than technical detail.

**Journeys, scenarios and test cases**
- FR-17: A user can search, rename and delete journeys. A deleted journey is left out of everything that follows.
- FR-18: For each journey, Vantage drafts test scenarios. Each scenario has steps, test data and an expected result. Users can rename or delete scenarios, edit test data, or fill it in automatically.
- FR-19: Vantage writes a TypeScript Playwright test for each scenario. It shows progress, and generation can be stopped or retried for each journey.
- FR-20: A user can describe a test in plain English. An AI agent then works through the live application, writes the test and lists any steps it couldn't perform.
- FR-21: A user can record a test by clicking through a flow in a remote browser, then save it as a test or throw it away.
- FR-22: All test cases sit in one list. Each shows where it came from (discovery, plain-English prompt or recording) and can be filtered, searched, opened to view its code, or have its test data edited.
- FR-23: A user can download every test as a ready-to-run Playwright project in a .zip file.

**Running tests and results**
- FR-24: A user can run every test, or a named selection of journeys and test cases. Each run gets its own number.
- FR-25: A user can cancel a run. Finished results are kept, and unfinished tests are marked cancelled.
- FR-26: When a test fails, Vantage tries to repair it with AI within a set number of attempts. The repair may fix how the test finds things on the page, but it may never change or weaken what the test checks.
- FR-27: A test is flagged flaky if its recent results include both a pass and a fail.
- FR-28: Every failure has a plain-language explanation, the raw error, a screenshot and a step-by-step trace.
- FR-29: Every finished run has a branded HTML test report.
- FR-30: When a run finishes, the person who started it gets an email summary.
- FR-31: Test runs can be scheduled daily, weekly, monthly or with a custom timetable.

**Workspace administration**
- FR-32: An admin can invite people by email with a role, change a person's role and remove people.
- FR-33: An admin can set limits for exploration and test generation, the self-repair budget, which screenshots to keep, the clean-up period for deleted applications, the logins saved for each application, and whether each application needs sign-in at all.
- FR-34: An admin can see one timeline of everything that happened in the organization. Records are kept for 90 days.

**Explorer discovery**
- FR-35: Adding an application with discovery on starts Explorer, unless operations have switched it off. Users can watch what it is doing live, and pause, stop, resume or start a new run.
- FR-36: Explorer writes a one-page App Summary of what the application is for and waits for a person to check and confirm it before going further. An unconfirmed summary expires after 14 days.
- FR-37: Explorer asks a person when it is unsure or about to do something risky. Every answer becomes knowledge for that application, and the same question is never asked twice.
- FR-38: Explorer works through missions (real goals in the application), hunts for screens that only appear sometimes, lists every screen it found and flags things that look wrong.
- FR-39: Explorer writes scenarios and proves each one. Only proven scenarios are handed on to test generation; a possible bug needs a person's verdict before it can become a test.

### Non-Functional Requirements

- NFR-1 (Security): Logins for the applications under test are kept in a dedicated encrypted secrets store, never in plain text. Only an admin can reveal a saved password, and every reveal is recorded in the activity history.
- NFR-2 (Roles enforced on the server): The server checks every role rule, not just the screen. A viewer is refused every kind of change, in Explorer too. Epic 8 gaps: Explorer's other user types and knowledge are not limited to admins, and viewers can download Explorer's tests, run report, recordings and highlight video.
- NFR-3 (Organization isolation): Every request is limited to the signed-in user's organization through one shared check.
- NFR-4 (Reliability): Long-running work (exploration, generation, test runs) runs in the background and survives individual worker restarts. A check every 15 minutes automatically closes off any test run that has been stuck for more than 6 hours.
- NFR-5 (Test integrity): Automatic repair must never change a test's checks. Any repair that would change one is rejected.
- NFR-6 (Plain language): Errors and progress are written in plain product language. AI-written failure explanations are labelled as such.
- NFR-7 (Retention): A deleted application is purged after 1 day, 1 week or 1 month (admin's choice). Activity history is kept for 90 days.
- NFR-8 (Platform): Vantage is a desktop web app in light mode only.
- NFR-9 (Accessibility target): Every interactive element has a visible focus state and can be used with the keyboard.

### Design Requirements

- DR-1: There is one set of colour, type and spacing values (teal accent, Instrument Sans for interface text, IBM Plex Mono for code). Screens never use their own one-off colours.
- DR-2: Anything that is working shows its label followed by three bouncing dots. There is never a spinning ring or a static "…".
- DR-3: "More options" menus always use the vertical three-dot icon.
- DR-4: Input placeholders tell the user what to enter. They never show made-up example values. The one exception is the custom schedule field, where a real example of the format is shown.
- DR-5: Discovered and AI-generated content never shows a confidence, risk or importance score.

### FR Coverage Map

| Requirement | Epic | Stories |
|---|---|---|
| FR-1 | Epic 1 | 1.2 |
| FR-2 | Epic 1 | 1.2 |
| FR-3 | Epic 1 | 1.2 |
| FR-4 | Epic 7 | 7.1 (rules enforced throughout) |
| FR-5 | Epic 1 | 1.3 |
| FR-6 | Epic 1 | 1.4 |
| FR-7 | Epic 2 | 2.23 |
| FR-8 | Epic 2 | 2.24 |
| FR-9 | Epic 1 | 1.7 |
| FR-10 | Epic 1 | 1.7 |
| FR-11 | Epic 2 | 2.1, 2.2, 2.4, 2.9, 2.14 |
| FR-12 | Epic 2 | 2.3 |
| FR-13 | Epic 2 | 2.10, 2.11, 2.12, 2.19 |
| FR-14 | Epic 2 | 2.17, 2.18 |
| FR-15 | Epic 2 | 2.5, 2.6 |
| FR-16 | Epic 2 | 2.7 |
| FR-17 | Epic 3 | 3.1, 3.4 |
| FR-18 | Epic 4 | 4.1 |
| FR-19 | Epic 4 | 4.2 |
| FR-20 | Epic 4 | 4.4 |
| FR-21 | Epic 5 | 5.1, 5.2 |
| FR-22 | Epic 4 | 4.5 |
| FR-23 | Epic 4 | 4.3 |
| FR-24 | Epic 6 | 6.1 |
| FR-25 | Epic 6 | 6.2 |
| FR-26 | Epic 6 | 6.3 |
| FR-27 | Epic 6 | 6.4 |
| FR-28 | Epic 6 | 6.5 |
| FR-29 | Epic 6 | 6.6 |
| FR-30 | Epic 6 | 6.7 |
| FR-31 | Epic 6 | 6.8 |
| FR-32 | Epic 7 | 7.1 |
| FR-33 | Epic 7 | 7.2 |
| FR-34 | Epic 7 | 7.3 |
| FR-35 | Epic 8 | 8.1 |
| FR-36 | Epic 8 | 8.2 |
| FR-37 | Epic 8 | 8.3 |
| FR-38 | Epic 8 | 8.4 |
| FR-39 | Epic 8 | 8.5 |

Non-functional and design requirements apply across all epics.

## Epic List

### Epic 1: Foundation, Sign-in & Application Onboarding
People sign in to an organization-scoped workspace, find their way around the app shell and Overview dashboard, and add an application with its sign-in details.
**Requirements covered:** FR-1, FR-2, FR-3, FR-5, FR-6, FR-9, FR-10

### Epic 2: Runtime Discovery & AI Journey Inference
Vantage explores an application on its own in a real browser, safely and within limits, and turns what it finds into named business journeys. Discovery is optional for each application and only starts once the login has been proven to work. This epic describes the classic discovery engine, which now runs only for applications discovered before Explorer became the default, or when operations switch Explorer off.
**Requirements covered:** FR-7, FR-8, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16

### Epic 3: Journey Curation
Users review the journeys that were found, and rename or delete them.
**Requirements covered:** FR-17

### Epic 4: Scenario & Test Case Generation
Journeys become test scenarios and then TypeScript Playwright tests. Tests can also be written from a plain-English description. Every test sits in one library and can be downloaded as a project.
**Requirements covered:** FR-18, FR-19, FR-20, FR-22, FR-23

### Epic 5: Record and Play
Users record a test by clicking through a flow in a remote browser, then save or discard it.
**Requirements covered:** FR-21

### Epic 6: Test Execution & Reporting
Users run tests on demand or on a schedule. Failures get repaired automatically where possible, and results come with flaky flags, explanations, evidence, a report and an email.
**Requirements covered:** FR-24 to FR-31

### Epic 7: Workspace Administration
Admins manage the team and roles, workspace settings and the organization's activity history.
**Requirements covered:** FR-4, FR-32, FR-33, FR-34

### Epic 8: Explorer Discovery
Explorer is the default way Vantage learns an application. It reads each screen like a person, writes an App Summary for a person to confirm, asks when unsure, works through missions, flags things that look wrong, and proves scenarios before handing only the proven ones to test generation.
**Requirements covered:** FR-35, FR-36, FR-37, FR-38, FR-39

---

## Epic 1: Foundation, Sign-in & Application Onboarding

### Story 1.1: Platform foundation (repository & services)
**Status:** done

As the delivery team, I want the product split into a web app, a server and separate background workers for exploration, test generation, test runs and recording, so that every feature has a consistent place to live and long jobs never block the screen.

**Acceptance criteria**
1. Given the product is deployed, when a user works in the web app, then all data comes through the server, and the web app's understanding of server data is kept in step with the server automatically.
2. Given a long job (exploration, generation, a test run or a recording), when it starts, then it runs in a background worker and the screen only shows its progress.
3. Given a change is pushed, when the team's automated checks run, then code style, type checks and tests must pass.

### Story 1.2: Sign in, password reset & organization-scoped workspace
**Status:** done

As a team member, I want to sign in securely and only ever see my organization's work, so that our applications and results stay private.

**Acceptance criteria**
1. Given an invited user, when they sign in with their email and password, then they land on the Overview for their own organization.
2. Given a signed-in user has been inactive for 1 hour, when they next act, then they go back to Sign in with "Your session expired from inactivity". Activity keeps the session alive.
3. Given a user clicks "Forgot password?", when they enter an email, then the screen always says "Check your email". If the account exists, a reset link is sent that works once within 1 hour and asks for a new password of at least 8 characters.
4. Given any request, when it is answered, then it only ever includes the signed-in user's organization's data.
5. Given the server can't be reached, when the app loads, then a "service unavailable" screen with a Retry button appears instead of Sign in.

**Gaps / not built**
- Clicking the "Welcome back" heading on the sign-in screen fills in a development login. This is switched on in every build, including the live product. It doesn't skip the password check, but it should be turned off outside development.

### Story 1.3: Add an application — basic details & connection test
**Status:** done

As a member or admin, I want to add an application by giving its name, environment and URL, so that Vantage can start working on it.

**Acceptance criteria**
1. Given the Add application form, when the user fills it in, then it asks for an application name, an environment (staging, production, qa, or "other" with a custom name) and a URL.
2. Given a URL, when the user clicks Test connection, then Vantage checks the URL can be reached. The form won't submit until the test passes; clicking submit too early shows a reminder. The server checks again on submit.
3. Given the form has been submitted, when the screen updates, then it becomes a read-only record of what was submitted ("Connected application").
4. Given a new application, when it is created, then three schedules are set up for it automatically, all turned off: Nightly, Weekly and Monthly Regression.
5. Given a viewer, when they look at the sidebar or top bar, then "Add application" isn't shown.

### Story 1.4: Application sign-in method (credentials / no login, saved sessions, MFA)
**Status:** in-progress

As a member or admin, I want to tell Vantage how to sign in to my application, so that it can explore and test pages behind a login.

**What it does today**
- The form has a toggle, "This application requires sign-in". When it's on, the form asks for an optional login page address, a username and a password or token. A note says these are stored encrypted and used only during exploration and test runs.
- When it's off, the application is treated as needing no login.
- The saved username and password are never shown again on the form. Admins manage them later in Settings, where each application also has a Sign-in on/off switch (Story 7.2).

**Acceptance criteria**
1. Given sign-in is turned on, when the form is submitted, then the username and password go into the encrypted secrets store and nowhere else.
2. Given sign-in is turned off, when Vantage explores or runs tests, then it doesn't try to log in.
3. Given saved credentials, when exploration or a test run happens, then Vantage signs in with them on its own.

**Gaps / not built**
- Reusing a saved single-sign-on browser session works on the server but has no screen.
- Storing an MFA one-time-code seed is accepted on the server when credentials are changed, but has no screen.
- API-key and OAuth sign-in methods don't exist.

### Story 1.6: Dynamic browser tab branding
**Status:** dropped (reversed)

As a user with several tabs open, I wanted the browser tab to show which application I'm working on.

**What it does today**
This story was built and later reversed on purpose. The browser tab always shows the title "Vantage" and the Vantage icon, whichever application is open. Showing each application's name and icon in the tab is no longer part of the product.

**Acceptance criteria**
1. Given any page, when it is showing, then the browser tab shows "Vantage" and the Vantage icon.

### Story 1.7: App shell, sidebar navigation & Overview dashboard
**Status:** done

As a user, I want a clear sidebar, an organization-wide dashboard and a list of applications, so that I can see how everything is doing and jump straight to where work is needed.

**Acceptance criteria**
1. Given no application is open, when the sidebar shows, then it lists Overview, Applications (with a count), Add application (hidden for viewers) and a Configuration group: Team members (admins), Activity (admins) and Settings. The Configuration group is hidden for viewers.
2. Given an application is open, when the sidebar shows, then it shows the application's name, an Exit link and these tabs: Overview, Journeys, Scenarios, Explorer, Test cases, Test runs, Record and play, Schedules, Download project. Journeys, Scenarios and Explorer only appear if Discovery was on for that application. For an application Explorer discovered, Journeys and Scenarios are hidden and any link to them opens Explorer instead. Record and play and Download project are hidden for viewers. Tabs can be opened in any order.
3. Given the Overview, when it loads, then it shows applications tested, test cases generated, pass rate, failure rate, average run time, self-healed locators and last discovery. It also shows charts for pass rate over time, latest run outcome and test cases per application, plus an "Active pipelines" list of work in progress that opens the related application when clicked.
4. Given the Applications list, when it loads, then each row shows journeys, tests, pass rate, last activity and status. Status is the current stage, "Ready to run", "Running", or after the first run a health level: Healthy, Needs attention or Critical. The list is paginated.
5. Given an application row, when the user clicks it, then it opens on the most useful tab: Overview if tests exist, Test cases if generation is running or Discovery is off, Explorer if Explorer discovered the application (and right after an application is added with Discovery), otherwise Scenarios or Journeys.
6. Given an admin opens a row's ⋮ menu, when they choose Rename, then the name is edited in place. When they choose Delete, then they confirm and the application is removed. Delete is blocked, with a reason given, while Discovery, generation or a test run is going. The application's data is purged after the clean-up period set in Settings.
7. Given an application, when its Overview tab opens, then it shows "No test runs yet" until the first run finishes; after that it shows the health level, last run pass rate with a link to the run, "Pass rate by run" bars, counts and quick-action cards for each tab. For an application Explorer discovered, the Journeys and Scenarios cards are replaced by one "Open Explorer" card ("See what it learned and the scenarios it proved").
8. Given there are no applications or no runs yet, when the page loads, then a clear empty state appears.

---

## Epic 2: Runtime Discovery & AI Journey Inference

The stories in this epic describe the **classic discovery engine**. Explorer (Epic 8) is now the default: adding an application with Discovery on, or starting from the Explorer tab, runs Explorer. The classic engine runs only for applications discovered before the switch, or when operations switch Explorer off.

### Story 2.1: Start a discovery run
**Status:** done

As a member or admin, I want Discovery to start as soon as I add an application with Discovery on, so that mapping begins without an extra step.

This story describes the classic engine. With Explorer on (the default), adding an application with Discovery starts Explorer instead (Story 8.1).

**Acceptance criteria**
1. Given an application added with Discovery on and a confirmed login (Story 2.23), when it is created, then a discovery run starts in the background and the Journeys tab shows its progress.
2. Given the background exploration service isn't available, when the user tries to start, then they get a plain message saying the service is unavailable, and nothing is half-created.

### Story 2.2: Autonomous exploration captures the application model
**Status:** done

As a user, I want Vantage to explore my application by itself, so that it builds a full picture of the pages, forms and actions to base tests on.

**Acceptance criteria**
1. Given a running discovery, when Vantage moves through the application, then it records each page with a screenshot, along with its forms and fields, the actions on it and how pages link to each other.
2. Given the same page can be reached by several routes, when it has already been seen, then it isn't explored again.
3. Given a page has many identical actions (for example, an "Edit" button on every row), when Vantage explores it, then it tries one example of each kind rather than every copy.
4. Given an action leads to another page, when that page is on the same site, then it is explored in turn. Pages that fail to load or return an error are skipped.

### Story 2.3: Discovery Completion and Stop Limits
**Status:** done

As a user, I want Discovery to stop on its own at a sensible point, so that it finishes in reasonable time and I know the result is final.

**Acceptance criteria**
1. Given a running discovery, when there are no new pages left to explore, then the run completes.
2. Given the admin limits for maximum pages (500 by default) or maximum discovery time (30 minutes by default), both set in Settings, when either limit is reached, then the run stops and completes with what it found.
3. Given a run stops, when it is recorded, then the reason it stopped is saved with it: nothing new left, page limit reached, or time limit reached.
4. Given a run completes, when its journeys are ready, then scenario and test generation do not start on their own. The user starts them with "Review scenarios" (Story 3.1).
5. Given a run has completed, when its status is shown anywhere, then it reads from the run's own recorded status and is never guessed from other data.

### Story 2.4: Session expiry handling
**Status:** in-progress

As a user, I want Discovery to cope when the application logs it out, so that a timed-out session doesn't quietly produce a half-empty map.

**Acceptance criteria**
1. Given the application's session expires mid-exploration, when Vantage notices it has been sent back to the login page, then it signs in again and carries on. It makes a limited number of attempts in a row.
2. Given signing in again keeps failing, when the run stops, then the Journeys tab shows a "session expired" banner that is distinct from other failures.

**Gaps / not built**
- The banner asks the user to sign in again to continue, but a run that failed this way can't be restarted or resumed.

### Story 2.5: Application model builder
**Status:** done

As a user, I want duplicate findings merged into one clean model of my application, so that journeys and tests are built from reliable information.

**Acceptance criteria**
1. Given exploration has finished, when the model is built, then duplicate pages, forms and actions (within this run or from earlier runs) are merged into one entry each.
2. Given the merged model, when it is built, then each element a test can use (buttons, links, inputs) gets a preferred way to find it plus back-up ways, and expected outcomes are derived from what happened on the page.

### Story 2.6: AI Journey/Capability Inference from the Application Model
**Status:** done

As a user, I want what was found turned into named business journeys, so that I review something meaningful instead of a raw log.

**Acceptance criteria**
1. Given the model has been built, when AI inference runs, then it writes journeys with business-language names (never raw page addresses), each linked to the pages and steps behind it.
2. Given the same journey is found again later, when inference runs, then it is matched to the existing journey rather than duplicated.

### Story 2.7: Business-Oriented Discovery Progress Display
**Status:** done

As a user who has just started Discovery, I want progress shown in plain stages, so that I understand what is happening without technical detail.

**Acceptance criteria**
1. Given a running discovery, when the Journeys tab is open, then it shows these stages in order: Exploring pages, Capturing screenshots, Grouping flows, Mapping journeys. A note says "Discovery runs in the background — this list updates automatically".
2. Given journeys are found, when they appear, then the list fills in live.
3. Given the run is paused, has failed, lost its session, or recovered from a background restart, when the tab is open, then a matching banner explains the situation.

### Story 2.8: Production object storage on AWS S3
**Status:** done

As the team running Vantage, I want screenshots, traces and reports kept in managed cloud storage, so that large files are stored durably without running our own storage service.

**Acceptance criteria**
1. Given Discovery takes a screenshot, or a test run produces a screenshot, trace or report, when it is saved, then it goes to cloud file storage and the database only keeps a pointer to it.
2. Given any environment (local or live), when files are stored, then the same cloud storage service is used.

### Story 2.9: Page Readiness & Bounded Sampling
**Status:** done

As a user, I want Vantage to wait until a page has properly loaded, and to sample long or endless lists rather than scroll forever, so that captures are complete and runs don't stall.

**Acceptance criteria**
1. Given a page is loading, when Vantage is about to capture it, then it waits until network activity has quietened (ignoring analytics and repeated polling), the page has stopped changing and content is showing, up to a time limit. The limit is 15 seconds by default (set in Settings). A per-application override exists but has no screen.
2. Given the limit is reached first, when the page still hasn't settled, then Vantage records that and moves on. The run itself is never blocked.
3. Given a list that keeps loading more items, when new items look the same as earlier ones, then Vantage stops scrolling that list and moves on.

### Story 2.10: Recognising Same, Variant and New Screens
**Status:** done

As a user, I want Vantage to tell a truly new screen apart from the same screen showing different data, so that it neither misses real variants nor wastes time on repeats.

**Acceptance criteria**
1. Given a newly seen screen, when it is compared with earlier screens of the same kind, then it is judged the same (skipped), a variant (kept as a sibling) or new (fully explored), based on a similarity score and per-application thresholds.

### Story 2.11: Exploration Planner, Action Priorities & Getting Back to a Page
**Status:** done

As a user, I want Vantage to finish exploring a page's own actions before moving on, and to plan its next step sensibly, so that pages are fully understood and effort stays bounded.

**Acceptance criteria**
1. Given a page, when Vantage chooses what to do next, then it tries actions within the page (tabs, panels, "load more") before links that lead away.
2. Given a candidate action, when it is checked, then loop, safety and data checks run in a fixed order, and Vantage decides to do it, put it off, or skip it.
3. Given Vantage has to get back to a page to try its next action, when it returns, then it uses a fixed series of fallbacks, ending with reopening the starting page. It never replays a whole path of steps.

### Story 2.12: Safety Engine — Risky Actions, Caution Level & Post-Action Checks
**Status:** in-progress

As a user, I want Vantage to never perform clearly destructive actions while exploring, so that Discovery can't cause irreversible changes in my environment.

**Acceptance criteria**
1. Given a candidate action, when it is classified by rules (wording and patterns), then it is safe, clearly destructive or unclear.
2. Given a clearly destructive action, when it is reached, then it is never performed.
3. Given an unclear action, when it is reached, then whether it is performed depends on the application's safety setting.

**Gaps / not built**
- An AI-assisted second opinion for unclear actions is built but not switched on. Classification is rules-only.
- There is no way to set an application's caution level, so every application is treated as non-production and unclear actions (Submit, Save, Approve) are performed.
- Actions held back for approval can't be approved anywhere.

### Story 2.13: Data Resolver — Choosing What to Type, and Learning from Rejections
**Status:** done

As a user, I want Vantage to fill forms with real or safely made-up data, and never guess business-specific values, so that exploration gets through forms without inventing data it shouldn't.

**What it does today**
When a field needs a value, Vantage tries in this order:
1. Values seeded for the application (Story 2.20).
2. A value it already used earlier in the same run.
3. Safe made-up data for generic fields, or a placeholder file for uploads.

If none of these works, it puts the step off. Every value used is recorded against the run.

**Acceptance criteria**
1. Given a field needs a value, when one is available from the sources above, then it is used and recorded.
2. Given a business-specific value can't be found, when the action is checked, then it is put off rather than guessed.

**Gaps / not built**
- Reading a usable value from the current page was cut on purpose.

### Story 2.14: Widget & Container Coverage — Frames, Embedded Components, Tabs, Dialogs, Windows, Uploads
**Status:** in-progress

As a user, I want Vantage to see inside the containers real enterprise applications use, so that it doesn't report an empty page as a success.

**Acceptance criteria**
1. Given tab groups on a page, when they are detected, then each tab's content is explored. Tabs inside a page are explored before navigation links.
2. Given a dialog or pop-up opens, when its content has been explored, then Vantage closes it and goes back to the page underneath.
3. Given a new window or tab opens, when it does, then Vantage records it as a page linked from the action that opened it (address and title) without exploring it further, and focus goes back to the original.
4. Given embedded frames or self-contained components, when they are present, then Vantage looks inside them up to a set depth.
5. Given a file-upload field, when it is reached, then a safe placeholder file is used.

**Gaps / not built**
- The fallback for widgets that aren't properly labelled (best-guess detection) isn't built.

### Story 2.15: Blocked Items — One Combined Request per Missing Thing
**Status:** in-progress

As a user, I want areas blocked by the same missing information grouped into one question, so that I'm not asked the same thing on every page.

**What it does today**
Every put-off step is recorded and grouped with others that need the same information, whether that is missing data, approval, or both. Blocked areas never stop the rest of the exploration.

**Acceptance criteria**
1. Given a step is put off, when it is recorded, then it joins any open request that needs the same information instead of creating a duplicate.

**Gaps / not built**
- Nothing on screen shows these grouped requests or lets a user answer them.

### Story 2.16: Remembering the Route to a Blocked Area & Resuming It
**Status:** in-progress

As a user, I want the route to a blocked area remembered, so that once I supply what was missing, exploration can pick up there without re-submitting forms and creating duplicate records.

**What it does today**
When a path is blocked, the steps that led there are saved as a readable record. The logic to save a supplied value and explore forward again from the nearest reachable starting page exists, but nothing triggers it.

**Gaps / not built**
- Resuming after the user answers a blocked request. There is no screen for it, and nothing starts it.

### Story 2.17: Pause and Resume Discovery
**Status:** done

As a user, I want to pause Discovery and resume it later without losing progress, so that I don't have to finish everything in one sitting.

**Acceptance criteria**
1. Given a running discovery, when a member or admin clicks Pause Discovery, then the run pauses and a "Paused" banner shows.
2. Given a paused run, when they click Resume Discovery (in the same or a later session), then exploration continues from where it stopped without re-exploring confirmed pages.
3. Given a viewer, when they view the Journeys tab, then pause and resume aren't available.
4. Given an application that has ever had an Explorer run, when Pause or Resume Discovery is attempted, then it is refused with "Explorer discovers this application: pause or resume it from the Explorer tab." Explorer has its own Pause, Stop and Resume (Story 8.1).

**Gaps / not built**
- A summary of confirmed, blocked and remaining-to-explore counts for a paused application.

### Story 2.18: Crash Recovery & Discovery Error Codes
**Status:** done

As a user, I want Discovery to recover from background crashes and to log application errors clearly, so that problems don't silently cut results short.

**Acceptance criteria**
1. Given the background worker restarts mid-run, when it comes back, then the run carries on from where it got to, and the Journeys tab shows that it recovered and is resuming.
2. Given a page keeps failing (server errors, pages that never settle, lost track after a form), when a small number of retries have been used up, then that branch is recorded as errored and exploration continues elsewhere.
3. Given any discovery error, when it is recorded, then it uses one of a small fixed set of error types with a plain explanation.

### Story 2.19: Loop Prevention
**Status:** done

As a user, I want all anti-loop safeguards checked before every action, so that an odd page can't trap Discovery.

**Acceptance criteria**
1. Given a candidate action, when it is checked, then Vantage skips actions it has already tried, cycles of going back and forth between the same pages, and repeated versions of the same page address. It also respects the scroll and per-page action limits.

### Story 2.20: Test Data Pool — Business Values Supplied Before Discovery
**Status:** in-progress

As a user, I want to give Vantage business-specific values before Discovery starts, so that it can get through areas that would otherwise block.

**What it does today**
Values can be stored for each application, and they are kept across discovery runs. When filling a form, Discovery checks these values first. Values marked sensitive go into the encrypted secrets store.

**Gaps / not built**
- There is no screen to add or manage these values. They can only be set through the server.

### Story 2.21: Durable Element Finding — Ranked Locators & Fragility Detection
**Status:** done

As a user, I want Vantage to capture the most reliable way to find each element on a page, so that generated tests keep working after my application's next release.

**Acceptance criteria**
1. Given an element is captured, when the ways to find it are worked out, then dedicated test IDs come first, then accessible role and name, then visible text and labels, then page structure.
2. Given a way of finding an element relies on machine-generated names, when the options are ranked, then it goes below every readable option. It is kept rather than dropped.
3. Given the ways of finding an element are stored, when they are saved, then each gets a reliability score.

### Story 2.22: Coverage report & run diagnostics
**Status:** in-progress

As a user, I want an honest account of what Discovery reached, what it couldn't and why, so that I can trust the result and act on the gaps.

**What it does today**
The server can produce a report for each run that groups what happened into reached, blocked, skipped for safety, errored and unreached, together with the engine's decision details.

**Gaps / not built**
- There is no screen for this report. "Complete" is still shown without these counts.

### Story 2.23: Validate login before discovery starts
**Status:** done

As a member or admin, I want Vantage to prove my application's login works before it starts exploring, so that Discovery never runs, or fails late, on bad credentials.

**Acceptance criteria**
1. Given Discovery is on and the application needs sign-in, when the user submits, then Vantage first signs in with the credentials in a real browser.
2. Given the credentials are rejected, when the check finishes, then the form shows "The username or password is incorrect…" and Discovery doesn't start.
3. Given the result can't be confirmed (for example, a timeout), when the check finishes, then the form shows "We couldn't confirm these credentials…" and Discovery doesn't start.
4. Given the login works, when the check finishes, then the application is created and Discovery starts.

**Gaps / not built**
- The check recognises English error wording only and uses fixed time limits.

### Story 2.24: Optional autonomous discovery (skip discovery per application)
**Status:** done

As a member or admin, I want to add an application without autonomous Discovery, so that I can build tests only by describing or recording them.

**Acceptance criteria**
1. Given the Add application form, when it loads, then "Autonomous discovery" is ticked by default, and the submit button reads "Start discovery".
2. Given the box is unticked, when the user submits, then the button reads "Add application", the application is added without any exploration, and the Journeys, Scenarios and Explorer tabs don't appear.
3. Given an application without Discovery, when it is opened, then it lands on Test cases, where tests can be authored (Story 4.4) or recorded (Epic 5).

---

## Epic 3: Journey Curation

### Story 3.1: Discover Journeys — candidate list & detail panel
**Status:** done

As a reviewer, I want to see every discovered journey with its evidence, so that I can judge each one against what was actually found.

**Acceptance criteria**
1. Given journeys exist, when the Journeys tab opens, then each journey shows as a card with its business name, a screenshot (click to enlarge) and its page-by-page steps. Repeated steps on the same page are shown as one business step.
2. Given many journeys, when the user types in search, then the list filters.
3. Given the user is happy with the journeys, when they click "Review scenarios", then scenario drafting starts and the Scenarios tab opens.
4. Given any journey, when it is shown, then no confidence or risk score appears.
5. Given an application Explorer discovered, when its sidebar shows, then the Journeys page is hidden and links to it open Explorer. Its journeys still exist, built from Explorer's proven scenarios (Story 8.5), because test generation reads them. Opened directly, the page shows an Open Explorer button instead of discovery progress or Pause/Resume.

### Story 3.4: Rename & delete a journey
**Status:** done

As a member or admin, I want to rename or delete a discovered journey, so that names make sense and irrelevant journeys are left out.

**Acceptance criteria**
1. Given a journey, when it is renamed, then the new name shows everywhere the journey appears.
2. Given a journey, when it is deleted, then it is left out of everything that follows: scenarios, tests and runs.
3. Given a viewer, when they view journeys, then rename and delete aren't available.

**Gaps / not built**
- Merging, splitting or editing what makes up a journey isn't supported. Neither is regenerating a kept journey.

---

## Epic 4: Scenario & Test Case Generation

### Story 4.1: Generate scenarios for a journey
**Status:** done

As a member or admin, I want test scenarios drafted for each journey, so that the map becomes real test coverage.

**Acceptance criteria**
1. Given the user clicks "Review scenarios", when drafting runs, then progress shows Reading journeys, Drafting scenarios, Deriving test data, and scenarios appear grouped by journey.
2. Given a scenario, when it is shown, then it has test steps, test data fields and an expected result. Each field is marked "Required for this scenario" or "Optional — auto-filled if left blank".
3. Given a scenario, when a member or admin works on it, then they can rename it, delete it, edit test data in place, fill test data with Auto-generate, or clear values.
4. Given drafting fails for one journey, when the others carry on, then the failed journey is listed with the reason. It can't be retried.
5. Given the user clicks "Generate test cases", when generation starts, then the Test cases tab opens.
6. Given an application Explorer discovered, when the Scenarios page would show, then it is hidden from the sidebar; Explorer's own Scenarios tab replaces it. If Review scenarios is opened, no drafting runs: it lists Explorer's proven scenarios with "Explorer worked these out by using the app. Generate test cases to turn them into tests." and keeps the Generate test cases button. Before anything is handed over, it shows "Scenarios appear here once Explorer has proven its tests."

**Gaps / not built**
- There is no approve/reject step for scenarios. Review means renaming, deleting and editing data.
- Labels for test type (happy path, negative, edge case) exist but are hidden on request.
- There is no Ready / Needs Data filter.
- Values used during Discovery are not carried over as default test data for scenarios.

### Story 4.2: Generate Playwright test cases from scenarios
**Status:** done

As a member or admin, I want each scenario turned into a runnable Playwright test, so that I have real regression coverage.

**Acceptance criteria**
1. Given scenarios, when generation runs, then each scenario becomes a TypeScript Playwright test. Each test is checked to make sure it compiles, repaired automatically if it doesn't, and checked for common problems; tests with problems are marked for review.
2. Given generation is running, when the Test cases tab opens, then a progress screen shows the stages (Resolving locators, Writing test cases, Generating fixtures), counts (test cases, journeys covered, estimated run time) and the status of each journey, including "Incomplete" and "Terminated".
3. Given a journey is generating, when the user clicks Terminate, then that journey stops. When they click Retry Generation, then it runs again.
4. Given generation has finished, when the progress screen shows, then the user can download or run the test cases.

### Story 4.3: Download a generated test project
**Status:** done

As a member or admin, I want to download all tests as a ready-to-run Playwright project, so that I can run them outside Vantage.

**Acceptance criteria**
1. Given at least one test exists, when the Download project tab opens, then it shows the project layout: a folder of tests for each journey, shared fixtures and utilities, a config file and a README.
2. Given the user clicks Download project, when the file is ready, then they get a .zip of a runnable TypeScript Playwright project. The application's login is read from environment settings rather than written into the files.
3. Given a viewer, or an application with no tests, when they look at the sidebar, then the tab is hidden. A viewer is also refused by the server.

### Story 4.4: Author a test case in plain English
**Status:** done

As a member or admin, I want to describe a test in plain English and have Vantage write it, so that I can add tests without Discovery or writing code.

**Acceptance criteria**
1. Given the "Author a test case" panel, when the user picks an existing journey or names a new one and describes what to do and what to check, then an AI agent works through the live application ("No prior discovery is needed").
2. Given the agent is working, when progress shows, then it reads "Exploring the live application…" followed by "Generating the test case…".
3. Given the test is ready, when it is added, then it appears in the test case list marked "Authored by prompt". Vantage first runs it and repairs it as an internal check, and that check run isn't kept.
4. Given some steps couldn't be done in the application, when the result shows, then they are listed under "Not generated — Vantage couldn't do these in the application".
5. Given an application without Discovery, when the panel is used, then it works the same way.

### Story 4.5: Test case library & source filters
**Status:** done

As a user, I want every test case in one searchable list showing where it came from, so that I can find and manage tests whatever their source.

**Acceptance criteria**
1. Given test cases exist, when the Test cases tab opens, then a paginated list shows each test's number, name, journey and source: "From discovery", "Authored by prompt" or "Recorded".
2. Given the filter chips All / Author test cases / Record-and-play test cases (each with a count), when one is chosen, then the list narrows to match. Search works on number, name and journey.
3. Given a row is expanded, when the user picks View code, then the Playwright test opens in a pop-up.
4. Given a member or admin edits test data on a row, when they save, then only that one test is rewritten to use the new data.

---

## Epic 5: Record and Play

### Story 5.1: Record a test in a remote browser
**Status:** done

As a member or admin, I want to record a test by clicking through a flow, so that I can capture exactly the path I care about.

**Acceptance criteria**
1. Given the Record and play tab, when the user enters a flow name and picks "Record a login flow" (start logged out) or "Record an authenticated flow" (start signed in as the saved user), then "Record a flow" opens a separate tab with a live remote browser.
2. Given recording has started, when the page shows, then it warns "Anything you type — including passwords — is recorded into the generated test."
3. Given the browser blocks the pop-up, when that happens, then a link is offered to open it manually. A dropped connection reconnects.
4. Given a recording link, when 30 minutes pass without use, then it expires.
5. Given a viewer, when they look at the sidebar, then the Record and play tab is hidden.

### Story 5.2: Save, cancel and replay recorded tests
**Status:** done

As a member or admin, I want to save or throw away a recording, and run saved recordings like any other test, so that recordings become part of the suite.

**Acceptance criteria**
1. Given a recording, when the user clicks Stop and Save, then it becomes a Playwright test and is checked to make sure it compiles. Vantage then switches to Test cases and highlights the new row, marked "Recorded".
2. Given a recording, when the user clicks Discard, then nothing is saved.
3. Given saving fails, when the error shows, then the user can try again.
4. Given a recorded test, when it is run, then it uses the same set-up, element finding and automatic repair as generated tests.

---

## Epic 6: Test Execution & Reporting

### Story 6.1: Run tests — run all or a named selective run
**Status:** done

As a member or admin, I want to run all tests or a chosen set, so that I can check the whole application or just the areas I care about.

**Acceptance criteria**
1. Given the Test runs tab, when the user chooses Run tests and then "All test cases", then every test in the application runs.
2. Given "Selective run", when the dialog opens, then the user must give a Run Name and pick journeys from a searchable list (with Select all / Clear). They can expand a journey to pick individual tests.
3. Given any run, when it starts, then it gets its own Run # number. Tests run 5 at a time, except that a run containing any test Explorer marked as belonging to an application that keeps progress per login (saved drafts, a cart) runs all its tests one at a time. Manual runs are allowed to overlap.
4. Given the runs list, when it loads, then it shows latest pass rate, average pass rate, median duration and open failures. Each row shows Run #, who or what started it ("Manual run by …" or "Scheduled run — …"), date, duration, results and pass rate. Paging uses plain Prev/Next buttons.
5. Given a viewer, when they view the tab, then they can see runs but can't start one.
6. Given a test deliberately skipped in its code (for example, one marked as a known bug), when the run finishes, then it shows as **Skipped** with its reason instead of errored.

### Story 6.2: Cancel a run
**Status:** done

As a member or admin, I want to cancel a run in progress, so that I can stop a run I started by mistake or no longer need.

**Acceptance criteria**
1. Given a running run, when the user clicks Cancel run and confirms, then running tests are stopped, unfinished tests are marked cancelled and finished results are kept.
2. Given a cancelled run, when it ends, then no report and no email are produced.

### Story 6.3: Self-healing of failing tests
**Status:** done

As a member or admin, I want failing tests repaired automatically when the cause is the test rather than the application, so that small changes to the application don't break my suite.

**Acceptance criteria**
1. Given a test fails, when automatic repair runs, then the AI looks at the error, the console output and a screenshot, and checks the live page if the problem is finding an element. It changes the test, checks it, runs it again, and repeats within a fixed number of automatic attempts.
2. Given a failure caused by the environment, when repair runs, then the test is simply re-run once without AI.
3. Given a failure inside one of the test's checks, when repair is considered, then it isn't repaired. Any proposed fix that would change a check is rejected.
4. Given the same failure keeps happening, when repair runs, then it stops early.
5. Given a failed test, when the user clicks Retry, then it runs again with repair, using the admin's "maximum self-heal attempts" budget (3 by default).
6. Given a test is being repaired, when the run detail is shown, then it shows a pulsing "Self-healing" status. Afterwards the chips "Self-healed" or "Heal exhausted" appear.
7. Given a test that records a known bug, when it fails, then it is never repaired, because repair would hide the bug it records.
8. Given operations have switched automatic repair off (a server setting; it is on by default), when a test fails, then no automatic repair runs. The manual Retry still repairs.

### Story 6.4: Flaky test flags
**Status:** done

As a user, I want unreliable tests flagged, so that I don't chase failures that aren't real.

**Acceptance criteria**
1. Given a test's last 10 finished results, including this run, when they contain at least one pass and at least one fail, then the test shows a "Flaky" chip ("Inconsistent results across this test") and is counted in the run's Flaky group.
2. Given results from cancelled runs or internal check runs, when flakiness is worked out, then they are ignored.
3. Given a test's first run, when it is shown, then it is never flagged flaky.

### Story 6.5: Failure explanations & evidence (screenshots, traces)
**Status:** done

As a user, I want to understand why a test failed and see the evidence, so that I can fix the right thing quickly.

**Acceptance criteria**
1. Given a failed test, when the user opens it, then a Summary tab gives a plain-language explanation. Known errors are explained by fixed rules. Anything else is explained by AI once, labelled "Explained by AI — may not be exact", and the explanation is reused for the same error.
2. Given a failed test, when the user opens Raw error, then the exact error is shown.
3. Given a failed test, when evidence was kept, then a screenshot and a step-by-step trace are available. The Screenshot capture setting decides which screenshots are kept.
4. Given most failures in a run share one cause (for example, sign-in failed), when the run detail is shown, then a banner names that cause.
5. Given the run detail, when it loads, then results are grouped as Passed, Self-healed, Flaky and Failed, with a results-by-journey chart.

**Gaps / not built**
- Fixed-rule explanations recognise English wording only.

### Story 6.6: Allure test report
**Status:** done

As a member or admin, I want a branded HTML report for each run, so that I can share results with others.

**Acceptance criteria**
1. Given a finished run, when the user clicks View report, then a Vantage-branded report opens at a link that stays the same for that run.
2. Given a viewer, when they try to open it, then they see "Reports aren't available for view-only access".
3. Given a report would be too large, when the run finishes, then no report is produced.

**Gaps / not built**
- The report is built just before the run is closed off, so a test that never started may be missing from it.

### Story 6.7: Run-completed email
**Status:** done

As the person who started a run, I want an email when it finishes, so that I don't have to keep checking.

**Acceptance criteria**
1. Given a run finishes, when the email is sent, then it goes to the person who started it. For a scheduled run, including "Run now", it goes to whoever created the schedule.
2. Given the email, when it is opened, then it shows the overall result, up to 10 failures, a "View report" link and an "Open in Vantage" link that opens the run after sign-in.
3. Given a run was cancelled, or ended through automatic clean-up, when it ends, then no email is sent.

**Gaps / not built**
- Each email is sent at most once. In rare cases it may not arrive, but it is never sent twice.
- No email is sent when a run is closed off after getting stuck, or after a manual retry.

### Story 6.8: Scheduled test runs
**Status:** done

As a member or admin, I want test runs to happen automatically on a timetable, so that regressions are caught without anyone remembering to run tests.

**Acceptance criteria**
1. Given the Schedules tab, when it loads, then it lists schedules with name, cadence, next run and an Enabled toggle. A ⋮ menu offers Run now, Edit and Delete.
2. Given the New/Edit schedule dialog, when the user sets the cadence, then they can choose Daily, Weekly (pick days), Monthly (day 1–28) or Custom (a five-part timetable expression interpreted in the server's time zone). Times are picked in 15-minute steps.
3. Given a schedule comes due while a run is already going for that application, when it fires, then it is skipped rather than queued. "Run now" says the run is already in progress.
4. Given an application is deleted, when that happens, then its schedules stop.
5. Given a new application, when it is created, then it gets Nightly, Weekly and Monthly Regression schedules, all turned off.

**Gaps / not built**
- Only test runs can be scheduled. The dialog text says "Run discovery or test cases automatically on a cadence", but Discovery can't be scheduled, and the text needs correcting.

---

## Epic 7: Workspace Administration

### Story 7.1: Team members, roles (admin / member / viewer) & invites
**Status:** done

As an admin, I want to invite teammates with the right role and manage the team, so that the right people have the right access.

**Acceptance criteria**
1. Given the Team members page (admins only), when it loads, then it lists each person's name, email, role and when they were last active ("Never signed in" if they haven't). A ⋮ menu offers Change role and Remove.
2. Given Invite member, when the admin enters an email address and picks Member, Admin or Viewer, then that person is emailed an invitation link that can only be used once.
3. Given an invitee opens the link, when they enter their full name and a password of at least 8 characters, then their account is created in that organization and they are signed in. A link that is invalid, expired or already used shows one general error.
4. Given role rules, when an admin acts, then they can't remove themselves or change their own role, and the last admin can't be demoted. Role changes take effect on the person's next action.
5. Given a viewer, when they use the app, then the only change they can make is signing out.

**Gaps / not built**
- The invite dialog says "Invitation expires in 7 days", but invitations actually expire after 72 hours. The text needs correcting.
- If no email service is set up, the invitation link is only written to the server's log.

### Story 7.2: Settings
**Status:** done

As an admin, I want to control Discovery and test limits, evidence and clean-up, and saved logins, so that Vantage behaves the way our organization needs.

**Acceptance criteria**
1. Given Settings (admins only; members who open it see "Access denied" and viewers don't see the link), when it loads, then it offers maximum discovery time, maximum pages, maximum journeys, navigation timeout, interaction level (Passive / Normal / Aggressive), maximum scenarios per journey, maximum test cases per application and maximum self-heal attempts.
2. Given Screenshot capture, when the admin changes it, then screenshots are kept for failed tests (the default), passed tests, or all tests.
3. Given clean-up of deleted applications, when the admin chooses a period, then deleted applications are purged after 1 day, 1 week or 1 month (the default). Clean-up is always on.
4. Given Saved credentials, when an admin reveals a password, then it is shown and the reveal is recorded in Activity. When an admin adds or changes a username and password, then it is saved. It isn't re-checked at that point.
5. Given Saved credentials, when it loads, then it also lists applications with no login ("No login") and shows a per-application Sign-in on/off switch, which only admins can change and only for username-and-password or no-login applications. Turning it off means the application has no login, so discovery, Explorer and test runs open it directly. It can't be turned back on from the switch alone: saving a username and password with Add credentials turns sign-in back on.
6. Given any change, when it is saved, then it applies to the whole deployment.

### Story 7.3: Activity history
**Status:** done

As an admin, I want one timeline of everything that happened across the organization, so that I can see what ran, what failed and who changed what.

**Acceptance criteria**
1. Given the Activity page (admins only), when it loads, then it shows Time, Event, By and Result for discovery runs and test runs (each one row that updates as it goes), scenario and test generation, and changes to settings, credentials, the team, applications and schedules.
2. Given the filters, when the admin uses them, then they can filter by type, application, result and time range (24 hours, 7, 30 or 90 days), search, and sort newest or oldest first.
3. Given a row is opened, when the detail drawer shows, then it explains what happened, why it couldn't run and a suggested next step. Settings changes show before and after values; credentials are never shown. Failed tests show a screenshot, a trace, the exact error and the log.
4. Given Open application, when it is clicked, then it goes to the related tab or run.
5. Given an entry is older than 90 days, when daily clean-up runs, then it is deleted.

**Gaps / not built**
- Search filters each page after it loads, so a page of results can come back shorter than expected.
- Explorer actions are not recorded.

---

## Epic 8: Explorer Discovery

Explorer is the default discovery engine. Adding an application with Discovery on, or starting from the Explorer tab, runs Explorer; the classic engine (Epic 2) runs only for applications discovered before the switch, or when operations switch Explorer off.

### Story 8.1: Start Explorer and watch it live
**Status:** in-progress

As a member or admin, I want Explorer to start learning my application as soon as I add it, and to watch what it is doing as it happens, so that I know discovery is under way and can step in, pause or stop it when I need to.

**What it does today**
- Adding an application with Autonomous discovery ticked starts Explorer. Users can also start it from the Explorer tab (compass icon, after Journeys) with **Start exploring**, after optionally adding other kinds of users with their usernames and passwords. Only one run can be active per application.
- The header shows a one-line status and Questions, Pause, Stop, Resume or New run. The **Live** sub-tab shows a "Waiting for you" box, the latest screenshot with a trail of 6, the last 80 activity entries and a four-stage progress panel (Learning the app → Your check → Trying every path → Writing scenarios).
- The application's discovery status follows Explorer (running, paused, failed, then complete after the hand-off). Classic Pause/Resume is refused for any application that has had an Explorer run.
- Explorer never deletes data, moves money, makes a business decision or signs out on its own; it asks first. It presses a final Save, Submit or Create only on applications marked as test environments.

**Acceptance criteria**
1. Given an application is added with Autonomous discovery ticked and Explorer is on, when it is created, then an Explorer run starts and the application opens on the Explorer tab.
2. Given Explorer's background service isn't running, when the application is added, then its discovery is marked failed ("worker unavailable"), and Explorer can be started later from the Explorer tab.
3. Given no run is active, when the user presses Start exploring or New run, then a run starts. A second run can't start while one is active.
4. Given a running run, when the Live tab is open, then it shows the status line, latest screenshots, activity log and progress.
5. Given a running run, when the user presses Pause or Stop and later Resume, then it carries on from the step it reached without redoing finished work.
6. Given operations have switched Explorer off, when an application is added with discovery, then the classic engine runs instead.

**Gaps / not built**
- No deployment setup for Explorer's background service yet; in a deployed environment, adding an application with discovery marks discovery failed.
- Members, not just admins, can add or delete other user types with their passwords. Viewers can download Explorer's tests, run report, mission recordings and highlight video (no screen offers these yet).
- Explorer actions are not recorded in Activity.
- Starting Explorer on an application discovered by the classic engine hides its Journeys and Scenarios pages for good, although the start card says current Journeys are not affected.
- The tab's first loading state uses a spinner instead of trailing bouncing dots.
- Per-mission recordings and the highlight video have no screen.

### Story 8.2: Review and confirm the App Summary
**Status:** done

As a member or admin, I want Explorer to tell me what it thinks my application is for and wait for me to confirm it, so that everything it tests afterwards is based on an understanding I have checked.

**Acceptance criteria**
1. Given Explorer has learned the application, when the one-page App Summary is ready, then the run waits, the "Waiting for you" box offers Check the summary, and the person who started the run is emailed.
2. Given a waiting summary (name, one-liner, key tasks, questions, optional goal for the run, screens to leave out), when the user edits and saves it, then the changes are kept.
3. Given unanswered questions in the summary, when it is shown, then "Looks right — confirm" is disabled. Once all are answered, confirming turns the answers into knowledge for the application and Explorer moves on to missions.
4. Given a summary left unconfirmed for 14 days, when the time is up, then the run expires for good; "Start a new run" begins from what was already learned and keeps the answers.
5. Given the Knowledge panel, when the user adds a fact or test data, uploads a document (PDF, Word, text, Markdown or CSV, up to 15 MB) or forgets an item, then it applies to this and every later run of that application.

**Gaps / not built**
- Members, not just admins, can add or delete knowledge and documents.
- Without mail settings on the server, the email is only logged.
- Explorer reads dates in English month names only.

### Story 8.3: Answer Explorer's questions
**Status:** done

As a member or admin, I want Explorer to ask me when it is unsure or about to do something risky, and to remember my answers, so that it gets past things only I know without guessing, and never asks me the same thing twice.

**Acceptance criteria**
1. Given Explorer needs information or permission, when it asks, then the header's Questions button shows the count and pulses, and the question appears in the "Questions for you" panel and the "Waiting for you" box.
2. Given a blocking question, when nobody answers within 10 minutes (the default), then only the asking mission was waiting, and it carries on without the answer.
3. Given an answer, when the same need comes up in this or a later run, then Explorer uses the answer instead of asking again. Similar open questions are merged.
4. Given an "is this a bug?" question, when it is open, then it never blocks and sits with its finding.
5. Given the person who started the run, when Explorer asks a blocking question, then they are emailed.

**Gaps / not built**
- Without mail settings on the server, the email is only logged.

### Story 8.4: Missions, screens and findings
**Status:** in-progress

As a member or admin, I want Explorer to work through the real goals of my application, show me every screen it found and flag anything that looks wrong, so that I can see how much was covered and spot problems before any test is written.

**Acceptance criteria**
1. Given the summary is confirmed, when Explorer plans, then it creates up to 15 missions and works on at most 3 at once. Each mission in the Progress panel has a Skip button.
2. Given screens that only appear for some options, amounts or server responses, when Explorer hunts, then it tries each option, small and large amounts and empty or failing responses, and records the screens that appear.
3. Given the Screens sub-tab, when it opens, then it shows a searchable, paged grid of screens; clicking one shows its actions and where each leads.
4. Given health problems (broken screens, server errors, broken links, slow pages, wording mistakes, things that look wrong), when Explorer meets them, then they appear under "Things that look wrong", where each can be marked a false alarm or judged as a bug, and the list can be downloaded as CSV.

**Gaps / not built**
- Worked out and stored, but no screen: adding your own mission, per-mission recordings, which screens each extra user type can reach, unlinked pages, code coverage and the application health score.
- No map or graph view of screens.

### Story 8.5: Proven scenarios and hand-off to test cases
**Status:** done

As a member or admin, I want Explorer to write scenarios, prove each one works, and pass only the proven ones on to test generation, so that my test cases start from behaviour that has been shown to work and possible bugs are judged by a person.

**Acceptance criteria**
1. Given a run reaches testing, when scenarios are written, then they come in seven kinds: Getting around, Input rules, Error handling, Data shown, Saving a form, Whole journey (up to 8) and Page quality. There are up to 150 per run, scaled to the application's size.
2. Given a scenario, when it replays the same way every time and fails without its key step, then it is marked as working. When the application behaves differently from what should happen, then it is kept as a possible bug.
3. Given the Scenarios sub-tab, when it opens, then it shows counts, kind filters, groups (whole journeys first, then one per screen) and a proof video for each scenario.
4. Given testing has finished, when results are handed over, then only proven scenarios become journeys and scenarios in the rest of the product. A possible bug is handed over only when the user chooses "Not a bug, keep as a test"; Ignore leaves it out.
5. Given at least one working scenario, when the user presses Generate tests, then test cases are generated, reusing Explorer's proven test as-is wherever it compiles.
6. Given Explorer runs again, when it hands over, then its earlier results stop being current.

**Gaps / not built**
- No screen for the run report, downloading Explorer's proven tests as a project, or re-writing scenarios without exploring again.
- Whether an application keeps progress per login (which makes its runs go one test at a time) is a keyword guess.
- For an application first discovered by the classic engine, Generate tests would likely cover both the classic journeys and Explorer's (inferred, not confirmed).

---

## Not built / deferred

These were planned at some point but are not in the current product:
- Sending tests into a customer's CI/CD pipeline or code repository.
- Running Vantage, or its AI, inside a customer's own network.
- Blocking destructive actions during test runs. This was deliberately removed so "Run tests" works with no setup.
- Regenerating a kept journey's scenarios and tests on request.
- A screen for the discovery coverage report (Story 2.22).
- Answering blocked discovery requests, and resuming or replaying the path to them (Stories 2.15, 2.16).
- A Confirmed / Blocked / Remaining summary for a paused Discovery (Story 2.17).
- A Ready / Needs Data filter for scenarios, and carrying Discovery values into scenario test data (Story 4.1).
- A screen to manage seeded test data (Story 2.20).
- Single-sign-on session reuse, MFA codes, API-key and OAuth sign-in for applications under test (Story 1.4).
- Scheduling Discovery runs.
- Deployment setup for Explorer's background service, limiting Explorer's other user types and knowledge to admins, refusing Explorer's downloads to viewers, and recording Explorer actions in Activity (Epic 8).
- Screens for Explorer's extra results: adding a mission, recordings, the highlight video, the run report, the proven-tests download, re-writing scenarios, user-type access, unlinked pages, code coverage and the health score (Stories 8.1, 8.4, 8.5).
- Per-application browser tab branding (Story 1.6). This was built and then deliberately reversed.
- Dark mode. This was dropped; the product is light mode only.
