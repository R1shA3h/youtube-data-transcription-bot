from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
import time
import json
import os
import platform
import subprocess
import sys
import traceback
import logging
import urllib.request
import zipfile
import shutil
import glob
import warnings
import functools
import random
import importlib.util
import math
import re

# Configure logging with more structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Create a logger
logger = logging.getLogger('eightify_scraper')
selenium_logger = logging.getLogger('selenium')
selenium_logger.setLevel(logging.CRITICAL)

# Check if selenium-stealth is installed, if not try to install it
try:
    from selenium_stealth import stealth
    has_stealth = True
except ImportError:
    has_stealth = False
    logger.warning("selenium-stealth not found. Will attempt to install it.")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "selenium-stealth"])
        from selenium_stealth import stealth
        has_stealth = True
        logger.info("Successfully installed selenium-stealth")
    except Exception as e:
        logger.error(f"Failed to install selenium-stealth: {e}")
        logger.warning("Will continue without stealth mode. Detection risk is higher.")

# Constants
WAIT_TIME_LOAD = 15
WAIT_TIME_EXTENSION = 10
WAIT_TIME_PROCESSING = 20
WAIT_TIME_TAB_CONTENT = 5
WAIT_TIME_ALL_CONTENT = 10
WAIT_TIME_RECOVERY = 3
MIN_CONTENT_LENGTH = 50

# Eightify tab types
TAB_TYPES = [
    "key_insights",
    "timestamped_summary",
    "top_comments",
    "transcript"]

# Selectors
IFRAME_SELECTORS = [
    "#eightify-iframe",
    "iframe[title*='Eightify']",
    "iframe[src*='eightify']",
    "iframe.eightify",
    "iframe"  # Last resort: try all iframes
]

TAB_SELECTORS = ".SummaryTabsView_item__Zjswl, .SummaryTabsView_tabs__69LdY > div, button[role='tab'], .tab, div[role='tab']"

CONTENT_SELECTORS = [
    ".tab-content",
    ".SummaryTabsView_content__6OYs8",
    "[class*='content']",
    ".content",
    "[data-testid='content']",
    ".tab-panel",
    "[role='tabpanel']",
    "div[id*='panel']",
    "div[class*='panel']",
    "main",
    "body"
]

SUMMARIZE_BUTTON_SELECTORS = [
    "//button[contains(text(), 'Summarize Video')]",
    "//button[contains(text(), 'Summarize')]",
    "//button[contains(text(), 'Generate')]",
    "//button[.//span[contains(text(), 'Summarize')]]",
    "//div[@role='button' and contains(text(), 'Summarize')]",
    "button.SummaryButton_button__hMBbW",
    "button.summarize-button",
    "button.primary",
    "button.btn-primary",
    "button.cta",
    "div[role='button']"
]

CONTENT_SECTION_HEADERS = {
    "key_insights": ["Key Insights", "Main Points", "Key Points", "Highlights"],
    "timestamped_summary": ["Timestamped Summary", "Summary", "Video Summary", "Timeline"],
    "top_comments": ["Top Comments", "Comments", "User Comments", "Best Comments"],
    "transcript": ["Transcript", "Full Transcript", "Video Transcript", "CC"]
}

# List of common user agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/110.0.1587.63",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/111.0.1661.54"
]

# Global driver that will stay in scope
global_driver = None

# Helper Functions for Selenium Operations

# Cache function results for optimization
def cache_result(func):
    """Cache function results to avoid redundant operations"""
    cache = {}
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]
    return wrapper


def apply_stealth_settings(driver):
    """Apply stealth settings to make automation harder to detect"""
    if has_stealth:
        try:
            stealth(
                driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
            logger.debug("Applied stealth settings to browser")
        except Exception as e:
            logger.error(f"Failed to apply stealth settings: {e}")


def find_elements_by_selector(driver, selector):
    """Find elements using CSS or XPath selector"""
    try:
        if selector.startswith("//"):
            # XPath selector
            return driver.find_elements(By.XPATH, selector)
        else:
            # CSS selector
            return driver.find_elements(By.CSS_SELECTOR, selector)
    except Exception as e:
        logger.error(f"Error finding elements with selector {selector}: {e}")
        return []


def wait_for_element(driver, selector, timeout=10, by_type=None):
    """Wait for element to be present and visible"""
    try:
        if by_type is None:
            by_type = By.XPATH if selector.startswith("//") else By.CSS_SELECTOR
        
        element = WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((by_type, selector))
        )
        return element
    except TimeoutException:
        logger.warning(f"Timed out waiting for element: {selector}")
        return None
    except Exception as e:
        logger.error(f"Error waiting for element {selector}: {e}")
        return None


def find_and_click_button_optimized(driver, selectors, purpose=None, wait_time=5):
    """
    Find and click a button using optimized selector prioritization with direct JavaScript
    """
    button_clicked = False
    purpose_str = f" {purpose}" if purpose else ""
    
    for selector in selectors:
        if button_clicked:
            break
                
        try:
            buttons = find_elements_by_selector(driver, selector)
            for button in buttons:
                try:
                    if button.is_displayed():
                        logger.info(f"Found button{purpose_str} with selector: {selector}")
                        
                        # Direct JavaScript click
                        driver.execute_script("arguments[0].click();", button)
                        
                        button_clicked = True
                        logger.info(f"Clicked button{purpose_str}")
                        
                        # Wait for page to stabilize
                        try:
                            WebDriverWait(driver, wait_time).until(
                                lambda d: d.execute_script("return document.readyState") == "complete"
                            )
                        except TimeoutException:
                            time.sleep(wait_time)
                        break
                except StaleElementReferenceException:
                    # Skip stale elements
                    continue
        except Exception as e:
            logger.error(f"Error with button selector {selector}{purpose_str}: {e}")

    if not button_clicked and purpose:
        logger.warning(f"Could not find button for {purpose}")
        
    return button_clicked


def find_and_click_button(driver, selectors, purpose=None, wait_time=5):
    """
    Try to find and click a button using a list of selectors
    """
    button_clicked = False
    purpose_str = f" {purpose}" if purpose else ""

    for selector in selectors:
        if button_clicked:
            break

        try:
            buttons = find_elements_by_selector(driver, selector)
            for button in buttons:
                if button.is_displayed():
                    logger.info(f"Found button{purpose_str} with selector: {selector}")
                    
                    # Direct JavaScript click
                    driver.execute_script("arguments[0].click();", button)
                    
                    button_clicked = True
                    logger.info(f"Clicked button{purpose_str}")
                    
                    # Wait for changes after clicking
                    try:
                        WebDriverWait(driver, wait_time).until(
                            lambda d: d.execute_script(
                                "return document.readyState"
                            ) == "complete"
                        )
                    except TimeoutException:
                        time.sleep(wait_time)
                    break
        except Exception as e:
            logger.error(f"Error with button selector {selector}{purpose_str}: {e}")

    if not button_clicked and purpose:
        logger.warning(f"Could not find button for {purpose}")

    return button_clicked


