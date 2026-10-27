---
last_updated: 2026-10-27
---

# Story 1.2: Sign in, password reset & organization-scoped workspace

Status: done

## Story

As a member of a QA team,
I want to sign in, recover a forgotten password, and work in a space that only contains my organization's data,
so that my applications and results are private to my company.

## What it does today

**Accounts are invite-only.** Nobody can sign themselves up. The first admin of an organization is set up by the Vantage team; everyone else joins by accepting an emailed invitation (Story 7.1).

**Sign in.**
- The screen is split: a marketing image panel on the left, and on the right the form "Welcome back — Sign in to your Vantage account" with email, password and a "Forgot password?" link. The footer reads "An initiative of Omnewave".
- After signing in the user lands on **Overview** (Story 1.7).
- Clicking the "Welcome back" heading fills in a development login. It only fills the form; it does not bypass sign-in. This shortcut is currently switched on in every build, including production.

**Forgot / reset password.**
- The user enters an email and always sees "Check your email", whether or not an account exists, so the screen never reveals who has an account.
- The emailed link is valid for 1 hour and can be used once.
- The reset page asks for a new password and a confirmation (at least 8 characters), then returns the user to Sign in.

**Session.**
- Signing in starts a session that ends after **1 hour of inactivity**; any activity extends it.
- When it expires the user is sent back to Sign in with "Your session expired from inactivity. Please sign in again."
- The account menu in the top bar shows the user's name and email and a **Log out** action.

**Organization scoping.**
- Every user belongs to exactly one organization. Everything they see or change — applications, journeys, scenarios, test cases, runs, schedules, team, activity — is limited to that organization. Another organization's data is never returned.
- What a user can do inside the organization depends on their role (admin, member, viewer — Story 7.1).

**Service down.** If the platform can't be reached, a "service unavailable" screen with a **Retry** button is shown instead of the sign-in page.

## Acceptance criteria

1. Given a user with an account, when they sign in with the right email and password, then they land on Overview.
2. Given a wrong email or password, when the user signs in, then they stay on Sign in and see an error.
3. Given any email, when the user asks for a password reset, then the screen says "Check your email" whether or not the account exists, and a reset link valid for 1 hour is emailed only if it does.
4. Given a valid reset link, when the user sets a new password of at least 8 characters that matches its confirmation, then the password changes and the user is returned to Sign in; an expired or used link is refused.
5. Given a signed-in user who is inactive for 1 hour, when they next act, then they are returned to Sign in with the inactivity message.
6. Given a signed-in user, when they open the account menu, then they see their name and email and can log out.
7. Given two organizations, when a user of one signs in, then nothing belonging to the other is ever visible or changeable.
8. Given the platform is unreachable, when the app loads, then the service-unavailable screen with Retry is shown.

## Gaps / not built

- The development login shortcut on the sign-in screen is enabled in production builds and should be limited to development.
- Single sign-on for Vantage's own users is not built (email and password only).
