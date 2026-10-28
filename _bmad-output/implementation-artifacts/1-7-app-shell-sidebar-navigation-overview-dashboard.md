---
last_updated: 2026-10-27
---

# Story 1.7: App shell, sidebar navigation & Overview dashboard

Status: done

## Story

As a QA lead,
I want a consistent sidebar to move around Vantage and a dashboard that shows how testing is going across all my applications,
so that I can see health and what is running right now without opening each application.

## What it does today

**Shell.**
- A left sidebar, and a top bar with a breadcrumb, an **Add application** button (hidden for viewers) and an account menu (name, email, Log out).
- Light theme only: a light grey background with white cards.

**Sidebar — no application open:**
- **Overview**
- **Applications**, with a count badge
- **Add application** (hidden for viewers)
- **Configuration** group (hidden for viewers): **Team members** (admins only), **Activity** (admins only), **Settings** (members see the link but get "Access denied").

**Sidebar — application open:** an Application section with its name, an **Exit** link and these tabs in order: **Overview, Journeys, Explorer, Scenarios, Test cases, Test runs, Record and play, Schedules, Download project**.
- Journeys, Explorer and Scenarios appear only if the application was added with discovery on.
- For an application **discovered by Explorer**, Journeys and Scenarios are hidden: Explorer's own Scenarios view takes their place, and any link that would open them opens Explorer instead. Applications discovered by the classic engine keep Journeys and Scenarios and also get the Explorer tab, but once Explorer is started on one it permanently counts as an Explorer application and loses Journeys and Scenarios.
- Record and play and Download project are hidden for viewers. Overview and Download project are always listed; until there is something to show they display an empty state ("No test runs yet", "No test cases generated yet").
- Tabs can be opened in any order; there is no step-by-step wizard.

**Applications list.**
- Columns: Application, Journeys, Tests, Pass rate, Last activity, Status. Paginated.
- Status shows the discovery or generation stage, "Ready to run", "Running" (a test run is going), or — after the first finished run — a health tier: Healthy, Needs Attention or Critical. A tooltip on the Journeys count shows the share of journeys covered by scenarios.
- Clicking a row opens the application on the most useful tab: Test cases if test cases are being generated for the first time; Overview if tests exist; Test cases if discovery is off; Explorer if Explorer discovered it; otherwise Scenarios or Journeys.
- Admins get a ⋮ menu with Rename and Delete (Story 1.3).
- Empty state: "Add your first application".

**Overview dashboard (whole organization).**
- Headline figures: Applications tested, Test cases generated, Pass rate, Failure rate, Avg run duration, Self-healed locators and Last discovery — some labelled "In the last 7 days".
- Charts: pass rate over time, latest run outcome (pass/fail pooled from each application's last run) and test cases per application.
- **Active pipelines** — a collapsible list of what is running now (discovery, generating test cases, authoring from a prompt, a test run). Clicking an item opens that application.
- Empty states "No applications yet" and "No test runs yet".

**Application Overview tab** (shows "No test runs yet" until the first run finishes, then): health tier, last run pass rate with "View run", a pass-rate-by-run trend, counts (journeys mapped, test cases, pass rate, open failures, passed/failed/not run) and quick-action cards to the other tabs (Record and play and Download hidden for viewers). For an Explorer application the Journeys and Scenarios cards are replaced by one **Open Explorer** card ("See what it learned and the scenarios it proved.").

## Acceptance criteria

1. Given a user signs in, when sign-in succeeds, then they land on the organization Overview.
2. Given no application is open, when the sidebar is shown, then it lists Overview, Applications (with a count) and Add application, plus the Configuration group according to the user's role.
3. Given an application is open, when the sidebar is shown, then it shows the application's name, Exit and its tabs, hiding Journeys, Explorer and Scenarios for applications without discovery, Journeys and Scenarios for applications discovered by Explorer, and Record and play / Download project for viewers.
4. Given the Applications list, when a row is clicked, then the application opens on the most useful tab for its state.
5. Given at least one application has finished a run, when the Overview is shown, then the headline figures and charts reflect all of the organization's applications.
6. Given work is running in any application, when the Overview is shown, then it appears under Active pipelines and clicking it opens that application.
7. Given there are no applications or no runs yet, when the Overview is shown, then the matching empty state appears.
