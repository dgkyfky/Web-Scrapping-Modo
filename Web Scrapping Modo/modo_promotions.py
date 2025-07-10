"""
modo_promos_scraper.py  •  2025-06-14
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Collects every promo link from https://www.modo.com.ar/promos and builds a
DataFrame with detailed parameters for each promo.

Usage
-----
links = fetch_promo_links()
df    = build_promo_dataframe(links)

Columns returned
----------------
['link', 'titulo', 'foto', 'subtitulo', 'comercios',
 'store_names', 'store_addresses', 'vigencia', 'bancos',
 'tope_reintegro', 'tiempo_acreditacion', 'dias', 'canal']
"""

from __future__ import annotations
import time
from urllib.parse import urljoin
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager


# ─────────────────────────────────────────────────────────────────────────────
# 1.  GRAB ALL PROMO LINKS
# ─────────────────────────────────────────────────────────────────────────────
def fetch_promo_links(
    scroll_pause: int = 1,
    max_stalls: int = 2,
    headless: bool = True,
) -> list[str]:
    URL, BASE = "https://www.modo.com.ar/promos", "https://www.modo.com.ar"
    CSS_TARGET = ".w-full.h-auto"                     # promo cards = <div>

    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )

    try:
        driver.get(URL)
        time.sleep(2)

        helper = driver.find_element(
            By.XPATH, "//h3[normalize-space()='¿Necesitás ayuda?']"
        )

        seen, stalls, last_y = set(), 0, -1
        while stalls < max_stalls:
            y_before = driver.execute_script("return window.pageYOffset")
            driver.execute_script("window.scrollBy(0, window.innerHeight*0.8)")
            time.sleep(0.3)
            y_after = driver.execute_script("return window.pageYOffset")

            if y_after == y_before == last_y:
                break            # absolute bottom
            last_y = y_after

            top = driver.execute_script(
                "return arguments[0].getBoundingClientRect().top", helper
            )
            if 0 < top < driver.execute_script("return window.innerHeight") - 100:
                time.sleep(scroll_pause)
                for card in driver.find_elements(By.CSS_SELECTOR, CSS_TARGET):
                    href = card.get_attribute("href")
                    if href:
                        seen.add(urljoin(BASE, href))
                stalls = stalls + 1 if len(seen) == y_after else 0
        return sorted(seen)
    finally:
        driver.quit()


