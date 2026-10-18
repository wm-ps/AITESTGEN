# 1. Explorer in plain words

> Diagram: [How Explorer works, in plain words](diagrams/explorer-plain-flow.html)

## The problem it solves

The old Vantage discovery worked like someone who had never seen the app and clicked every link in order, typing "Test value" into every box. That approach:

- **missed screens that only appear sometimes.** Examples are an approval step above a certain amount, a "spouse details" step when you pick *Married*, an empty "No records found" page, and error pages;
- **got stuck** on screens that need real business data, such as a valid policy number;
- **wrote tests that guessed** what should happen instead of knowing.

## What Explorer is

Explorer behaves like **a sharp new QA engineer in their first week**. It learns the app, checks its understanding with you, and then tests the app on purpose. It never treats whatever the app does as "correct". The app might have bugs, and a tester who copies a bug into a test just protects the bug.

## The journey, step by step

### 1. You add your app and press Start

You give Vantage the app's address and its login. That login is kept in a secure vault. In the Explorer tab you press **Start exploring**. When Explorer is the discovery engine (the default), adding a new application starts it automatically.

### 2. Explorer gets to know the app

- It **signs in** with the saved login.
- It **looks around with purpose**. For each screen it takes a picture and reads the page, then names the screen by what it *means*, for example "Customer details" or "New claim form". A thousand different customer pages count as **one** screen, so it never gets lost.
- It chooses where to look next by **business importance**, not by link order.
- When a screen offers a task like "Report a claim", it **walks through the task** step by step and fills in realistic data. It notes every choice that probably changes the path.
- It **stops before anything real**: sending, paying, deleting, approving.
- It quietly runs a **health check**: crashes, server errors, broken links, slow screens. These give a 0–100 health score. Below 60, Explorer becomes more careful and relies more on what you tell it.

It looks at up to about 24 distinct screens or 25 minutes, whichever comes first.

### 3. You check the App Summary

Explorer writes a short **App Summary**: what the app is, the key tasks it will test, and a few multiple-choice questions for you. You can:

- fix anything that's wrong;
- answer the questions by clicking an option;
- say what to focus on and which screens to leave out;
- press **Looks right — confirm**.

**Nothing else happens until you confirm.** That is your consent to what Explorer will test against.

### 4. Explorer tries every path

Explorer turns the summary into a to-do list of **missions** (6 to 15). There are four kinds:

- **Key tasks:** complete a business task end to end.
- **Hidden branches:** take a different choice that probably changes the path.
- **New areas:** visit parts of the app it hasn't seen yet.
- **Rule checks:** deliberately test a business rule.

Before each mission, Explorer writes down **what should happen**, based on your answers, your documents and common sense. Up to **three missions run at the same time**, each in its own browser that is video-recorded. At the end it compares what happened with what should have happened. A mismatch becomes a **possible bug**.

### 5. Explorer asks only when it must

Explorer asks you only when the answer really matters:

- **Test data it can't invent**, like a real policy number.
- **Your OK** before a risky button, like "Delete" or "Pay".
- **"Is this a bug?"** when the app did something unexpected. These questions never hold anything up. They sit next to the finding they are about.

Only the one mission that asked waits for you; everything else keeps going. Explorer also **remembers every answer for this app, forever**. It never asks the same thing twice, not even on the next run. You can upload requirement documents (PDF, Word, text), and Explorer treats them as trusted knowledge too. If Explorer needs you, it emails the person who started the run.

### 6. Explorer hunts for hidden screens

After the missions, Explorer goes back to screens it knows and tries to make hidden parts appear:

- It tries **every option** of dropdowns and radio buttons.
- It tries **small and very large amounts**.
- It **pretends, inside its own browser only**, that the server returned nothing, returned an error, switched on optional features, or that it is a year from now. The real server is never touched.

It can also check **who can see what**. If you add other kinds of users, such as a viewer or an admin, Explorer tries every screen as each of them. It also finds **pages nothing links to** and reports **how much of the app's code it actually ran**.

### 7. Explorer writes tests and proves them

Tests come in **five kinds** only:

- navigation
- validation
- error states
- data loading
- form submission

Explorer also adds simple page-quality checks: does the page load cleanly, are any images broken, does it fit a phone screen, does every field have a label.

Every test must pass three bars, or it is thrown away. You only ever see tests that passed all three:

1. **Do it once for real** in a browser, recording the exact clicks and typing.
2. **Replay it three times without any AI.** It must give the same result every time.
3. **Replay it with the key step removed.** It must **fail**. This proves the test can actually catch a problem.

If the app does something different from what it *should*, the correct test is kept and labelled **"Known bug: expected to fail"**. Explorer never writes a test that protects a bug.

### 8. You get the results

- **Scenarios tab:** every proven test with its steps, its expected result, a screenshot, and a video of it running.
- **"Things that look wrong":** the possible bugs, kept quiet and folded until you open them.
- **Tests in Vantage:** proven tests flow into the normal Vantage test suite. There, "Generate tests" turns them into a runnable Playwright project, using the exact code Explorer already proved.

## What you'll see while it runs

The Explorer tab opens on **Live**: a picture of what the browser is doing right now, a running activity log, and the progress of the four stages ("Learning the app", "Your check", "Trying every path", "Writing scenarios"). Anything waiting on you pulses and links straight to the **Questions** tab. You can **Pause** a run at any time and **Resume** it later from where it stopped. Nothing finished is lost.

## What Explorer will never do

- Press delete, pay, approve, reject, transfer, sign-out and similar buttons without your OK. This applies in every environment.
- Save anything on a **production** app. On a test environment it may press Save or Submit so it can create its own test data.
- Answer a question or confirm the summary on your behalf.
- Treat "the app did it" as proof that it is right.