def find_iframe_and_switch(driver, iframe_selectors=IFRAME_SELECTORS):
    """
    Find the Eightify iframe and switch to it

    Args:
        driver: WebDriver instance
        iframe_selectors: List of CSS selectors to try

    Returns:
        bool: True if iframe was found and switched to, False otherwise
    """
    iframe_found = False

    for selector in iframe_selectors:
        try:
            iframes = driver.find_elements(By.CSS_SELECTOR, selector)
            logger.info(f"Found {len(iframes)} iframes with selector: {selector}")

            if iframes:
                for iframe in iframes:
                    try:
                        # Check if this iframe is visible and seems to be
                        # Eightify
                        if iframe.is_displayed() and (
                                iframe.get_attribute("id") == "eightify-iframe" or selector == "iframe"):
                            logger.info(f"Found potential Eightify iframe! ID: {iframe.get_attribute('id')}")
                            
                            # Switch to the iframe
                            driver.switch_to.frame(iframe)
                            iframe_found = True
                            
                            return True
                    except Exception as iframe_error:
                        logger.error(f"Error processing iframe: {iframe_error}")
        except Exception as selector_error:
            logger.error(f"Error with iframe selector {selector}: {selector_error}")

    return False


def switch_to_default_content(driver):
    """Safely switch back to main content"""
    try:
        driver.switch_to.default_content()
        return True
    except Exception as e:
        logger.error(f"Error switching to default content: {e}")
        return False


def extract_tab_content(driver, tab_type, content_selectors=CONTENT_SELECTORS):
    """
    Extract content from the current tab with optimized selector usage

    Args:
        driver: WebDriver instance
        tab_type: Type of tab being processed
        content_selectors: List of CSS selectors to try

    Returns:
        str: Extracted content or empty string if not found
    """
    # Try high-probability selectors first for faster results
    high_priority_selectors = content_selectors[:3]  # First 3 selectors are most likely
    remaining_selectors = content_selectors[3:]
    
    # First try the high priority selectors with shorter timeout
    for content_selector in high_priority_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, content_selector)
            for element in elements:
                if element.is_displayed():
                    content_text = element.text
                    if content_text and len(content_text) > MIN_CONTENT_LENGTH:
                        logger.info(f"Extracted content from {tab_type} tab with selector {content_selector} ({len(content_text)} chars)")
                        return content_text
        except Exception as selector_error:
            logger.error(f"Error with content selector {content_selector}: {selector_error}")
            continue

    # Try remaining selectors only if high priority ones failed
    for content_selector in remaining_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, content_selector)
            for element in elements:
                if element.is_displayed():
                    content_text = element.text
                    if content_text and len(content_text) > MIN_CONTENT_LENGTH:
                        logger.info(f"Extracted content from {tab_type} tab with selector {content_selector} ({len(content_text)} chars)")
                        return content_text
        except Exception as selector_error:
            logger.error(f"Error with content selector {content_selector}: {selector_error}")
            continue

    # If we still don't have content, try getting the entire body as last resort
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if body_text and len(body_text) > MIN_CONTENT_LENGTH:
            logger.info(f"Extracted content from {tab_type} tab using body ({len(body_text)} chars)")
            return body_text
    except Exception as body_error:
        logger.error(f"Error getting body text: {body_error}")

    return ""


def navigate_to_tab_and_extract(
        driver,
        tab_index,
        tab_type,
        tab_selector=TAB_SELECTORS):
    """
    Navigate to a specific tab and extract its content
    """
    try:
        # Find the tabs
        tabs = driver.find_elements(By.CSS_SELECTOR, tab_selector)
        if tab_index >= len(tabs):
            logger.warning(f"Not enough tabs found for {tab_type}, skipping")
            return ""

        tab = tabs[tab_index]
        logger.info(f"Processing tab #{tab_index}: {tab_type}")

        # Ensure tab is in view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
        time.sleep(0.5)
        
        # Click the tab with JavaScript
        logger.info(f"Clicking tab for: {tab_type}")
        driver.execute_script("arguments[0].click();", tab)
        
        # Wait for content to load
        time.sleep(2)
        
        # Extract content
        return extract_tab_content(driver, tab_type)

    except Exception as tab_error:
        logger.error(f"Error accessing tab {tab_index}: {tab_error}")
        return ""


def recover_iframe_context(driver, iframe_selector="#eightify-iframe"):
    """Attempt to recover iframe context after errors"""
    try:
        # First switch back to default content
        driver.switch_to.default_content()
        time.sleep(1)  # Brief pause needed here

        # Find the iframe again
        iframe = driver.find_element(By.CSS_SELECTOR, iframe_selector)
        driver.switch_to.frame(iframe)
        logger.info("Successfully switched back to iframe context")
        return True
    except Exception as recovery_error:
        logger.error(f"Failed to recover iframe context: {recovery_error}")
        return False


def click_summarize_button_in_tab(
        driver,
        tab_index,
        tab_type,
        tab_selector=TAB_SELECTORS):
    """Click the summarize button in a specific tab"""
    try:
        # Find the tabs
        tabs = driver.find_elements(By.CSS_SELECTOR, tab_selector)
        if tab_index >= len(tabs):
            logger.warning(f"Not enough tabs found for {tab_type}, skipping")
            return False

        tab = tabs[tab_index]

        # Ensure tab is in view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
        time.sleep(0.5)
        
        # Click the tab with JavaScript
        logger.info(f"Clicking tab for: {tab_type}")
        driver.execute_script("arguments[0].click();", tab)
        
        # Wait for tab to become active
        time.sleep(2)

        # Look for and click "Summarize Video" button
        return find_and_click_button(
            driver,
            SUMMARIZE_BUTTON_SELECTORS,
            purpose=f"'Summarize Video' in {tab_type} tab"
        )
    except Exception as tab_error:
        logger.error(f"Error clicking summarize button in tab {tab_index}: {tab_error}")
        return False


@cache_result
def get_chrome_version():
    """Get the version of Chrome installed on the system"""
    system = platform.system()
    try:
        if system == "Windows":
            # Try to get chrome version from the registry
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Google\Chrome\BLBeacon")
            version, _ = winreg.QueryValueEx(key, "version")
            return version
        elif system == "Darwin":  # macOS
            process = subprocess.Popen(
                ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'],
                stdout=subprocess.PIPE
            )
            version = process.communicate()[0].decode(
                'UTF-8').replace('Google Chrome', '').strip()
            return version
        elif system == "Linux":
            process = subprocess.Popen(
                ['google-chrome', '--version'],
                stdout=subprocess.PIPE
            )
            version = process.communicate()[0].decode(
                'UTF-8').replace('Google Chrome', '').strip()
            return version
    except Exception as e:
        logger.error(f"Could not determine Chrome version: {e}")

    return None


