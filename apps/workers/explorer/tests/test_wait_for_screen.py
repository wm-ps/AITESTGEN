"""A step that makes no move and isn't done ("the list is still loading, I'll
wait") looks again, up to IDLE_LOOKS times, instead of ending the walk — a
walk once stopped on a loading list and never reached the rest of the task."""

from explorer_worker.pursue import IDLE_LOOKS, waiting_for_screen


def test_no_move_and_not_done_looks_again_a_few_times() -> None:
    waiting = {"thought": "Still loading, I'll wait", "advance": None, "done": False}
    assert IDLE_LOOKS == 3
    assert all(waiting_for_screen(waiting, n) for n in range(IDLE_LOOKS))
    assert not waiting_for_screen(waiting, IDLE_LOOKS)  # then it ends, as before


def test_a_move_or_done_is_never_a_wait() -> None:
    assert not waiting_for_screen({"advance": "Open in studio", "done": False}, 0)
    assert not waiting_for_screen({"advance": None, "done": True}, 0)


def test_done_on_a_loading_screen_still_looks_again() -> None:
    # The Contacts walk: "the Dashboard hasn't loaded, I can't start" ended the walk.
    gave_up = {"advance": None, "done": True}
    assert waiting_for_screen(gave_up, 0, loading=True)
    assert not waiting_for_screen(gave_up, IDLE_LOOKS, loading=True)


async def test_a_screen_is_read_only_after_its_spinner_stops() -> None:
    from explorer_worker.browser import Eyes

    # The app's frame comes first; a CSS spinner (no page changes) for 1.5s, then the menu.
    page = """
    <style>@keyframes spin { to { transform: rotate(360deg) } }
      .ring { width: 24px; height: 24px; border: 3px solid #000; animation: spin 1s linear infinite }</style>
    <header>Denali</header><main id="m"><div class="ring"></div></main>
    <script>setTimeout(() => { document.getElementById('m').innerHTML = '<a href="#c">Contacts</a>'; }, 1500)</script>
    """
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(page)
        visit = await eyes.look(eyes.page.url, None, 0)
    finally:
        await eyes.close()
    assert "Contacts" in visit.inventory["body_text"]