# ─────────────────────────────────────────────────────────────────────────────
# 2.  SCRAPE ONE PROMO PAGE
# ─────────────────────────────────────────────────────────────────────────────
def _parse_single_promo(driver, url):
    """
    Visit one promo URL and return a dict with all required fields.
    Immune to StaleElementReferenceException caused by live re-renders.
    """
    # ── local Selenium helpers ──────────────────────────────────────────
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver import ActionChains
    from selenium.common.exceptions import (
        NoSuchElementException, TimeoutException, StaleElementReferenceException
    )

    driver.get(url)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    rec = {
        "link": url,
        "titulo": None, "foto": None, "subtitulo": None,
        "comercios": None, "store_names": None, "store_addresses": None,
        "vigencia": None, "bancos": None, "tope_reintegro": None,
        "tiempo_acreditacion": None, "dias": None, "canal": None,
    }

    # ───────────────── headline ────────────────────────────────────────
    for css in ("h1", "label.styles__TextCard-sc-25khzf-6"):
        try:
            rec["titulo"] = driver.find_element(By.CSS_SELECTOR, css).text.strip()
            break
        except NoSuchElementException:
            pass

    try:
        rec["foto"] = driver.find_element(
            By.CSS_SELECTOR, "div.styles__ImageContainer-sc-25khzf-3 img"
        ).get_attribute("src")
    except NoSuchElementException:
        pass

    for css in ("h1 + p",
                "h3.styles_new_description_sub_header__AEMry span",
                "div.styles_container_sub_header__JpoUq"):
        try:
            t = driver.find_element(By.CSS_SELECTOR, css).text.strip()
            if t:
                rec["subtitulo"] = t
                break
        except NoSuchElementException:
            continue

    # ───────────────── parameter blocks ────────────────────────────────
    comercios_btn = None
    blocks = driver.find_elements(
        By.CSS_SELECTOR,
        "div.styles__ItemText-sc-25khzf-15,"
        "div.styles__ItemSubContainer-sc-waujo0-9"
    )

    def _safe_text(elem, selector) -> str:
        """return .text of `elem.find_element(selector)` or ''"""
        try:
            return elem.find_element(By.CSS_SELECTOR, selector).text.strip()
        except NoSuchElementException:
            return ""

    for blk in blocks:
        # label (two possible classes)
        label_txt = _safe_text(blk, "span.styles_sub_item__s3Aiz") or \
                    _safe_text(blk, "p.text-caption-regular")
        if not label_txt:
            continue
        label = label_txt.lower()

        # value text (three fall-backs)
        val = _safe_text(blk, "span.styles_sub_item_data__kKr1_") or \
              _safe_text(blk, "p.text-body-medium")
        if not val:
            ps = blk.find_elements(By.TAG_NAME, "p")
            val = ps[1].text.strip() if len(ps) >= 2 else ""

        # ——— Comercios ————————————————————————————
        if label.startswith("comercios"):
            rec["comercios"] = val or None
            if val.lower().startswith("ver listado"):
                try:
                    comercios_btn = blk.find_element(
                        By.XPATH, ".//p[contains(.,'Ver listado')]"
                    )
                except NoSuchElementException:
                    comercios_btn = None

        # ——— Vigencia ————————————————————————————
        elif label.startswith("vigencia"):
            rec["vigencia"] = val

        # ——— Bancos ——————————————————————————————
        elif label.startswith("bancos"):
            alts = []
            for img in blk.find_elements(By.TAG_NAME, "img"):
                try:
                    alt = img.get_attribute("alt")
                    if alt:
                        alts.append(alt.strip())
                except StaleElementReferenceException:
                    continue
            rec["bancos"] = alts or None

        # ——— Tope de reintegro ————————————————
        elif label.startswith("tope"):
            rec["tope_reintegro"] = val

        # ——— Tiempo de acreditación ————————————
        elif label.startswith("tiempo"):
            rec["tiempo_acreditacion"] = val

        # ——— Días (robust loop) ————————————————
        elif "usalo" in label:
            active = []
            for sp in blk.find_elements(By.CSS_SELECTOR, "span[aria-label]"):
                try:
                    if sp.get_attribute("aria-hidden") != "true":
                        active.append(sp.get_attribute("aria-label"))
                except StaleElementReferenceException:
                    continue
            rec["dias"] = active or None

        # ——— Canal ————————————————————————————
        elif label.startswith("desde la"):
            rec["canal"] = val

    # ───── optional “Ver listado” modal (safe) ───────────────────────────
    if (rec.get("comercios") or "").lower().startswith("ver listado") and comercios_btn:
        try:
            ActionChains(driver).move_to_element(comercios_btn).click().perform()
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     "section[data-testid='participating-stores-list']")
                )
            )
            sec = driver.find_element(
                By.CSS_SELECTOR, "section[data-testid='participating-stores-list']"
            )
            # store names
            names, addrs = [], []
            for p in sec.find_elements(By.CSS_SELECTOR,
                                       "p[data-testid='store-name']"):
                try:
                    names.append(p.text.strip())
                except StaleElementReferenceException:
                    continue
            for p in sec.find_elements(By.CSS_SELECTOR,
                                       "p[data-testid='store-address']"):
                try:
                    addrs.append(p.text.strip())
                except StaleElementReferenceException:
                    continue
            rec["store_names"] = names or None
            rec["store_addresses"] = addrs or None
            # close modal
            try:
                driver.find_element(
                    By.CSS_SELECTOR,
                    "button[data-testid='button-modal-close']"
                ).click()
            except NoSuchElementException:
                pass
        except (TimeoutException, StaleElementReferenceException):
            pass

    return rec


# ─────────────────────────────────────────────────────────────────────────────
# 3.  BUILD DATAFRAME FOR MANY PROMOS
# ─────────────────────────────────────────────────────────────────────────────
def build_promo_dataframe(urls: list[str], headless: bool = True) -> pd.DataFrame:
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )

    try:
        recs = []
        for i, u in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}]  {u}")
            recs.append(_parse_single_promo(driver, u))
        return pd.DataFrame(recs)
    finally:
        driver.quit()



# ─────────────────────────────────────────────────────────────────────────────
# 4.  DEMO
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    links = fetch_promo_links()
    print("Links found:", len(links))
    df = build_promo_dataframe(links)
    print(df.head())