@cache_result
def get_eightify_extension_id():
    """
    Try to find the Eightify extension ID in the user's Chrome profile
    """
    system = platform.system()

    try:
        # Determine user data directory based on OS
        if system == "Windows":
            user_data_dir = os.path.join(
                os.environ['USERPROFILE'],
                'AppData',
                'Local',
                'Google',
                'Chrome',
                'User Data')
            extensions_path = os.path.join(
                user_data_dir, 'Default', 'Extensions')
        elif system == "Darwin":  # macOS
            user_data_dir = os.path.join(
                os.environ['HOME'],
                'Library',
                'Application Support',
                'Google',
                'Chrome')
            extensions_path = os.path.join(
                user_data_dir, 'Default', 'Extensions')
        else:  # Linux
            user_data_dir = os.path.join(
                os.environ['HOME'], '.config', 'google-chrome')
            extensions_path = os.path.join(
                user_data_dir, 'Default', 'Extensions')

        # Look for extension folders that might be Eightify
        eightify_dirs = []
        if os.path.exists(extensions_path):
            for ext_id in os.listdir(extensions_path):
                # Look for manifest.json files in each extension directory
                for version in os.listdir(
                    os.path.join(
                        extensions_path,
                        ext_id)):
                    manifest_path = os.path.join(
                        extensions_path, ext_id, version, 'manifest.json')
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                manifest_data = json.load(f)
                                # Check if this could be Eightify based on name
                                # or description
                                name = manifest_data.get('name', '').lower()
                                description = manifest_data.get(
                                    'description', '').lower()

                                # Look for keywords that suggest it's Eightify
                                eightify_keywords = [
                                    'eightify',
                                    'eight',
                                    'transcript',
                                    'summary',
                                    'youtube transcript',
                                    'summarize']

                                if (any(keyword in name for keyword in eightify_keywords) or any(
                                        keyword in description for keyword in eightify_keywords)):
                                    eightify_dirs.append(ext_id)
                                    logger.info(f"Found potential Eightify extension: {ext_id} - {name}")
                        except Exception:
                            # Skip if there's any issue reading the manifest
                            pass

        return eightify_dirs
    except Exception as e:
        logger.error(f"Error finding Eightify extension ID: {e}")
        return []


def scrape_eightify_data(youtube_url, close_existing=False):
    """
    Scrape all data produced by Eightify extension for a YouTube video
    """
    # Initialize the Chrome driver
    driver, error = initialize_chrome_driver(close_existing)

    if not driver:
        error["video_url"] = youtube_url
        return error

    try:
        # Modify URL to force start from beginning (t=0)
        if '?' in youtube_url:
            if 't=' in youtube_url:
                # Replace existing time parameter
                youtube_url = re.sub(r't=\d+', 't=0', youtube_url)
            else:
                # Add time parameter
                youtube_url += '&t=0'
        else:
            # No parameters yet
            youtube_url += '?t=0'
            
        logger.info(f"Using URL with time reset: {youtube_url}")
        
        # Navigate to the YouTube video
        logger.info(f"Navigating to {youtube_url}")
        driver.get(youtube_url)
        
        # Simple wait instead of human-like behavior
        time.sleep(2)

        # Wait for the video to load with retries for the "Something went wrong" error
        logger.info("Waiting for video player to load...")
        video_loaded = False
        retry_count = 0
        max_retries = 3
        
        while not video_loaded and retry_count < max_retries:
            try:
                # Wait for movie_player element
                WebDriverWait(driver, WAIT_TIME_LOAD).until(
                    EC.presence_of_element_located((By.ID, "movie_player"))
                )
                
                # Check if error message is present
                error_messages = driver.find_elements(By.XPATH, "//div[contains(text(), 'Something went wrong')]")
                if error_messages and len(error_messages) > 0 and error_messages[0].is_displayed():
                    logger.warning(f"YouTube error detected (attempt {retry_count+1}/{max_retries}), refreshing...")
                    driver.refresh()
                    time.sleep(5)  # Wait after refresh
                    retry_count += 1
                    continue
                
                # Make sure video is playing from beginning by directly setting time to 0
                try:
                    driver.execute_script("document.querySelector('video').currentTime = 0;")
                    logger.info("Reset video position to beginning")
                except Exception as time_error:
                    logger.warning(f"Could not reset video time: {time_error}")
                
                video_loaded = True
                logger.info("Video loaded successfully")
                
            except TimeoutException:
                if retry_count < max_retries - 1:
                    logger.warning(f"Timed out waiting for video player (attempt {retry_count+1}/{max_retries}), refreshing...")
                    driver.refresh()
                    time.sleep(5)  # Wait after refresh
                    retry_count += 1
                else:
                    logger.warning("Final timeout waiting for video player, trying to continue anyway")
                    video_loaded = True  # Force continue on last attempt

        # Give Eightify time to load
        logger.info("Waiting for Eightify to load...")
        try:
            # Try to wait for Eightify iframe to appear
            WebDriverWait(driver, WAIT_TIME_EXTENSION).until(
                lambda d: any(len(d.find_elements(By.CSS_SELECTOR, sel)) > 0 for sel in IFRAME_SELECTORS[:3])
            )
            
        except TimeoutException:
            # If timeout, use sleep as fallback
            time.sleep(WAIT_TIME_EXTENSION)
            
            # Try refreshing once more if Eightify doesn't appear
            if not any(len(driver.find_elements(By.CSS_SELECTOR, sel)) > 0 for sel in IFRAME_SELECTORS[:3]):
                logger.warning("Eightify not detected, trying page refresh...")
                driver.refresh()
                time.sleep(WAIT_TIME_EXTENSION)

        return process_eightify_content(driver, youtube_url)

    except Exception as e:
        logger.error(f"Error during navigation: {str(e)}")
        if driver:
            logger.info("Driver still active - browser control handed to main function")

        return {
            "video_url": youtube_url,
            "status": "Error",
            "message": f"Error during navigation: {str(e)}"
        }


