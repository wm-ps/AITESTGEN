"""Authoring: test cases from a user's request, built by the existing Explorer.

A separate path. Explorer's own stages (understand, missions, build and prove)
are called as they are; only what differs lives here:
- request.py: read the request (the flow, the scenarios asked for, questions);
- plan.py:    missions and scenarios for exactly that request, nothing else;
- promote.py: the proven scenarios are ADDED as test cases ("Authored by
              prompt"), never replacing Explorer's or another request's;
- workflow.py: the order of it all, then test-case generation.
A run is an authoring run when `ExplorerRun.prompt` is set.
"""
