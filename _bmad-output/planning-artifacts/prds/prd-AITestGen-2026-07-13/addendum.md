# Addendum: Application Intelligence Platform PRD

Depth that belongs to the broader product story but doesn't earn a place in the V1 execution PRD. Useful for architecture, sales enablement, and future V2/V3 PRDs.

## Competitive Positioning (from Product Brief)

V1 does not win on a unique technical edge. Autonomous, URL-only discovery that generates tests without source code access is already claimed by several players: **Virtuoso QA**, **QA.tech**, and **Autonoma AI** among them. Any V1 pitch leaning on "we can discover your app from just a URL" is making a claim the market has already heard.

What V1 actually offers is a different *shape* of product: competitors that discover autonomously still frame themselves as test-automation tools — discovery serves the tests. This platform inverts that: the business capability map and journey understanding are the product; generated Playwright tests are one output among several. No competitor identified in the brief's market research combines business-capability language, journey-level understanding, coverage analytics, and risk scoring into a single intelligence layer the way this platform intends to. That framing, plus the human-in-the-loop review step (AI-discovered journeys as draft, not ground truth), is what V1 sells on.

## V2 / V3 Vision Arc

The platform grows along: **coverage intelligence → application intelligence → change intelligence.**

- **V1** proves business journeys can be discovered and turned into working regression coverage without anyone having to remember they exist.
- **V2** adds source-code correlation — every Journey traces back to the routes, components, and dependencies that implement it, turning the map from a picture of behavior into a picture of structure *and* behavior. This is the point at which competitors without source access lose parity.
- **V3** closes the loop: given a code change, the platform tells a team which Business Journeys are at risk and which tests to run before shipping — release-readiness intelligence no competitor in this market currently offers (per brief research). This is the strongest, most defensible part of the long-term vision, and the reason early pilots are likely being sold as much on the roadmap as on V1 itself.

Long-term destination: the system of record for Application Intelligence — the place engineering leaders, QA directors, architects, and product owners go to understand what's built, what's changed, and what's at risk before every release. Not yet earned — contingent on V1 holding up in real pilots and V2's technical differentiation proving out.

## Confidence/Risk Scoring — Why It Was Cut From V1 (and how to revisit)

During PRD discovery, both the per-Journey AI discovery confidence score and the Stage-8 risk/confidence scorecard (explicitly named in the approved brief as a V1 outcome) were cut. The reasoning:

- The brief's scorecard definition uses "usage" and "error rates" as inputs — in a normal reading, these imply live production telemetry, which V1 does not ingest (discovery is a point-in-time crawl, not continuous observation).
- Once that dependency surfaced, resolving it raised more unresolved sub-questions (what counts as a feed, who provides it, how is it kept fresh) than the feature's value justified for a first release.

**If revisiting for V2 or a V1 fast-follow:** the per-Journey discovery confidence score does *not* strictly require a production feed — it could be computed purely from discovery-time signals (e.g., consistency of the navigation pattern across the crawl, clarity/uniqueness of the matched API calls). That's a smaller, self-contained feature that could be reintroduced without waiting for a telemetry integration. The full risk/confidence *scorecard*, by contrast, genuinely wants usage and error-rate data and is more naturally a V2+ feature once source-code correlation or a customer telemetry integration exists.

## Success Criteria — Full Reasoning (from Product Brief)

The brief deliberately avoids setting numeric coverage or time-saved targets for V1: "a percentage invented now would be a fabricated claim, not a real success criterion." The intended sequence is pilot data first, thresholds second — not the reverse. This is why §7 of the PRD reads as qualitative/directional rather than quantitative, and why Open Question 2 (V2 greenlight threshold) is deliberately still open rather than pre-answered.