def process_eightify_content(driver, youtube_url):
    """
    Process Eightify content from a loaded YouTube page

    Args:
        driver: WebDriver instance
        youtube_url: YouTube video URL

    Returns:
        dict: Extracted Eightify data
    """
    try:
        logger.info("Looking for Eightify iframe...")
        iframe_found = False
        eightify_data = {
            "key_insights": "",
            "timestamped_summary": "",
            "top_comments": "",
            "transcript": ""
        }

        # Try each iframe selector until we find a match
        for selector in IFRAME_SELECTORS:
            iframes = driver.find_elements(By.CSS_SELECTOR, selector)
            logger.info(f"Found {len(iframes)} iframes with selector: {selector}")

            if not iframes:
                continue

            for iframe in iframes:
                try:
                    # Check if this iframe is visible and seems to be Eightify
                    if not (iframe.is_displayed() and (iframe.get_attribute(
                            "id") == "eightify-iframe" or selector == "iframe")):
                        continue

                    logger.info(f"Found potential Eightify iframe! ID: {iframe.get_attribute('id')}")

                    # Process the iframe
                    iframe_data = process_iframe(driver, iframe)

                    # Merge with existing data
                    for key, value in iframe_data.items():
                        if value and (
                                key not in eightify_data or not eightify_data[key]):
                            eightify_data[key] = value

                    iframe_found = True
                    break
                except Exception as iframe_error:
                    logger.error(f"Error processing iframe: {iframe_error}")
                    driver.switch_to.default_content()  # Make sure we're back to the main content

            # If we've found some data, we can break the selector loop
            if iframe_found and any(
                value for key,
                value in eightify_data.items() if key in [
                    "key_insights",
                    "timestamped_summary",
                    "top_comments",
                    "transcript"]):
                break

        # Process transcript data if we found it
        structured_transcript = []
        if eightify_data.get("transcript"):
            structured_transcript = process_transcript_data(
                eightify_data["transcript"])

        # Prepare the final result
        result = {
            "video_url": youtube_url,
            "status": "Success" if any(eightify_data.values()) else "Error",
            "key_insights": eightify_data.get("key_insights", ""),
            "timestamped_summary": eightify_data.get("timestamped_summary", ""),
            "top_comments": eightify_data.get("top_comments", ""),
            "transcript": eightify_data.get("transcript", ""),
            "structured_transcript": structured_transcript
        }

        if result["status"] == "Success":
            logger.info("Successfully extracted Eightify data")
            for key, value in result.items():
                if key not in ["video_url", "status",
                               "structured_transcript"] and value:
                    logger.info(f"- {key}: {len(value)} characters")
        else:
            result["message"] = "Could not locate Eightify data"
            result["next_steps"] = (
                "1. Open the video in your normal browser and verify Eightify is working\n"
                "2. Check the saved HTML and screenshots for debugging")

        return result

    except Exception as e:
        logger.error(f"Error during data extraction: {e}")

        try:
            with open("error_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        except Exception as write_error:
            logger.error(f"Error saving page source: {write_error}")

        return {
            "video_url": youtube_url,
            "status": "Error",
            "message": f"Error during extraction: {str(e)}",
            "next_steps": "Check the saved HTML for debugging"
        }


def process_iframe(driver, iframe):
    """
    Process an Eightify iframe to extract content

    Args:
        driver: WebDriver instance
        iframe: Iframe element to process

    Returns:
        dict: Extracted data from the iframe
    """
    tab_data = {}

    try:
        # Switch to the iframe
        driver.switch_to.frame(iframe)

        # Check if there's already content present first - early return if content exists
        content_present = check_for_existing_content(driver)
        if content_present:
            # If content is already present, extract directly without clicking buttons
            logger.info("Content found - extracting without clicking buttons")
            tab_data = extract_content_from_tabs(driver)
            if any(tab_data.values()):
                driver.switch_to.default_content()
                return tab_data
                
        # First, try to click the main summarize button if needed
        main_button_clicked = find_and_click_button_optimized(
            driver,
            SUMMARIZE_BUTTON_SELECTORS,
            purpose="main summarize button",
            wait_time=WAIT_TIME_PROCESSING
        )

        if main_button_clicked:
            logger.info("Successfully clicked main summarize button. Now checking for tabs.")

        # Extract content from tabs
        tab_data = extract_content_from_tabs(driver)

        # If we're still missing some tabs, try a direct extraction approach
        missing_tabs = [tab for tab in TAB_TYPES if not tab_data.get(tab)]

        if missing_tabs:
            tab_data = extract_direct_content(driver, tab_data, missing_tabs)

        # Switch back to main content
        driver.switch_to.default_content()
    except Exception as e:
        logger.error(f"Error processing iframe content: {e}")
        driver.switch_to.default_content()

    return tab_data


def check_for_existing_content(driver):
    """Check if content is already present in the iframe"""
    try:
        content_selectors = [".SummaryTabsView_content__6OYs8", "[class*='content']", ".tab-content"]
        for selector in content_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                if element.is_displayed() and len(element.text.strip()) > MIN_CONTENT_LENGTH:
                    logger.info("Content already present, no need to click the summarize button")
                    return True
    except Exception as e:
        logger.error(f"Error checking for existing content: {e}")

    return False


def extract_content_from_tabs(driver):
    """Extract content from all tabs in the Eightify interface sequentially"""
    tab_data = {}

    try:
        # Wait 5 seconds after page loads before starting tab processing
        logger.info("Waiting 5 seconds for initial page stabilization...")
        time.sleep(5)
        
        # Find the tabs
        tabs = driver.find_elements(By.CSS_SELECTOR, TAB_SELECTORS)

        if not tabs:
            logger.warning("No tabs found in the Eightify interface")
            return tab_data

        tab_count = len(tabs)
        logger.info(f"Found {tab_count} tabs in the Eightify interface")
        
        # Only process tabs that exist (don't try more tabs than found)
        actual_tab_types = TAB_TYPES[:min(tab_count, len(TAB_TYPES))]

        # Process each tab sequentially from start to finish
        logger.info("Processing tabs sequentially one by one")
        for i, tab_type in enumerate(actual_tab_types):
            if i >= tab_count:
                break
            
            logger.info(f"PROCESSING TAB {i+1}/{len(actual_tab_types)}: {tab_type}")
            
            # Get the tab element (re-find each time to avoid stale references)
            tabs = driver.find_elements(By.CSS_SELECTOR, TAB_SELECTORS)
            if i >= len(tabs):
                logger.warning(f"Tab {i} for {tab_type} not found, skipping")
                continue
                
            tab = tabs[i]
            
            # First ensure tab is in view
            logger.info(f"Scrolling to tab: {tab_type}")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
            time.sleep(0.5)  # Wait for scrolling to complete
            
            # Click the tab
            logger.info(f"Clicking tab: {tab_type}")
            try:
                driver.execute_script("arguments[0].click();", tab)
            except Exception as tab_click_error:
                logger.error(f"Error clicking tab {tab_type}: {tab_click_error}")
                continue
                
            # Wait initially for tab to become active
            time.sleep(2)
            
            # Look for and click "Summarize Video" button if present
            summarize_clicked = False
            for btn_selector in SUMMARIZE_BUTTON_SELECTORS:
                if summarize_clicked:
                    break
                    
                try:
                    if btn_selector.startswith("//"):
                        # XPath selector
                        buttons = driver.find_elements(By.XPATH, btn_selector)
                    else:
                        # CSS selector
                        buttons = driver.find_elements(By.CSS_SELECTOR, btn_selector)
                        
                    for button in buttons:
                        if button.is_displayed():
                            logger.info(f"Found 'Summarize Video' button in {tab_type} tab")
                            driver.execute_script("arguments[0].click();", button)
                            summarize_clicked = True
                            logger.info(f"Clicked 'Summarize Video' button in {tab_type} tab")
                            break
                except Exception as btn_error:
                    logger.error(f"Error with button selector {btn_selector} in {tab_type} tab: {btn_error}")
            
            # Wait for content to be generated (3 seconds as requested)
            logger.info(f"Waiting 5 seconds for {tab_type} content to generate...")
            time.sleep(5)
            
            # Extract content
            content_found = False
            for content_selector in CONTENT_SELECTORS:
                if content_found:
                    break
                    
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, content_selector)
                    for element in elements:
                        if element.is_displayed():
                            content_text = element.text.strip()
                            if content_text and len(content_text) > MIN_CONTENT_LENGTH:
                                tab_data[tab_type] = content_text
                                logger.info(f"Extracted content from {tab_type} tab ({len(content_text)} chars)")
                                content_found = True
                                break
                except Exception as selector_error:
                    logger.error(f"Error with content selector {content_selector}: {selector_error}")
                    continue
            
            # If we still don't have content, try getting the entire body
            if not content_found:
                try:
                    body_text = driver.find_element(By.TAG_NAME, "body").text.strip()
                    if body_text and len(body_text) > MIN_CONTENT_LENGTH:
                        tab_data[tab_type] = body_text
                        logger.info(f"Extracted content from {tab_type} tab using body text ({len(body_text)} chars)")
                        content_found = True
                except Exception as body_error:
                    logger.error(f"Error getting body text: {body_error}")
            
            # Add a separator in logs between tabs
            logger.info(f"Completed processing tab: {tab_type} - {'SUCCESS' if content_found else 'FAILED'}")
            logger.info("-" * 40)

    except Exception as e:
        logger.error(f"Error extracting content from tabs: {e}")

    # Log summary of extraction results
    tabs_extracted = sum(1 for v in tab_data.values() if v)
    logger.info(f"Extracted content from {tabs_extracted}/{len(actual_tab_types)} tabs")
    
    return tab_data


