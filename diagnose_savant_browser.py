#!/usr/bin/env python3
"""Inspect the browser-side data requests used by NFL/Savant's pass-rush leaderboard."""
import asyncio
from playwright.async_api import async_playwright

URL = "https://www.nflsavant.com/leaderboard?season=2026&tab=pressure"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        seen = []
        page.on("response", lambda response: seen.append(response))
        await page.goto(URL, wait_until="networkidle", timeout=90000)
        await page.wait_for_timeout(5000)
        print(f"SAVANT_BROWSER_TITLE={await page.title()}")
        print(f"SAVANT_BROWSER_URL={page.url}")
        print(f"SAVANT_RENDERED_TEXT={(await page.locator('body').inner_text())[:5000]!r}")
        print("SAVANT_NETWORK_RESPONSES_BEGIN")
        for response in seen:
            request = response.request
            if request.resource_type in ("xhr", "fetch", "document") or any(x in response.url.lower() for x in ("api", "json", "csv", "leaderboard")):
                try:
                    body = await response.body()
                    preview = body[:1200].decode("utf-8", "replace")
                except Exception as exc:
                    preview = f"<body unavailable: {exc}>"
                    body = b""
                print({
                    "url": response.url,
                    "status": response.status,
                    "type": request.resource_type,
                    "content_type": response.headers.get("content-type", ""),
                    "bytes": len(body),
                    "preview": preview,
                })
        print("SAVANT_NETWORK_RESPONSES_END")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
