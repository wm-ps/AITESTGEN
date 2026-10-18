# 1b. How Explorer actually does it, in plain words

> Picture: [Inside Explorer: the helpers](diagrams/explorer-inside-plain.html)
>
> [Document 1](01-explorer-in-plain-words.md) says **what** Explorer does. This page says **how**: the tricks behind each step, with no technical words.

## The helpers

Explorer is not one big AI that does everything. It is a small team, and each member is good at one thing:

| Helper | Think of it as | What it does |
|---|---|---|
| **Robot browser** | A pair of hands | A real web browser with no person in front of it. Explorer controls it: it opens pages, clicks buttons, types into boxes, and takes photos of the screen. |
| **AI brain** | A sharp new QA colleague | It looks at the photo of a screen and says what it means and what to do next. It comes in two sizes: a **careful thinker** for most decisions, and a **quick picker** only for "where should I look next?". |
| **Notebook** | A diary that never forgets | Every screen, photo, click, question, answer and test is written down the moment it happens. |
| **Conductor** | A project manager with a checklist | It knows which stage the run is in, starts the next job, and remembers the plan even if the computer restarts. |
| **Safe** | A locked drawer | It holds your app's login. The AI brain never sees the password; plain code types it in. |

Explorer itself is the worker that coordinates them. It takes a step from the conductor, uses the hands, asks the brain, and writes everything in the notebook.

---

## How it "sees" a screen

A person glances at a screen and understands it. Explorer does it in three moves:

1. **It takes a photo** of the screen.
2. **It makes a list of what's on the page**: every button, link, box, heading, table and message, and the first part of the text.
3. **It shows both to the AI brain** and asks: "What is this screen? What can you do here? Does anything look wrong?"

The brain answers in a fixed form, for example:

> *This is the **New claim form**. It has the fields Policy number, Date of loss and Description. Its buttons are Next and Cancel. The **Report a claim** link starts a task worth trying.*

## How it knows two pages are "the same screen"

Customer 1001's page and customer 1002's page look different, but they are the same *kind* of screen. Explorer gives every screen a **fingerprint** made of:

- **what the brain calls it** (for example "Customer details");
- **what kind of screen it is** (a list, a form, a detail page or a step in a wizard);
- **its web address with the numbers removed** (`/customers/1001` and `/customers/1002` both become `/customers/{id}`).

Same fingerprint means same screen, so a thousand customer pages count as **one**, and Explorer never gets lost going round in circles. When it comes back to a screen it already knows, it doesn't even ask the brain again. It reuses what it learned last time.

## How it decides where to go next

Explorer keeps a **to-do list of places to visit**. Each item gets an importance score from 1 to 5:

- the brain's suggestions ("the **Claims** menu looks central to this business") score higher;
- plain links found on the page score lowest;
- anything that **starts a task** ("Report a claim", "Add employee") gets a bonus.

Each time, the **quick picker** chooses the best place from the top 20. Things that are never put on the list: sign-out, links to other websites, file downloads, places already seen, and anything risky.

It stops looking around after about **24 new screens or 25 minutes**, whichever comes first.

## How it clicks and types

The robot browser finds buttons **the way a person would: by the words on them**. It tries an exact match on "Next" as a button, then as a link, then as text, and then looser matches.

For each step of a task, the careful thinker looks at the screen and decides:

- **what to type** in each box, using your test data first, then realistic made-up values;
- **what to choose** in dropdowns and radio buttons;
- **which file to upload**, if needed. Explorer carries its own sample photo, PDF and text files, so it never asks you for one;
- **which button to press** to move on.

After each click, Explorer **waits until the page stops changing** before looking again, just as you'd wait for a page to finish loading. If the same click does nothing twice, it gives up on that step and says it got stuck. Dates can be written as "today plus 3 days", and Explorer turns them into a real date, even working through calendar pop-ups.

## How it stays safe

This part is **not left to the AI**. It is a fixed list of words in the code:

- Buttons like **delete, pay, approve, reject, transfer, refund, sign out, cancel policy** always need your OK, everywhere.
- **Save, Submit and Send** are allowed only on a test environment, so Explorer can create its own test data. On a live production app it always asks first.
- It **never presses the same "final" button twice**.
- Before pressing anything on the list, Explorer creates a question, "May I press *Delete*?". Without your "yes" it stops just before the button.

## How it checks the app's health

While it moves around, the robot browser quietly notes problems the way a mechanic listens to an engine:

- pages that crash or never finish loading;
- server errors and broken links;
- error messages hidden behind the scenes;
- pages slower than 6 seconds.

Each problem gets **points off** the score, more for serious ones and more if it keeps happening. Everything starts at 100. Below 60, Explorer treats the app as unreliable and leans harder on what *you* tell it.

## How it writes the App Summary

