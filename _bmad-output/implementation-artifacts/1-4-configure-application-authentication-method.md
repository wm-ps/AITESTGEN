---
last_updated: 2026-10-27
---

# Story 1.4: Application sign-in method (credentials / no login, saved sessions, MFA)

Status: in-progress

## Story

As a user adding an application,
I want to tell Vantage how to sign in to it,
so that discovery, authored tests, recordings and test runs can reach the pages behind the login.

## What it does today

**On the Add application form** the toggle **"This application requires sign-in"** gives two choices:
- **No sign-in** (toggle off) — Vantage visits the application as an anonymous visitor.
- **Username and password** (toggle on) — the form asks for an optional **Login URL** (when the login page isn't the main address), a **Username** and a **Password**. Hint text says credentials are stored encrypted and used only at discovery and run time.

**How credentials are used and protected:**
- Credentials are kept only in a secure secrets store — never in ordinary application data, logs or screens. Once saved they show as "Stored securely — not shown".
- When discovery is on, Vantage logs in with them in a real browser before discovery starts, and won't start on a login that hasn't been proven to work (Story 2.23).
- During discovery (classic engine or Explorer) Vantage logs in automatically and logs in again if the session expires partway through.
- Explorer can also be given **other kinds of users** (a user type with its own username and password) on its start card. These are kept in the same secure secrets store (Epic 8).
- Test runs, authored tests and "authenticated" recordings sign in with the same saved credentials.

**Changing credentials later** is done by an admin in **Settings → Saved credentials** (Story 7.2): add or replace an application's username and password, or reveal a stored password (the reveal is recorded in Activity). Credentials saved there are not re-checked against the live application.
- The same list has a per-application **Sign-in** on/off switch (admins only; username-and-password and no-login applications only). Turning it **off** makes the application a no-login application: its saved login is replaced with an empty session, and discovery, Explorer and test runs open it directly. It can't be turned back **on** from the switch alone: saving a username and password with **Add credentials** turns sign-in on again.

**Supported by the platform but with no screen:**
- **Saved browser session** — for applications behind single sign-on, a previously captured signed-in browser session can be stored and reused instead of a username and password.
- **MFA code seed** — an authenticator (one-time code) seed can be stored when credentials are replaced.

## Acceptance criteria

1. Given the sign-in toggle is off, when the application is added, then Vantage treats it as needing no login.
2. Given the toggle is on, when the user enters a username and password (and optionally a login URL), then they are stored only in the secure secrets store and never shown again in plain text on the form.
3. Given stored credentials, when discovery, an authored test, an authenticated recording or a test run needs to sign in, then Vantage uses them automatically.
4. Given the session expires during discovery, when Vantage notices, then it signs in again and carries on.
5. Given an admin in Settings, when they save a new username and password for an application, then later work uses the new credentials; when they reveal a password, then the reveal is recorded in Activity.
6. Given an admin turns an application's Sign-in switch off in Settings, when discovery, Explorer or a test run next opens it, then it opens the application directly without logging in; given an admin later saves a username and password for it, then sign-in is switched back on.

## Gaps / not built

- **Saved browser session (single sign-on)** and **MFA code seed** have no screen; they can only be set up outside the user interface.
- **API-key and OAuth sign-in** for the application under test are not built.
- Credentials changed in Settings are not tested against the live application before being saved.
- Turning the Sign-in switch on or off is not recorded in Activity.
