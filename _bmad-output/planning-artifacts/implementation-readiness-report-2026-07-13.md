---
stepsCompleted: [1, 2, 3, 4, 5, 6]
date: 2026-10-27
lastUpdated: 2026-10-27
reportType: state-of-delivery
documentsIncluded:
  - "epics.md"
---

# State of Delivery Report

**Date:** 2026-10-27
**Project:** Vantage (AITestGen)

This report replaces the original readiness check from 2026-07-13. It describes what is built today, what is missing and the main risks. It is based on the current product and its history, not on earlier plans. The epic and story list it refers to is in `epics.md`.

## Summary

Vantage is in working order from start to finish. A team can:
- invite colleagues with roles
- add an application and prove its login works
- let Vantage explore it with Explorer (the default discovery engine), confirm what it learned and answer its questions, or skip exploration
- review journeys and scenarios, or Explorer's proven scenarios and possible bugs
- generate TypeScript Playwright tests, or add tests by plain-English description or by recording
- run tests on demand or on a schedule, with automatic repair that never changes what a test checks
- read results with flaky flags, plain-language explanations, screenshots, traces, a branded report and an email
- download everything as a project
- manage the team, settings and activity history

The product has grown well beyond the original four-epic plan. Record and play, test execution and reporting, scheduling, and workspace administration (roles, settings, activity) were all added and are now built. Explorer (Epic 8) is the newest addition and is now the default way Vantage discovers an application; the original discovery engine (Epic 2) remains as "classic discovery" for applications discovered before the switch.

| | Count |
|---|---|
| Epics | 8 |
| Stories | 55 |
| Done | 44 |
| In progress | 10 |
| Dropped (reversed) | 1 |

**Overall status: delivered and usable.** The open items are mostly deeper Discovery features that have no screen yet, plus a few security settings in the live setup that should be fixed before wider rollout. Explorer works end to end in development but cannot yet be deployed, lets members manage its user types and knowledge and viewers download its results, and is not recorded in Activity.

## Delivery by Epic

### Epic 1: Foundation, Sign-in & Application Onboarding (4 of 6 done)
- **Built:**
  - Invite-only, organization-scoped sign-in, with a 1-hour inactivity timeout and password reset.
  - The sidebar app shell.
  - An organization-wide Overview dashboard with charts and a live "Active pipelines" list.
  - The Applications list with health levels, plus rename and delete for admins.
  - The Add application form with a required connection test and an optional username/password login.
- **In progress (1.4):** Single-sign-on session reuse and MFA codes work on the server but have no screen. API-key and OAuth sign-in do not exist.
- **Dropped, reversed (1.6):** Per-application tab branding was built and then deliberately removed. The browser tab always shows "Vantage".

### Epic 2: Runtime Discovery & AI Journey Inference (17 of 24 done)
This epic now describes the **classic discovery engine**. It runs only for applications discovered before Explorer became the default, or for new applications if operations switch Explorer off.
- **Built:**
  - Autonomous exploration in a real browser, which signs in on its own and signs in again if the session runs out.
  - Waiting until pages have properly loaded, and sampling long lists.
  - Telling new screens apart from repeats, and looking inside tabs, dialogs, pop-up windows, embedded frames and file uploads.
  - Refusing clearly destructive actions, and protecting against loops.
  - Stopping when nothing new is left, or at the admin limits for pages (500 by default) or time (30 minutes by default), with the reason recorded. Finishing Discovery doesn't start generation; the user starts it with "Review scenarios".
  - Pause and resume, plus recovery after background restarts.
  - Ranking reliable ways to find page elements.
  - Turning findings into named business journeys with AI.
  - Plain-language progress stages.
  - Checking the login before exploration starts (new).
  - Making Discovery optional for each application (new).
- **In progress:**
  - A run that fails after the session expires can't be restarted or resumed (2.4).
  - There's no per-application caution level, the AI safety second opinion is off, and held actions can't be approved (2.12).
  - The fallback for widgets that aren't properly labelled isn't built (2.14).
  - Blocked areas are recorded and grouped, but users can't see or answer them (2.15), and nothing resumes from them (2.16).
  - Seeded test data can only be set through the server (2.20).
  - The coverage report exists on the server but has no screen (2.22).

### Epic 3: Journey Curation (2 of 2 done)
Journeys show as cards with a screenshot and steps. Users can search them, and members and admins can rename or delete them. There is no approval step; deleting is the only way to leave a journey out.