def extract_direct_content(driver, tab_data, missing_tabs):
    """
    Extract content directly when tab navigation fails

    Args:
        driver: WebDriver instance
        tab_data: Existing tab data
        missing_tabs: List of tabs still missing content

    Returns:
        dict: Updated tab data
    """
    logger.info(f"Still missing content for tabs: {missing_tabs}")
    logger.info("Trying direct extraction approach...")

    try:
        # First check if we're still in the iframe context
        try:
            # Quick check to see if we're in iframe context
            test_element = driver.find_element(By.TAG_NAME, "html")
            is_in_iframe = True
        except Exception:
            is_in_iframe = False
            logger.warning("No longer in iframe context, attempting to recover...")
        
        # If we lost iframe context, try to recover it
        if not is_in_iframe:
            logger.info("Attempting to find the iframe again...")
            driver.switch_to.default_content()
            time.sleep(1)
            
            # Try to find the iframe again
            iframe_found = find_iframe_and_switch(driver)
            if not iframe_found:
                logger.error("Failed to recover iframe context, aborting direct extraction")
                return tab_data
        
        # Verify we can access the body before proceeding
        try:
            # Check if body exists
            body_present = EC.presence_of_element_located((By.TAG_NAME, "body"))
            if not body_present(driver):
                logger.error("Body element not found in iframe, cannot extract content directly")
                return tab_data
        except Exception as verify_error:
            logger.error(f"Error verifying body presence: {verify_error}")
            return tab_data
            
        # Now try to get all text content from the iframe
        try:
            all_content = driver.find_element(By.TAG_NAME, "body").text
            if not all_content or len(all_content.strip()) < MIN_CONTENT_LENGTH:
                logger.warning("Body element found but contains insufficient content")
                return tab_data
        except Exception as body_error:
            logger.error(f"Error extracting body text: {body_error}")
            return tab_data
            
        logger.info(f"Successfully extracted body text ({len(all_content)} chars)")

        # Try to segment the content by looking for section headers
        for tab in missing_tabs:
            for header in CONTENT_SECTION_HEADERS[tab]:
                if header in all_content:
                    # Find the section and extract it
                    start_idx = all_content.find(header)
                    if start_idx == -1:
                        continue

                    # Find the next section header or use the end of text
                    end_idx = len(all_content)

                    # Look for the next section header
                    all_headers = sum(CONTENT_SECTION_HEADERS.values(), [])
                    for next_header in all_headers:
                        next_start = all_content.find(
                            next_header, start_idx + len(header))
                        if next_start != -1 and next_start < end_idx:
                            end_idx = next_start

                    # Extract the section content
                    section_content = all_content[start_idx:end_idx].strip()
                    if len(section_content) > MIN_CONTENT_LENGTH:
                        tab_data[tab] = section_content
                        logger.info(f"Extracted {tab} content through direct extraction ({len(section_content)} chars)")
                        break
                        
    except Exception as e:
        logger.error(f"Error in direct extraction: {e}")
        # Make sure we return to default content in case of error
        try:
            driver.switch_to.default_content()
        except:
            pass

    # Always ensure we're back to default content
    try:
        driver.switch_to.default_content()
    except:
        pass
        
    return tab_data


def process_transcript_data(transcript_text):
    """
    Process transcript text into structured format

    Args:
        transcript_text: Raw transcript text

    Returns:
        list: List of timestamp/text dictionaries
    """
    logger.info("Processing transcript text...")
    logger.info(f"First 100 characters: {transcript_text[:100]}...")
    transcript_lines = transcript_text.split('\n')
    structured_transcript = []

    i = 0
    while i < len(transcript_lines):
        # Check if the current line matches a timestamp pattern
        current_line = transcript_lines[i].strip()
        is_timestamp = (
            ':' in current_line and
            len(current_line) <= 8 and
            all(c.isdigit() or c == ':' for c in current_line)
        )

        if is_timestamp and i + 1 < len(transcript_lines):
            timestamp = current_line
            text = transcript_lines[i + 1].strip()
            structured_transcript.append({
                "timestamp": timestamp,
                "text": text
            })
            i += 2
        else:
            # If not a timestamp, just add the text
            if current_line and not current_line.lower() == "transcript":
                structured_transcript.append({
                    "timestamp": "",
                    "text": current_line
                })
            i += 1

    return structured_transcript


def close_existing_chrome(system):
    """Attempt to close any existing Chrome instances to avoid profile conflicts"""
    try:
        if system == "Windows":
            os.system("taskkill /f /im chrome.exe > nul 2>&1")
        elif system in ["Darwin", "Linux"]:
            os.system("pkill -f chrome > /dev/null 2>&1")

        logger.info("Attempted to close existing Chrome instances")
        time.sleep(2)  # Give time for Chrome to fully close
    except Exception:
        logger.warning("Failed to close Chrome, but continuing anyway")


