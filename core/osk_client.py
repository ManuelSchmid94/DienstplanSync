"""
Playwright-based automation for OSK DPlan.
Runs in a dedicated thread – never call Qt APIs from here.
"""
import re
import logging
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, Page, Download, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

BASE_URL = "https://dplan.oberschwabenklinik.de"
LOGIN_URL = f"{BASE_URL}/login.aspx"
HOURS_URL = f"{BASE_URL}/WebForms/AusfuehrlicherStundennachweis.aspx"


class OSKAuthError(Exception):
    pass


class OSKNavigationError(Exception):
    pass


def _wait_for_login(page: Page) -> None:
    """Confirm we actually landed on an authenticated page after submit."""
    try:
        page.wait_for_url(re.compile(r"WebForms|Default|Start", re.I), timeout=15_000)
    except PWTimeout:
        # Check for login error messages
        error_selectors = [
            "span[id*='Error']",
            "span[id*='error']",
            ".error",
            "#lblMessage",
        ]
        for sel in error_selectors:
            el = page.query_selector(sel)
            if el and el.inner_text().strip():
                raise OSKAuthError(f"Login fehlgeschlagen: {el.inner_text().strip()}")
        raise OSKAuthError("Login fehlgeschlagen – Seite nicht weitergeleitet.")


def _click_by_candidates(page: Page, candidates: list[str], description: str) -> None:
    """Try each selector candidate and click the first one found."""
    for sel in candidates:
        try:
            el = page.wait_for_selector(sel, timeout=5_000, state="visible")
            if el:
                el.click()
                logger.debug("Geklickt: %s via '%s'", description, sel)
                return
        except PWTimeout:
            continue
    raise OSKNavigationError(f"Element nicht gefunden: {description}")


def download_pdf(
    username: str,
    password: str,
    output_path: Path,
    log: Callable[[str], None],
    headless: bool = True,
) -> Path:
    """
    Full automation pipeline:
      1. Login
      2. Navigate to AusfuehrlicherStundennachweis
      3. Click "Monat vor" (next month)
      4. Open Druckansicht
      5. Download PDF
    Returns the saved PDF path.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # ── 1. Login ──────────────────────────────────────────────────────────
        log("Öffne Login-Seite…")
        page.goto(LOGIN_URL, wait_until="networkidle")

        # Username field — try multiple ASP.NET naming patterns
        user_candidates = [
            "input[id*='user' i]",
            "input[id*='User']",
            "input[name*='user' i]",
            "input[id*='login' i]",
            "input[id*='Login']",
            "input[type='text']",
        ]
        _click_by_candidates(page, user_candidates, "Benutzername-Feld")
        page.keyboard.type(username)

        pw_candidates = [
            "input[type='password']",
            "input[id*='pass' i]",
            "input[id*='kennwort' i]",
        ]
        _click_by_candidates(page, pw_candidates, "Passwort-Feld")
        page.keyboard.type(password)

        submit_candidates = [
            "input[type='submit']",
            "button[type='submit']",
            "input[id*='login' i]",
            "input[id*='Login']",
            "button[id*='login' i]",
        ]
        log("Sende Login-Daten…")
        _click_by_candidates(page, submit_candidates, "Login-Button")
        _wait_for_login(page)
        log("Login erfolgreich.")

        # ── 2. Navigate to Stundennachweis ────────────────────────────────────
        log("Navigiere zu Ausführlicher Stundennachweis…")
        page.goto(HOURS_URL, wait_until="networkidle")
        page.wait_for_load_state("domcontentloaded")

        # ── 3. Click "Monat vor" (previous/next month button) ─────────────────
        # OSK DPlan typically uses "Monat vor" meaning "one month forward in
        # the display" (the coming month). Selector covers common ASP.NET patterns.
        monat_candidates = [
            "input[value*='Monat vor']",
            "a:has-text('Monat vor')",
            "button:has-text('Monat vor')",
            "input[value*='nächster']",
            "input[value*='Vorwärts']",
            "#btnMonatVor",
            "input[id*='MonatVor']",
            "input[id*='monatvor' i]",
        ]
        log("Wechsle zum nächsten Monat…")
        _click_by_candidates(page, monat_candidates, "Monat-vor-Button")
        page.wait_for_load_state("networkidle")

        # ── 4. Open Druckansicht ──────────────────────────────────────────────
        druck_candidates = [
            "input[value*='Druckansicht']",
            "a:has-text('Druckansicht')",
            "button:has-text('Druckansicht')",
            "input[id*='druck' i]",
            "a[href*='druck' i]",
            "a[href*='print' i]",
            "input[value*='Drucken']",
        ]
        log("Öffne Druckansicht…")

        # Some sites open print view in a new tab – handle both cases.
        # expect_page must wrap only the click; its .value is read after the with-block.
        print_page = page
        try:
            with context.expect_page(timeout=8_000) as new_page_info:
                _click_by_candidates(page, druck_candidates, "Druckansicht-Button")
            print_page = new_page_info.value
            print_page.wait_for_load_state("networkidle")
        except PWTimeout:
            # No new tab was opened – print view loaded in the same page
            page.wait_for_load_state("networkidle")

        # ── 5. Download PDF ───────────────────────────────────────────────────
        pdf_downloaded = False

        # Strategy A: look for a PDF download link
        pdf_link_candidates = [
            "a[href$='.pdf']",
            "a[href*='pdf' i]",
            "input[value*='PDF']",
            "a:has-text('PDF')",
        ]
        for sel in pdf_link_candidates:
            try:
                el = print_page.query_selector(sel)
                if el:
                    log("Lade PDF herunter…")
                    with print_page.expect_download(timeout=30_000) as dl_info:
                        el.click()
                    dl: Download = dl_info.value
                    dl.save_as(str(output_path))
                    pdf_downloaded = True
                    log(f"PDF gespeichert: {output_path.name}")
                    break
            except Exception:
                continue

        # Strategy B: use browser print-to-PDF via CDP
        if not pdf_downloaded:
            log("Nutze Browser-PDF-Export…")
            pdf_bytes = print_page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
            )
            output_path.write_bytes(pdf_bytes)
            log(f"PDF gespeichert: {output_path.name}")

        context.close()
        browser.close()

    return output_path
