"""An export's proof is the file it downloads — seen by Explorer and checked
the same way by the exported test."""

from explorer_worker.browser import Eyes
from explorer_worker.testkit import holds, playwright_code
from explorer_worker.tests_stage import proof_was_there_before

PAGE = '<a href="data:text/csv,name%0AAcme" download="accounts.csv">Export as CSV</a>'


async def test_a_download_proves_an_export() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        eyes.mark_calls()
        check = {"kind": "download", "value": ".csv"}
        assert not await holds(eyes, check, wait_ms=500)  # nothing downloaded yet
        await eyes.page.click("text=Export as CSV")
        assert await holds(eyes, check, wait_ms=3000)
        assert "Downloaded a file: accounts.csv" in eyes.messages_since_mark()
        eyes.mark_calls()  # the next test starts with nothing downloaded
        assert not await holds(eyes, check, wait_ms=500)
    finally:
        await eyes.close()
    assert not proof_was_there_before(check, "", "", None)
    code = playwright_code("Export downloads the list", [], [], check, "x")
    assert "page.on('download'" in code and 'includes(".csv")' in code