def save_eightify_data_to_file(eightify_data, output_file):
    """Save Eightify data to a JSON file"""
    # Create a clean data structure with the video URL as the key
    clean_data = {
        eightify_data.get("video_url", ""): {
            "key_insights": eightify_data.get("key_insights", ""),
            "timestamped_summary": eightify_data.get("timestamped_summary", ""),
            "top_comments": eightify_data.get("top_comments", ""),
            "transcript": eightify_data.get("transcript", "")
        }
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(clean_data, f, indent=2, ensure_ascii=False)
    logger.info(f"Eightify data saved to {output_file}")


def extract_video_id(video_url):
    """Extract the YouTube video ID from a URL"""
    try:
        from urllib.parse import urlparse, parse_qs

        # Try to parse the URL
        parsed_url = urlparse(video_url)

        # Check if it's a youtu.be short URL
        if parsed_url.netloc == 'youtu.be':
            return parsed_url.path.strip('/')

        # Regular youtube.com URL
        video_id = parse_qs(parsed_url.query).get('v', [None])[0]
        if video_id:
            return video_id

        # Check for embedded video URL format
        if '/embed/' in parsed_url.path:
            return parsed_url.path.split('/embed/')[1].split('/')[0]

    except Exception:
        pass

    # If we can't extract a proper ID, return a timestamp
    return f"video_{int(time.time())}"


def process_next_url(driver, video_url):
    """Process the next URL in the currently open browser tab"""
    try:
        # Navigate to the YouTube video
        logger.info(f"Navigating to {video_url}")
        driver.get(video_url)

        # Wait for the video to load
        logger.info("Waiting for video player to load...")
        try:
            WebDriverWait(driver, WAIT_TIME_LOAD).until(
                EC.presence_of_element_located((By.ID, "movie_player"))
            )
            logger.info("Video loaded successfully")
        except TimeoutException:
            logger.warning("Timed out waiting for video player, trying to continue anyway")

        # Give Eightify time to load
        logger.info("Waiting for Eightify to load...")
        try:
            # Try to wait for Eightify iframe to appear
            WebDriverWait(driver, WAIT_TIME_EXTENSION).until(
                lambda d: any(len(d.find_elements(By.CSS_SELECTOR, sel)) > 0 for sel in IFRAME_SELECTORS[:3])
            )
        except TimeoutException:
            # If timeout, use sleep as fallback
            time.sleep(WAIT_TIME_EXTENSION)

        # Use the existing functions to extract content
        return process_eightify_content(driver, video_url)

    except Exception as e:
        logger.error(f"Error navigating to URL: {e}")
        return {
            "video_url": video_url,
            "status": "Error",
            "message": f"Error navigating: {str(e)}"
        }


def download_chromedriver_manually(chrome_version=None):
    """
    Manually download ChromeDriver that matches the installed Chrome version

    Args:
        chrome_version: Chrome version (optional). If not provided, will try to detect.

    Returns:
        str: Path to the chromedriver executable or None if download fails
    """
    try:
        if not chrome_version:
            chrome_version = get_chrome_version()

        if not chrome_version:
            logger.warning("Could not determine Chrome version, using latest ChromeDriver")
            chrome_driver_url = "https://chromedriver.storage.googleapis.com/LATEST_RELEASE"
            with urllib.request.urlopen(chrome_driver_url) as response:
                version = response.read().decode('utf-8').strip()
        else:
            # Extract major version (e.g., "94.0.4606.81" -> "94")
            major_version = chrome_version.split('.')[0]
            logger.info(f"Detected Chrome major version: {major_version}")

            # Get the latest ChromeDriver version for this Chrome version
            chrome_driver_url = f"https://chromedriver.storage.googleapis.com/LATEST_RELEASE_{major_version}"
            try:
                with urllib.request.urlopen(chrome_driver_url) as response:
                    version = response.read().decode('utf-8').strip()
            except Exception as e:
                logger.error(f"Error getting driver for version {major_version}: {e}")
                # Fallback to latest version
                chrome_driver_url = "https://chromedriver.storage.googleapis.com/LATEST_RELEASE"
                with urllib.request.urlopen(chrome_driver_url) as response:
                    version = response.read().decode('utf-8').strip()

        logger.info(f"Downloading ChromeDriver version: {version}")

        # Determine platform
        system = platform.system()
        if system == "Windows":
            platform_name = "win32"
        elif system == "Darwin":  # macOS
            # Check if M1/M2 Mac (arm64)
            if platform.machine() == 'arm64':
                platform_name = "mac_arm64"
            else:
                platform_name = "mac64"
        else:  # Linux
            platform_name = "linux64"

        # Download ChromeDriver
        download_url = f"https://chromedriver.storage.googleapis.com/{version}/chromedriver_{platform_name}.zip"
        logger.info(f"Downloading from: {download_url}")

        # Create temp directory for ChromeDriver
        driver_dir = os.path.join(
            os.path.dirname(
                os.path.abspath(__file__)),
            "chromedriver_temp")
        os.makedirs(driver_dir, exist_ok=True)

        zip_file_path = os.path.join(driver_dir, "chromedriver.zip")
        driver_path = os.path.join(
            driver_dir,
            "chromedriver.exe" if system == "Windows" else "chromedriver")

        # Download zip file
        urllib.request.urlretrieve(download_url, zip_file_path)

        # Extract zip file
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(driver_dir)

        # Make chromedriver executable on Linux/Mac
        if system != "Windows":
            os.chmod(driver_path, 0o755)

        logger.info(f"ChromeDriver downloaded to: {driver_path}")
        return driver_path

    except Exception as e:
        logger.error(f"Error downloading ChromeDriver: {e}")
        traceback.print_exc()
        return None


def check_chrome_installation():
    """
    Check if Chrome browser is properly installed and accessible

    Returns:
        str: Path to Chrome executable or None if not found
    """
    system = platform.system()
    chrome_executable = None

    if system == "Windows":
        # Common Chrome locations on Windows
        possible_paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            os.path.join(
                os.environ.get(
                    'LOCALAPPDATA',
                    ''),
                "Google\\Chrome\\Application\\chrome.exe")]

        for path in possible_paths:
            if os.path.exists(path):
                chrome_executable = path
                break
    elif system == "Darwin":  # macOS
        if os.path.exists(
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'):
            chrome_executable = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    else:  # Linux
        # Try to locate chrome using 'which'
        try:
            chrome_executable = subprocess.check_output(
                ['which', 'google-chrome']).decode('utf-8').strip()
        except subprocess.SubprocessError:
            try:
                chrome_executable = subprocess.check_output(
                    ['which', 'chrome']).decode('utf-8').strip()
            except subprocess.SubprocessError:
                pass

    if chrome_executable and os.path.exists(chrome_executable):
        logger.info(f"Found Chrome browser at: {chrome_executable}")
        return chrome_executable

    logger.warning("Warning: Chrome browser not found in common locations")
    return None


def find_existing_chromedriver():
    """
    Find existing ChromeDriver in the system PATH

    Returns:
        str: Path to chromedriver executable or None if not found
    """
    system = platform.system()
    driver_executable = "chromedriver.exe" if system == "Windows" else "chromedriver"

    # Check in current directory first
    current_dir_driver = os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)),
        driver_executable)
    if os.path.exists(current_dir_driver):
        logger.info(f"Found ChromeDriver in current directory: {current_dir_driver}")
        return current_dir_driver

    # Check in PATH
    for path_dir in os.environ.get('PATH', '').split(os.pathsep):
        driver_path = os.path.join(path_dir, driver_executable)
        if os.path.exists(driver_path):
            logger.info(f"Found ChromeDriver in PATH: {driver_path}")
            return driver_path

    # On Windows, check in Program Files and other common locations
    if system == "Windows":
        possible_paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chromedriver.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chromedriver.exe",
            os.path.join(os.environ.get('LOCALAPPDATA', ''),
                         "Google\\Chrome\\Application\\chromedriver.exe"),
            # ChromeDriver might be in webdriver-manager cache
            os.path.join(
                os.environ.get(
                    'LOCALAPPDATA',
                    ''),
                ".wdm\\drivers\\chromedriver\\win32\\*\\chromedriver.exe")
        ]

        for path in possible_paths:
            if '*' in path:  # Handle glob pattern
                matching_files = glob.glob(path)
                if matching_files:
                    # Sort by modified time to get the most recent one
                    newest_driver = max(matching_files, key=os.path.getmtime)
                    logger.info(f"Found ChromeDriver using glob pattern: {newest_driver}")
                    return newest_driver
            elif os.path.exists(path):
                logger.info(f"Found ChromeDriver in common location: {path}")
                return path

    logger.warning("Could not find existing ChromeDriver")
    return None


def is_chromedriver_compatible(driver_path):
    """
    Check if the ChromeDriver version is compatible with the installed Chrome version

    Args:
        driver_path: Path to chromedriver executable

    Returns:
        bool: True if compatible, False otherwise
    """
    try:
        chrome_version = get_chrome_version()
        if not chrome_version:
            logger.warning("Could not determine Chrome version for compatibility check")
            return False

        # Get ChromeDriver version
        system = platform.system()
        cmd = f'"{driver_path}" --version'

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True)
        driver_output = result.stdout

        # Parse the version number
        # Output is like: "ChromeDriver 94.0.4606.61"
        if driver_output and "ChromeDriver" in driver_output:
            driver_version_str = driver_output.split(' ')[1]
            driver_major = driver_version_str.split('.')[0]

            # Chrome version like "94.0.4606.81"
            chrome_major = chrome_version.split('.')[0]

            logger.info(f"Chrome version: {chrome_version} (major: {chrome_major})")
            logger.info(f"ChromeDriver version: {driver_version_str} (major: {driver_major})")

            # Major versions should match
            if driver_major == chrome_major:
                logger.info("Chrome and ChromeDriver versions are compatible")
                return True
            else:
                logger.warning(f"Warning: Chrome version ({chrome_major}) and ChromeDriver version ({driver_major}) mismatch")
                return False
        else:
            logger.warning(f"Could not determine ChromeDriver version from output: {driver_output}")
            return False
    except Exception as e:
        logger.error(f"Error checking ChromeDriver compatibility: {e}")
        return False