Once it has looked around, it hands the brain **everything in the notebook**: every screen it understood and every choice it noticed. Then it asks for a one-page summary: what the app is, its key tasks, and up to 5 multiple-choice questions for you. Then it **stops and waits for you**. It can wait up to two weeks without using any computer power, because the conductor just keeps a bookmark.

## How a mission works

After you confirm, the brain turns the summary into a list of **6 to 15 missions**, most important first. For each mission:

1. **It writes down what *should* happen first**, from your answers, your documents and common sense. It does this before touching the app.
2. **It opens its own robot browser** and starts **video recording**.
3. It walks the task step by step, as described above. Any screen it has never seen during a "what if" mission (for example "what if someone is hurt?") is marked as a **hidden screen**, with a note on when it appears.
4. At the end, the brain compares **the final screen** with **what should have happened**. If they differ, it becomes a **possible bug**. A quiet "Is this a bug?" question is added next to it, and it never holds anything up.

**Three missions run at the same time**, each in its own browser. If an app keeps saved progress (drafts, a shopping cart), Explorer runs missions **one at a time**, so they don't trip over each other's draft.

## How it asks you, and waits only where needed

When a mission needs something only you know:

1. **It checks the notebook first.** If you, or anyone on your team, answered a similar question before, for this app and in any earlier run, it uses that answer and doesn't ask. "Similar" means most of the important words match.
2. Otherwise it creates the question, with a screenshot and clickable options, and **emails you**.
3. **Only that one mission pauses.** Its browser stays open on the exact screen while it checks for your answer every 5 seconds, for up to 10 minutes. All other missions keep going.
4. When you answer, the mission **carries on from exactly where it stopped**. If no answer comes, it carries on without it.

Every answer goes into the app's **memory**. Every later question to the brain, in this run and every future run, includes a page saying "here's what the user told us before, and it's trusted". Uploaded documents are cut into passages and stored the same way.

## How it finds hidden screens

After the missions, Explorer goes back to screens it knows and **pokes them on purpose**:

- **Every choice:** for each dropdown or radio question, it picks each option in turn and compares the list of visible labels before and after. New labels appearing means a hidden part was found, and it is recorded as "appears when *Married* is chosen".
- **Every size of number:** it types 1, 999, 15,000 and 1,000,000 into amount fields and watches for new sections, like an approval step.
- **"What if" the server misbehaves:** inside its *own* browser only, it intercepts the data coming back and pretends there are no records, that the server failed, that optional features are switched on, or that it is a year from now. **Your real server never sees any of this.** If a page goes blank when the server fails, that is also noted as a possible bug.

## How it proves a test is good

This is the most careful part. A test must survive four checks:

1. **Do it once, with the AI driving.** The robot browser performs the test while Explorer **records every exact click and every word typed**, like a macro recorder.
2. **Pick a proof.** The brain picks something on the final screen that shows the test worked: a message like *"Claim submitted"*, or a change in the web address. **The proof must not have been on screen before the test started**, or it doesn't prove anything.
3. **Replay it 3 times with no AI at all.** A plain replay robot repeats the recorded clicks. The proof must appear **every** time, otherwise the test is unreliable and is thrown away.
4. **Replay it once with the key click removed.** The proof must now **not** appear. This proves the test can tell the difference between working and broken. A test that passes even when broken is useless, and it is thrown away.

What's left is either:

- a **proven test**: the app behaved as it should;
- or a **known-bug test**: the app did something it shouldn't. The correct test is kept and marked "expected to fail until the bug is fixed".

Each test is turned into standard **Playwright** code, the format Vantage runs. A video of the replay is kept so you can watch it.

## How it never loses work

Everything is in the notebook the moment it happens, and the conductor keeps a bookmark of the current stage. So:

- **Pause** stops everything cleanly. **Resume** reads the notebook, works out how far it got, puts any half-finished mission back in the queue, and continues. Nothing finished is redone.
- If a computer restarts mid-mission, that mission is retried once automatically.
- If one mission or test crashes, the others carry on, and the crashed one is clearly marked with the reason.

## How the results reach the rest of Vantage

When testing finishes, Explorer **copies its proven tests into Vantage's normal places**. Each starting screen becomes a journey, and each test becomes a scenario. When you press **Generate tests**, Vantage reuses the **exact code Explorer already proved**, instead of writing new code from scratch.

## In one paragraph

Explorer pairs a **robot browser** (the hands) with an **AI brain** (the judgment). It writes everything into a **notebook** (the memory) while a **conductor** keeps the plan. The AI decides *what things mean* and *what to try next*. Plain code handles everything that must be exact or safe: logins, the dangerous-button list, health scoring, replaying tests, and proof checks. Most importantly, Explorer decides **what should happen before it looks at what does happen**, so it finds bugs instead of copying them into tests.
