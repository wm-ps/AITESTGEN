"""Typing into a chat / rich-text box whose placeholder is drawn from an
attribute (an AI assistant's "Ask a question..." box is a contenteditable
<div> named "Chat input"): it used to find nothing, so "Send" went out empty."""

from explorer_worker.browser import Eyes

PAGE = (
    '<input type="search" placeholder="Search">'
    '<div contenteditable="true" role="textbox" aria-label="Chat input" '
    'data-placeholder="Ask a question..." style="min-height:20px"></div>'
)


async def test_types_into_a_box_whose_placeholder_is_drawn() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        assert await eyes.fill_field("Ask a question...", "ai")
        assert await eyes.page.get_by_role("textbox", name="Chat input").inner_text() == "ai"
        assert eyes.last_locator and eyes.last_locator["by"] == "css"
        # A field with a real placeholder is still found the way it always was.
        assert await eyes.fill_field("Search", "WebGenAI")
        assert eyes.last_locator == {"by": "placeholder", "text": "Search"}
        assert not await eyes.fill_field("Nothing like this", "x")
    finally:
        await eyes.close()