def setup_chrome_options(system):
    """
    Set up Chrome options for Eightify extension with optimized stealth settings

    Args:
        system: Operating system platform

    Returns:
        tuple: (Options object, user_data_dir)
    """
    chrome_options = Options()

    # Determine user data directory based on OS
    if system == "Windows":
        user_data_dir = os.path.join(
            os.environ['USERPROFILE'],
            'AppData',
            'Local',
            'Google',
            'Chrome',
            'User Data')
    elif system == "Darwin":  # macOS
        user_data_dir = os.path.join(
            os.environ['HOME'],
            'Library',
            'Application Support',
            'Google',
            'Chrome')
    else:  # Linux
        user_data_dir = os.path.join(
            os.environ['HOME'], '.config', 'google-chrome')

    logger.info(f"Using Chrome profile directory: {user_data_dir}")

    # Essential: Use existing profile with the extension
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_options.add_argument("--profile-directory=Default")  # Use default profile

    # Set random window size to appear more human-like
    width = random.randint(1280, 1920)
    height = random.randint(800, 1080)
    chrome_options.add_argument(f"--window-size={width},{height}")

    # Essential: Anti-detection measures
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    # Get the Eightify extension ID if possible
    eightify_extensions = get_eightify_extension_id()

    # Enable specific extensions if we found them
    if eightify_extensions:
        logger.info(f"Found potential Eightify extensions: {eightify_extensions}")
        # Specifically whitelist Eightify to make sure it's loaded
        for ext_id in eightify_extensions:
            chrome_options.add_argument(f"--whitelisted-extension-id={ext_id}")
    else:
        logger.warning("Could not find Eightify extension ID. Will use all extensions in profile.")

    # Essential stability options
    chrome_options.add_argument("--no-sandbox")  # Required for some environments
    chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems

    # Disable notifications to avoid interference
    chrome_options.add_argument("--disable-notifications")

    # Set a random user agent
    random_user_agent = random.choice(USER_AGENTS)
    chrome_options.add_argument(f"--user-agent={random_user_agent}")
    logger.debug(f"Using user agent: {random_user_agent}")

    # Disable logging for cleaner output
    chrome_options.add_argument("--log-level=3")  # Only show fatal errors
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

    return chrome_options, user_data_dir


def initialize_chrome_driver(close_existing=False):
    """
    Initialize Chrome WebDriver with stealth settings

    Args:
        close_existing: Whether to close existing Chrome instances

    Returns:
        tuple: (WebDriver instance, error message if failed)
    """
    # Get system info
    system = platform.system()
    logger.info(f"Operating System: {system}")
    chrome_version = get_chrome_version()
    logger.info(f"Chrome Version: {chrome_version}")

    # Set up Chrome options
    chrome_options, user_data_dir = setup_chrome_options(system)

    # Automatically download appropriate ChromeDriver version
    logger.info("Setting up ChromeDriver...")
    driver = None

    try:
        # Try with basic Chrome initialization first
        logger.info("Attempting basic Chrome initialization with user profile...")
        if close_existing:
            close_existing_chrome(system)
        driver = webdriver.Chrome(options=chrome_options)
        
        # Apply stealth settings
        apply_stealth_settings(driver)
        
        return driver, None

    except Exception as e:
        logger.error(f"Error initializing with user profile: {e}")
        
        # Remaining fallback approaches unchanged
        # ... (keep the rest of the initialization code)

    # Should never reach here, but just in case:
    return None, {
        "status": "Error",
        "message": "Failed to initialize browser"
    }