### Epic 4: Scenario & Test Case Generation (5 of 5 done)
- Scenarios are drafted for each journey, with test data that can be edited or filled in automatically.
- Each scenario becomes a TypeScript Playwright test. Every test is checked to make sure it compiles, and repaired automatically if not. Generation can be stopped and retried for each journey.
- New since the original plan:
  - Plain-English test authoring by a live AI agent.
  - One test case library with source filters (discovery, prompt, recorded).
- The whole suite downloads as a runnable project.

### Epic 5: Record and Play (2 of 2 done, new epic)
- Users record a login flow or a signed-in flow in a remote browser streamed into the page.
- They can save the recording as a test or discard it.
- Recorded tests run and repair like any other test.

### Epic 6: Test Execution & Reporting (8 of 8 done, new epic)
- Runs can include every test or a named selection, 5 tests at a time, and can be cancelled.
- Failing tests are repaired automatically, and a repair is never allowed to change a test's checks.
- Tests are flagged flaky based on their last 10 results.
- Failures come with plain-language explanations, screenshots and traces.
- Each run has a branded HTML report and sends a run-completed email.
- Schedules can run daily, weekly, monthly or on a custom timetable.

### Epic 7: Workspace Administration (3 of 3 done, new epic)
- Three roles (admin, member, viewer), enforced by the server; viewers can change nothing anywhere, Explorer included.
- Gaps (7.1): members, not just admins, can manage Explorer's other user types and knowledge; viewers can download Explorer's results; the invite dialog's wording is wrong and pending invites are not listed.
- Email invitations, plus changing roles and removing people.
- Settings for limits, screenshot capture, clean-up and saved logins.
- An admin Activity timeline with filters and a detail drawer, kept for 90 days.

### Epic 8: Explorer Discovery (3 of 5 done, new epic)
- **Built:**
  - Adding an application with discovery on starts Explorer; it can also be started, paused, stopped, resumed or re-run from the Explorer tab, which shows a live view, an activity log and stage progress (8.1).
  - Explorer writes an App Summary and waits for a person to check, edit and confirm it; an unconfirmed summary expires after 14 days (8.2, done).
  - Explorer asks blocking questions (only the asking mission waits, 10 minutes by default) and "is this a bug?" questions; every answer, fact or uploaded document becomes knowledge for the application. The run starter is emailed (8.3, done).
  - Missions (up to 3 at a time), a screens gallery, a hunt for screens that only appear sometimes, and health findings with false-alarm marking and CSV download (8.4).
  - Scenarios in seven kinds, each proven by replay with proof videos; possible bugs kept for a person to judge; only proven scenarios handed to test generation, which reuses Explorer's proven test when it compiles (8.5, done).
- **In progress:**
  - Members, not just admins, can manage Explorer's other user types and knowledge; viewers can download its tests, report, recordings and highlight video; its actions are not in Activity; and its background service has no deployment setup (8.1).
  - Adding your own mission, per-mission recordings, other user types' access results, unlinked pages and the app health score are stored but have no screen (8.4).
- Related changes to test runs: tests for applications that keep progress per login run one at a time; known-bug tests are never healed; deliberately skipped tests show as Skipped with a reason; operations can turn automatic healing off. Settings gained an admin-only per-application Sign-in switch.

## Gaps

### Features with no screen yet
- Discovery coverage report: what was reached, blocked, skipped for safety, errored or unreached.
- Answering blocked Discovery requests, and resuming exploration from them.
- Managing seeded test data for each application.
- Single-sign-on session reuse and MFA codes for applications under test.
- Explorer: adding your own mission, per-mission recordings, the shareable highlight video, the run report and its download, downloading Explorer's proven tests, and re-writing scenarios without exploring again.

### Wording in the product that doesn't match behaviour
- The invite dialog says invitations expire in 7 days. They actually expire after 72 hours.
- The schedule dialog says Discovery can be scheduled. Only test runs can.
- A few busy states still show "Saving…", "Deleting…" or "Terminating…" text instead of the standard bouncing dots.
- The application URL field's placeholder shows only "https://" instead of telling the user what to enter.
- Explorer's start card says "Your current Journeys are not affected", but starting Explorer on a classic application hides its Journeys and Scenarios pages for good and refuses the classic Pause and Resume.
- The Explorer tab still uses ring spinners in a few places (first load, live frame, stage progress, scenarios being tried) instead of bouncing dots.

