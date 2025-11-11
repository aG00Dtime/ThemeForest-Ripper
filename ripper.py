import os
import sys

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def build_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    return webdriver.Chrome(options=options)


def get_preview_url(driver, item_url):
    driver.get(item_url)
    WebDriverWait(driver, 20).until(lambda d: 'Just a moment' not in d.title)
    preview_link = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="full_screen_preview"]'))
    )
    return preview_link.get_attribute('href')


def get_full_frame_url(driver, preview_url):
    driver.get(preview_url)
    WebDriverWait(driver, 20).until(lambda d: 'Just a moment' not in d.title)
    frame = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe.full-screen-preview__frame'))
    )
    return frame.get_attribute('src')


def main():
    if len(sys.argv) != 3:
        print('Usage: python3 ripper.py <theme-url> <download-location>')
        sys.exit(1)

    source = sys.argv[1]
    destination = sys.argv[2]

    os.makedirs(destination, exist_ok=True)

    if "full_screen_preview" in source:
        preview_url = source
        print(preview_url)
    else:
        driver = build_driver()
        try:
            preview_url = get_preview_url(driver, source)
            print(preview_url)
        finally:
            driver.quit()

    driver = build_driver()
    try:
        full_frame_url = get_full_frame_url(driver, preview_url)
        print(full_frame_url)
    finally:
        driver.quit()

    command = ["wget", "-e", "robots=off", "-P", destination, "-m", full_frame_url]
    os.system(' '.join(command))


if __name__ == '__main__':
    main()