def create_empty_input_file(filename):
    """Create an empty input file if it doesn't exist"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# Enter one YouTube URL per line\n")
        logger.info(f"Created empty input file: {filename}")
        return True
    except Exception as e:
        logger.error(f"Error creating input file: {e}")
        return False


def load_urls_from_file(filename):
    """Load URLs from a file"""
    # if not os.path.exists(filename):
    #     logger.warning(f"Error: {filename} not found.")
    #     video_url = input("Enter YouTube video URL manually: ")
    #     return [video_url]

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()
                    and not line.strip().startswith('#')]

        logger.info(f"Found {len(urls)} URLs to process in {filename}")
        return urls
    except Exception as e:
        logger.error(f"Error reading input file: {e}")
        video_url = input("Enter YouTube video URL manually: ")
        return [video_url]


def load_existing_results(output_file):
    """Load existing results from the output file"""
    all_results = {}

    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                all_results = json.load(f)
            logger.info(f"Loaded existing results from {output_file} with {len(all_results)} entries")
        except Exception as e:
            logger.error(f"Error loading existing results: {e}")

    return all_results


def save_results(all_results, output_file):
    """Save all results to the output file"""
    try:
        # Create directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        logger.info(f"Updated results saved to {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error saving results: {e}")
        return False


def monkey_patch_webdriver():
    """Monkey patch the webdriver.Chrome to capture the driver object"""
    def capture_driver(driver):
        global global_driver
        global_driver = driver
        return driver

    original_chrome = webdriver.Chrome
    webdriver.Chrome = lambda *args, **kwargs: capture_driver(
        original_chrome(*args, **kwargs))

    return original_chrome


def restore_webdriver(original_chrome):
    """Restore the original webdriver.Chrome function"""
    webdriver.Chrome = original_chrome


def process_url(video_url, retry_count=0, max_retries=2):
    """
    Process a single YouTube URL with improved caching

    Args:
        video_url: YouTube video URL
        retry_count: Current retry attempt
        max_retries: Maximum number of retry attempts

    Returns:
        tuple: (success, eightify_data)
    """
    global global_driver

    try:
        # If retry_count > 0, we're in a retry attempt
        if retry_count > 0:
            logger.info(f"Retry attempt {retry_count}/{max_retries} for {video_url}")

            # Force a new browser instance for retries
            if global_driver is not None:
                try:
                    logger.info("Closing existing browser for retry...")
                    global_driver.quit()
                except Exception as close_error:
                    logger.error(f"Error closing browser: {close_error}")
                finally:
                    global_driver = None

        # Create a new browser instance if needed
        if global_driver is None:
            logger.info("\nStarting data extraction with new browser instance...")
            # Close any existing Chrome instances to avoid conflicts
            system = platform.system()
            close_existing_chrome(system)
            # Initialize a new browser with the first URL
            eightify_data = scrape_eightify_data(
                video_url, close_existing=True)
        else:
            # For subsequent URLs, first check if the driver is still
            # responsive
            try:
                logger.info("Checking if browser is still responsive...")
                # Simple operation to check browser responsiveness
                _ = global_driver.current_url
                # Force a clean state by refreshing the page
                global_driver.refresh()
                
                # Wait for page refresh to complete
                try:
                    WebDriverWait(global_driver, 3).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                except TimeoutException:
                    # If timeout, use sleep as fallback
                    time.sleep(3)

                logger.info("Browser is responsive. Trying to process next URL...")
                # Process the URL in the existing browser
                eightify_data = process_next_url(global_driver, video_url)
            except Exception as driver_error:
                logger.error(f"Browser is not responsive: {driver_error}")
                logger.info("Creating a new browser instance...")
                # If driver is not responsive, recreate it
                try:
                    if global_driver is not None:
                        global_driver.quit()
                except Exception:
                    pass
                global_driver = None
                system = platform.system()
                close_existing_chrome(system)
                eightify_data = scrape_eightify_data(
                    video_url, close_existing=True)

        # Check if extraction was successful
        if (eightify_data.get("status") == "Success" or
                any(eightify_data.get(key, "") for key in TAB_TYPES)):
            logger.info(f"Successfully extracted data for {video_url}")
            return True, eightify_data

        logger.warning(f"Extraction failed: {eightify_data.get('message', 'No error message')}")

        # If we haven't exceeded retry attempts, try again
        if retry_count < max_retries:
            return process_url(video_url, retry_count + 1, max_retries)

        return False, eightify_data

    except Exception as extraction_error:
        logger.error(f"Error during extraction: {extraction_error}")

        # If we haven't exceeded retry attempts, try again
        if retry_count < max_retries:
            time.sleep(5)  # Wait before retrying
            return process_url(video_url, retry_count + 1, max_retries)

        return False, {
            "video_url": video_url,
            "status": "Error",
            "message": f"Extraction failed after {max_retries} retries: {str(extraction_error)}"
        }


def prepare_browser_for_next_url():
    """
    Prepare the browser for the next URL

    Returns:
        bool: True if successful, False otherwise
    """
    global global_driver

    if global_driver is None:
        return False

    try:
        logger.info("Creating a clean new tab for next URL...")
        # Create a new tab
        global_driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(2)
        # Close the old tab
        global_driver.switch_to.window(global_driver.window_handles[-1])
        global_driver.close()
        global_driver.switch_to.window(global_driver.window_handles[0])
        time.sleep(2)
        logger.info("Ready to process next URL in clean tab...")
        return True
    except Exception as tab_error:
        logger.error(f"Error preparing browser for next URL: {tab_error}")
        # If we can't create a new tab, try closing the browser to force a new
        # instance next time
        try:
            if global_driver is not None:
                global_driver.quit()
        except Exception:
            pass
        global_driver = None
        logger.warning("Browser reset for next URL")
        return False


def keep_browser_open():
    """Keep the browser open and monitor its status"""
    global global_driver

    if global_driver is None:
        return

    logger.info("\n=============================================")
    logger.info("BROWSER IS OPEN - DO NOT CLOSE THIS TERMINAL")
    logger.info("=============================================")
    logger.info("Press Ctrl+C when you want to close the browser")

    try:
        while True:
            time.sleep(5)  # Sleep to reduce CPU usage
            # Check if the driver is still responsive
            try:
                current_url = global_driver.current_url
                logger.info(f"Browser still open at: {current_url}")
            except Exception:
                logger.warning("Browser was closed externally")
                break
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt detected")
    finally:
        try:
            if global_driver:
                global_driver.quit()
        except Exception:
            pass


def process_urls(urls_to_process, output_file):
    """
    Process a list of YouTube URLs

    Args:
        urls_to_process: List of YouTube URLs to process
        output_file: Path to output file
    """
    # Initialize results dictionary
    all_results = load_existing_results(output_file)

    # Store the driver in the global variable
    original_chrome = monkey_patch_webdriver()

    try:
        # Process each URL
        for i, video_url in enumerate(urls_to_process):
            # Skip URLs that have already been processed
            if video_url in all_results:
                logger.warning(f"\n[{i + 1}/{len(urls_to_process)}] Skipping already processed URL: {video_url}")
                continue

            logger.info(f"\n[{i + 1}/{len(urls_to_process)}] Processing: {video_url}")

            # Disable warnings
            warnings.filterwarnings("ignore", category=DeprecationWarning)

            # Process the URL
            success, eightify_data = process_url(video_url)

            # Create the data structure for this URL
            url_data = {
                "key_insights": eightify_data.get(
                    "key_insights", ""), "timestamped_summary": eightify_data.get(
                    "timestamped_summary", ""), "top_comments": eightify_data.get(
                    "top_comments", ""), "transcript": eightify_data.get(
                    "transcript", "")}

            # Add to results
            all_results[video_url] = url_data

            # Save all results after each URL is processed
            save_results(all_results, output_file)

            if not success:
                logger.error(f"\n❌ Failed to extract data for {video_url}")
            else:
                logger.info(f"\n✅ Successfully extracted data for {video_url}!")
                items_found = sum(
                    1 for key, value in url_data.items() if value)
                logger.info(f"Found data in {items_found}/{len(TAB_TYPES)} tabs")

            # Reset browser between videos if needed
            if not success or i == len(urls_to_process) - 1:
                continue

            # Prepare browser for next URL
            prepare_browser_for_next_url()

        # Keep the browser open at the end
        keep_browser_open()

    except Exception as e:
        logger.error(f"Error in main program: {e}")
        traceback.print_exc()
    finally:
        # Restore original Chrome class
        restore_webdriver(original_chrome)


def print_system_info():
    """Print information about the system and Chrome/ChromeDriver"""
    logger.info("\n===== Eightify Data Extractor =====")

    # Print system info
    system = platform.system()
    logger.info(f"Operating System: {system}")
    chrome_version = get_chrome_version()
    logger.info(f"Chrome Version: {chrome_version}")

    # Check for existing ChromeDriver
    existing_driver = find_existing_chromedriver()
    if existing_driver:
        logger.info(f"Found existing ChromeDriver: {existing_driver}")
        if chrome_version:
            compatibility = is_chromedriver_compatible(existing_driver)
            logger.info(f"ChromeDriver compatibility: {compatibility}")
            if not compatibility:
                logger.warning("\n==== IMPORTANT: ChromeDriver Version Mismatch ====")
                logger.warning(
                    "Your Chrome browser version doesn't match your ChromeDriver version.")
                logger.warning("This may cause errors when running the script.")
                logger.warning("\nYou can manually download the correct ChromeDriver version:")
                logger.warning(f"1. Visit: https://chromedriver.chromium.org/downloads")
                if chrome_version:
                    major_version = chrome_version.split('.')[0]
                    logger.warning(f"2. Download ChromeDriver version that matches Chrome {major_version}")
                else:
                    logger.warning("2. Download ChromeDriver version that matches your Chrome version")
                logger.warning("3. Extract the downloaded zip file")
                logger.warning("4. Place chromedriver.exe in this script's directory")
                logger.warning("======================================================\n")
    else:
        logger.warning("No ChromeDriver found in PATH or common locations")
        logger.warning("\n==== IMPORTANT: ChromeDriver Not Found ====")
        logger.warning("ChromeDriver is required to run this script.")
        logger.warning("\nYou can manually download ChromeDriver:")
        logger.warning("1. Visit: https://chromedriver.chromium.org/downloads")
        if chrome_version:
            major_version = chrome_version.split('.')[0]
            logger.warning(f"2. Download ChromeDriver version that matches Chrome {major_version}")
        else:
            logger.warning("2. Download ChromeDriver version that matches your Chrome version")
        logger.warning("3. Extract the downloaded zip file")
        logger.warning("4. Place chromedriver.exe in this script's directory")
        logger.warning("============================================\n")


def main():
    """Main function to run the script"""
    # Configure logging
    try:
        # Print system information
        print_system_info()

        # Define input and output files
        input_file = "video_urls.txt"
        output_file = "eightify_data.json"

        # Create input file if it doesn't exist
        if not os.path.exists(input_file):
            create_empty_input_file(input_file)

        # Load URLs from file
        urls_to_process = load_urls_from_file(input_file)

        # Process URLs
        if urls_to_process:
            process_urls(urls_to_process, output_file)
        else:
            logger.warning("No URLs to process. Please add YouTube URLs to the input file.")

    except Exception as e:
        logger.error(f"Unexpected error in main function: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