### Deliberately not built
- Sending tests into a customer's CI/CD pipeline or code repository.
- Running Vantage or its AI inside a customer's own network.
- Blocking destructive actions during test runs. This was removed so runs need no setup.
- Regenerating a journey's tests on request.
- API-key and OAuth sign-in for applications under test.
- A Ready / Needs Data filter for scenarios.
- Carrying values used during Discovery into scenario test data.
- For classic discovery: answering blocked items, replaying the path to them, and a Confirmed / Blocked / Remaining summary. (Explorer asks and takes answers instead.)
- Per-application browser tab branding. This was built and then reversed.
- Scheduling Discovery.
- Dark mode.

## Known Risks

### Security
1. **Background job history is lost if the job engine restarts.** In the live environment, the engine that runs exploration, generation, test runs and schedules keeps its records in memory only. After a restart, in-flight work is lost, and user schedules may need to be set up again.
2. **The sign-in cookie isn't restricted to secure connections in the live setup, and the secure-connection certificate isn't fully set up.** Sessions could be exposed on an unencrypted connection.
3. **If the session-signing secret is ever left unset, a publicly known fallback is used.** Anyone could then forge a sign-in.
4. **The development login shortcut ships in the live product.** Clicking the "Welcome back" heading on the sign-in page fills in a development account. It doesn't skip the password check, but it should be removed outside development.
5. **The secrets store keeps its unlock key next to the data it protects.** Anyone who gets hold of that storage gets both.
6. **The live database's address is written directly into the shared configuration.**
7. **Explorer's role rules are looser than the rest of the product.** Viewers can't change anything in Explorer, but any member (not just admins) can store other user types' passwords and change knowledge and documents, and viewers can download Explorer's tests, run report, recordings and highlight video. None of Explorer's actions appear in Activity.

### Reliability
8. **Every service runs as a single copy.** Any crash means that part of the product is down until it restarts, and report generation relies on there being exactly one test-running service.
9. **There is no monitoring or alerting.** Problems only show up in plain logs and the job engine's own screen, so failures may go unnoticed until a user reports them.
10. **A run-completed email can occasionally go missing.** It is never sent twice. No email is sent after a stuck run is closed off or after a manual retry.
11. **The pre-Discovery login check can leave a temporary copy of the credentials behind** if the background worker dies during the check.
12. **Explorer media is stored in the main database.** Its screenshots and videos (1 to 6 MB per mission) are kept there, not in cloud file storage, so the database will grow quickly.

### Product limits
13. **Settings apply to the whole deployment, not to each organization.** One admin's limits and clean-up period affect every organization on the same deployment.
14. **Recognising login errors and explaining test failures with fixed rules only works in English.** Applications in other languages fall back to AI explanations or "couldn't confirm" results.
15. **Two "service unavailable" cases** (test authoring and the scheduling service) show a generic error instead of a specific message.
16. **Starting Explorer on a classic application is one-way.** Its Journeys and Scenarios pages disappear and the classic Pause and Resume are refused for good. Generate tests may then cover both the classic journeys and Explorer's (not yet confirmed).
17. **One-at-a-time runs rely on a guess.** Whether an application keeps progress per login is guessed from keywords. A wrong guess either slows runs or lets parallel tests interfere.
18. **Several Explorer features have no screen** (see Gaps).

### Delivery process
19. **The main release line is about three months behind the working line.** It stops at the test-download feature from late July, so nearly everything described here exists only on the working line.
20. **The architecture diagram is out of date.** It is missing the test-running service, the recording service, the live AI agent, email and the HTML report.
21. **Explorer cannot be deployed yet.** Explorer is the default, but its background service has no deployment setup. In a deployed environment, adding an application with discovery on would mark discovery failed.

## Recommendations

1. **Before wider rollout, fix the live security settings:**
   - persistent job-engine storage
   - secure-only cookies with a proper certificate
   - a required session secret with no fallback
   - removing the development login shortcut
   - separating the secrets store's unlock key from its data
2. **Bring the main release line up to date** with the working line.
3. **Correct the mismatched product wording:** invite expiry and the schedule dialog.
4. **Decide which Discovery back-end features get screens:** coverage report, blocked requests and resume, seeded test data. Either build their screens or formally drop them.
5. **Add basic monitoring and alerting** for background job failures and stuck runs.
6. **Decide whether settings should be per organization** before more than one organization shares a deployment.
7. **Before Explorer reaches a deployed environment:** ship its background service (or have operations switch new applications back to classic discovery), limit Explorer's user types and knowledge to admins, refuse its downloads to viewers, add Activity entries for Explorer actions, and move its screenshots and videos out of the main database.
8. **Decide which Explorer features built behind the scenes get screens:** own missions, recordings, highlight video, report, tests download and regenerate.

---

**Prepared by:** State-of-delivery review
**Date:** 2026-10-27
