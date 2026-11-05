import asyncio
import os
from playwright.async_api import async_playwright

OUT_DIR = r"c:\Users\Lenovo\Downloads\SocketScale_Project_Completed (1)\SocketScale\report_assets"
os.makedirs(OUT_DIR, exist_ok=True)

async def capture_all():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True
        )
        context = await browser.new_context(viewport={"width": 1440, "height": 960})
        page = await context.new_page()

        print("[1] Opening login page...")
        await page.goto("http://localhost:8080", wait_until="networkidle")
        await page.screenshot(path=os.path.join(OUT_DIR, "01_login_screen.png"), full_page=True)
        print("  -> Captured 01_login_screen.png")

        print("[2] Logging in as admin...")
        await page.fill('input[placeholder="Enter username"]', "admin")
        await page.fill('input[placeholder="Enter password"]', "AdminPass123!")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2500)

        print("[3] Capturing Admin Overview...")
        await page.screenshot(path=os.path.join(OUT_DIR, "02_admin_overview.png"), full_page=True)
        print("  -> Captured 02_admin_overview.png")

        print("[4] Capturing Gateway Cluster & Elastic Scaling...")
        await page.locator("nav button").filter(has_text="Gateway Nodes").click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=os.path.join(OUT_DIR, "03_gateway_cluster_nodes.png"), full_page=True)
        print("  -> Captured 03_gateway_cluster_nodes.png")

        print("[5] Capturing Infrastructure Health...")
        await page.locator("nav button").filter(has_text="Infrastructure").click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=os.path.join(OUT_DIR, "04_infrastructure_health.png"), full_page=True)
        print("  -> Captured 04_infrastructure_health.png")

        print("[6] Capturing Fault Tolerance Lab...")
        await page.locator("nav button").filter(has_text="Fault Tolerance Lab").click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=os.path.join(OUT_DIR, "05_fault_tolerance_lab.png"), full_page=True)
        print("  -> Captured 05_fault_tolerance_lab.png")

        print("[7] Capturing Dynamic Benchmarks...")
        await page.locator("nav button").filter(has_text="Dynamic Benchmarks").click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=os.path.join(OUT_DIR, "06_dynamic_benchmarks.png"), full_page=True)
        print("  -> Captured 06_dynamic_benchmarks.png")

        print("[8] Capturing System Event Logs...")
        await page.locator("nav button").filter(has_text="System Logs").click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=os.path.join(OUT_DIR, "07_system_event_logs.png"), full_page=True)
        print("  -> Captured 07_system_event_logs.png")

        print("[9] Capturing Live Chat Interface...")
        await page.locator("nav button").filter(has_text="User Chat").click()
        await page.wait_for_timeout(2000)
        try:
            msg_input = page.locator('input[placeholder="Type a message..."]')
            if await msg_input.is_visible():
                await msg_input.fill("System verified: Real-time distributed WebSocket message delivery active.")
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(1500)
        except Exception as e:
            print("  Note on message send:", e)

        await page.screenshot(path=os.path.join(OUT_DIR, "08_live_user_chat.png"), full_page=True)
        print("  -> Captured 08_live_user_chat.png")

        await browser.close()
        print("[DONE] All screenshots successfully generated!")

if __name__ == "__main__":
    asyncio.run(capture_all())
