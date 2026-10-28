---
last_updated: 2026-10-27
---

# Story 7.1: Team members, roles (admin / member / viewer) & invites

Status: done  (single-email invites work; gaps below)

## Story

As an organization admin,
I want to invite teammates with the right level of access and manage who is on the team,
so that people can work in Vantage without being able to do more than their role allows.

## What it does today

**Roles** apply to the whole organization. The platform enforces them, and the screens hide what a role can't use.
- **Admin** — "Everything a member can do, plus saved credentials and discovery limits." Also the only role that can manage the team, see Activity, change Settings, and rename or delete applications.
- **Member** — "Can onboard applications, review scenarios and trigger runs." Adds applications, runs discovery, curates journeys and scenarios, generates, authors and records tests, runs and cancels tests, manages schedules, opens reports and downloads the project.
- **Viewer** — "Can view applications, test cases and run results — no changes." Can't change anything (logging out is the only action allowed), can't open HTML reports or download the project (Explorer's downloads are the exception, see gaps), and doesn't see Add application, Record and play, Download project or the Configuration group.
- Role changes take effect on the person's next action.

**Team members page** (admins only):
- A table of members with name, email, role and last active time ("Never signed in" if they haven't).
- Each row has a ⋮ menu to **Change role** or **Remove**.
- Admins can't change their own role or remove themselves. The last admin can't be demoted ("an organization needs at least one admin").

**Invite member** dialog:
- Email address and a role (Member, Admin or Viewer, with the descriptions above).
- Sends a branded invitation email. An email that already belongs to a user is refused.
- If no email server is configured, the invite link is written to the server log instead.

**Accepting an invite:** the link opens "Set up your account", where the invitee enters a full name and a password (at least 8 characters). The account joins the inviting admin's organization with the chosen role and is signed in straight away. An invalid, expired or already-used link shows one generic error. Invitations expire **72 hours** after they are sent.

Invites and role changes are recorded in Activity (Story 7.3).

## Acceptance criteria

1. Given an admin, when they open Team members, then they see every member with role and last active time; members and viewers can't open the page.
2. Given an admin, when they invite an email with a role, then an invitation email is sent and the invite is recorded in Activity; an email already registered is refused.
3. Given an unused invitation less than 72 hours old, when the invitee sets a name and an 8+ character password, then their account is created in that organization with that role and they are signed in.
4. Given an expired, used or unknown invitation link, when it is opened, then a single generic error is shown.
5. Given an admin, when they change another member's role, then the new role applies on that member's next action; demoting the last admin is refused.
6. Given an admin, when they remove another member, then that person loses access; an admin can't remove themselves or change their own role.
7. Given a viewer, when they try any change by any route, then the platform refuses it.

## Gaps / not built

- **Expiry copy is wrong:** the invite dialog says "Invitation expires in 7 days", but invitations actually expire after 72 hours.
- **Several emails at once don't work:** the dialog says "Comma-separate for several", but only one email address is handled per invitation.
- **Pending invitations aren't shown:** the platform can list and revoke pending invites, but the Team members page has no view or button for them.
- **Remove has no confirmation step** — it happens straight from the ⋮ menu.
- The page subtitle mentions people who "approve scenarios", but the product has no approval step.
- Per-application access is not supported; roles cover the whole organization.
- **Explorer's admin-only actions are open to members** (Epic 8). Any member, not just admins, can add or delete Explorer's other kinds of users with their passwords, and add or delete its knowledge and documents.
- **Viewers can download from Explorer** (Epic 8). A viewer can download Explorer's tests, run report, mission recordings and highlight video, unlike elsewhere where reports and downloads are refused to viewers. Viewers still can't change anything in Explorer: its buttons are shown to them, but the platform refuses each change.
