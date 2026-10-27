---
last_updated: 2026-10-27
---

# Story 2.23: Validate Login Before Discovery Starts

Status: done

> This check runs before **both** discovery engines: it applies to applications discovered by Explorer (Epic 8) as well as by the classic engine, and it still uses the classic engine's background service to do the sign-in.

## Story

As a member or admin adding an application that needs sign-in,
I want Vantage to prove my test credentials actually work before it starts Discovery,
so that a typo in a password doesn't waste a whole Discovery run that can only explore the login page.

## What it does today

- **When it runs.** The check happens when the user clicks **Start discovery** on Add application, with "This application requires sign-in" turned on and "Autonomous discovery" checked. It's skipped for apps without sign-in, and for apps added without Discovery ("Add application").
- **How it checks.** Vantage opens a real browser and tries to sign in with the details entered. It uses the login URL if one was given; otherwise it starts from the application URL and follows a sign-in link. The button reads "Validating credentials" with trailing bouncing dots while this happens.
- **Three possible results:**
  - **Valid:** the password field went away and no error text appeared. The application is created and Discovery starts.
  - **Invalid:** the login form is still showing *and* the application displayed a wrong-credentials message. The user sees: "The username or password is incorrect. Enter valid credentials and click Start discovery again." Nothing is created.
  - **Can't tell:** anything else, for example a slow app, no login form found, unfamiliar wording, a timeout, or the check service being unavailable. The user sees: "We couldn't confirm these credentials. Click Start discovery to validate again." Nothing is created.
- Vantage never says "incorrect" unless the application itself said so. Discovery never starts on a login that hasn't been proven to work.
- The whole check takes about two and a half minutes at most.
- The credentials used for the check are held only temporarily. Once the application is created, they are stored encrypted.

## Acceptance criteria

1. **Given** sign-in is required and Discovery is on, **when** the user clicks Start discovery, **then** the credentials are tried in a real browser before the application is created.
2. **Given** the login succeeds, **then** the application is created and Discovery starts.
3. **Given** the application shows a wrong-credentials message and the form is still there, **then** the "username or password is incorrect" message is shown and nothing is created.
4. **Given** the result can't be confirmed for any reason, **then** the "We couldn't confirm these credentials" message is shown, nothing is created, and the user can try again.
5. **Given** the app needs no sign-in, or Discovery is off, **then** no check runs.

## Gaps / not built

- Wrong-credential messages are only recognised in English and in common error-message styles. An app that words or places its error differently gets "We couldn't confirm" instead of "incorrect".
- The check is enforced by the Add application screen only. The server doesn't insist on a passed check before starting Discovery.
- Credentials an admin changes later in Settings aren't checked again.
