from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

def get_chrome_version():
    """Get the version of Chrome installed on the system"""
    system = platform.system()
    try:
        if system == "Windows":
            # Try to get chrome version from the registry
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
            version, _ = winreg.QueryValueEx(key, "version")
            return version
        elif system == "Darwin":  # macOS
            process = subprocess.Popen(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'], 
                                     stdout=subprocess.PIPE)
            version = process.communicate()[0].decode('UTF-8').replace('Google Chrome', '').strip()
            return version
        elif system == "Linux":
            process = subprocess.Popen(['google-chrome', '--version'], 
                                     stdout=subprocess.PIPE)
            version = process.communicate()[0].decode('UTF-8').replace('Google Chrome', '').strip()
            return version
    except Exception as e:
        print(f"Could not determine Chrome version: {e}")
    return None

def get_eightify_extension_id():
    """
    Try to find the Eightify extension ID in the user's Chrome profile
    """
    system = platform.system()
    
    try:
        if system == "Windows":
            user_data_dir = os.path.join(os.environ['USERPROFILE'], 'AppData', 'Local', 'Google', 'Chrome', 'User Data')
            extensions_path = os.path.join(user_data_dir, 'Default', 'Extensions')
        elif system == "Darwin":  # macOS
            user_data_dir = os.path.join(os.environ['HOME'], 'Library', 'Application Support', 'Google', 'Chrome')
            extensions_path = os.path.join(user_data_dir, 'Default', 'Extensions')
        else:  # Linux
            user_data_dir = os.path.join(os.environ['HOME'], '.config', 'google-chrome')
            extensions_path = os.path.join(user_data_dir, 'Default', 'Extensions')
        
        # Look for extension folders that might be Eightify
        eightify_dirs = []
        if os.path.exists(extensions_path):
            for ext_id in os.listdir(extensions_path):
                # Look for manifest.json files in each extension directory
                for version in os.listdir(os.path.join(extensions_path, ext_id)):
                    manifest_path = os.path.join(extensions_path, ext_id, version, 'manifest.json')
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                manifest_data = json.load(f)
                                # Check if this could be Eightify based on name or description
                                name = manifest_data.get('name', '').lower()
                                description = manifest_data.get('description', '').lower()
                                
                                # Look for keywords that suggest it's Eightify
                                if ('eightify' in name or 'eight' in name or 
                                    'transcript' in name or 'summary' in name or
                                    'eightify' in description or 
                                    'youtube transcript' in description or
                                    'summarize' in description):
                                    eightify_dirs.append(ext_id)
                                    print(f"Found potential Eightify extension: {ext_id} - {name}")
                        except:
                            pass
        
        return eightify_dirs
    except Exception as e:
        print(f"Error finding Eightify extension ID: {e}")
        return []

def scrape_eightify_data(youtube_url, close_existing=False):
    """
    Scrape all data produced by Eightify extension for a YouTube video
    
    Args:
        youtube_url (str): URL of the YouTube video
        keep_browser_open (bool): Whether to keep the browser open after scraping
        close_existing (bool): Whether to close existing Chrome instances
        
    Returns:
        dict: All Eightify data including key insights, summary, comments and transcript
    """
    chrome_options = Options()
    
    # Get system info
    system = platform.system()
    print(f"Operating System: {system}")
    chrome_version = get_chrome_version()
    print(f"Chrome Version: {chrome_version}")
    
    # Use the user's existing Chrome profile to access the Eightify extension
    if system == "Windows":
        user_data_dir = os.path.join(os.environ['USERPROFILE'], 'AppData', 'Local', 'Google', 'Chrome', 'User Data')
    elif system == "Darwin":  # macOS
        user_data_dir = os.path.join(os.environ['HOME'], 'Library', 'Application Support', 'Google', 'Chrome')
    else:  # Linux
        user_data_dir = os.path.join(os.environ['HOME'], '.config', 'google-chrome')
    
    print(f"Using Chrome profile directory: {user_data_dir}")
    
    # Add user data directory - this is crucial for accessing the Eightify extension
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_options.add_argument("--profile-directory=Default")  # Use default profile
    
    # CRITICAL FIX: Add these options to prevent DevTools port issues
    chrome_options.add_argument("--remote-debugging-port=9222")  # Specify a debugging port
    chrome_options.add_argument("--no-first-run")  # Skip first run setup
    chrome_options.add_argument("--no-default-browser-check")  # Skip default browser check
    
    # Add additional options for stability
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # IMPORTANT: We WANT Eightify extension to be enabled
    # Get the Eightify extension ID if possible
    eightify_extensions = get_eightify_extension_id()
    
    # Do NOT disable extensions - we want Eightify to be available
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    
    # Enable specific extensions if we found them
    if eightify_extensions:
        print(f"Found potential Eightify extensions: {eightify_extensions}")
        # Instead of disabling all extensions except Eightify, we'll keep all enabled
        # but specifically whitelist Eightify to make sure it's loaded
        for ext_id in eightify_extensions:
            chrome_options.add_argument(f"--whitelisted-extension-id={ext_id}")
    else:
        print("Could not find Eightify extension ID. Will use all extensions in profile.")
    
    # Add these new options to handle the errors we saw
    chrome_options.add_argument("--disable-web-security")  # Disable CORS
    chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")  # Disable site isolation
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")  # Hide automation
    chrome_options.add_argument("--disable-notifications")  # Disable notifications
    
    # FIX FOR DEPRECATED_ENDPOINT ERROR - but don't disable extensions
    chrome_options.add_argument("--flag-switches-begin")
    chrome_options.add_argument("--flag-switches-end")
    chrome_options.add_argument("--disable-sync")  # Disable Chrome sync
    chrome_options.add_argument("--metrics-recording-only")  # Disable usage metrics
    chrome_options.add_argument("--disable-background-networking")  # Disable background network activity
    
    # Prevent WebGL errors
    chrome_options.add_argument("--disable-webgl")
    chrome_options.add_argument("--disable-threaded-animation")
    chrome_options.add_argument("--disable-threaded-scrolling")
    chrome_options.add_argument("--disable-in-process-stack-traces")
    
    # Disable logging for cleaner output
    chrome_options.add_argument("--log-level=3")  # Only show fatal errors
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    # Add user agent to look more like a regular browser
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")
    
    # Suppress console logging from Selenium
    selenium_logger = logging.getLogger('selenium')
    selenium_logger.setLevel(logging.CRITICAL)
    
    # Automatically download appropriate ChromeDriver version
    print("Setting up ChromeDriver...")
    driver = None

    try:
        # Try with basic Chrome initialization first
        print("Attempting basic Chrome initialization with user profile...")
        if close_existing:
            close_existing_chrome(system)
        driver = webdriver.Chrome(options=chrome_options)
        
    except Exception as e:
        print(f"Error initializing with user profile: {e}")
        
        # Check for Chrome installation
        chrome_path = check_chrome_installation()
        if not chrome_path:
            print("Warning: Could not find Chrome browser. Please make sure Chrome is installed.")
        
        try:
            # First try to find existing ChromeDriver
            print("Looking for existing ChromeDriver...")
            existing_driver_path = find_existing_chromedriver()
            
            if existing_driver_path:
                print(f"Trying to use existing ChromeDriver at: {existing_driver_path}")
                try:
                    # Check compatibility first
                    if is_chromedriver_compatible(existing_driver_path):
                        service = Service(executable_path=existing_driver_path)
                        chrome_options.add_argument("--user-data-dir=")  # Remove user data dir to avoid conflicts
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                    else:
                        print("Existing ChromeDriver is not compatible with installed Chrome, trying another approach")
                except Exception as driver_error:
                    print(f"Error using existing ChromeDriver: {driver_error}")
                    # Continue to next fallback
            
            if not driver:
                print("Falling back to webdriver-manager initialization...")
                try:
                    # Try with webdriver-manager approach which handles Chrome version matching
                    service = Service(ChromeDriverManager().install())
                    chrome_options.add_argument("--user-data-dir=")  # Remove user data dir to avoid conflicts
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                except Exception as service_error:
                    print(f"WebDriver Manager approach failed: {service_error}")
                    
                    # Try manual download of ChromeDriver
                    print("Trying with manually downloaded ChromeDriver...")
                    chromedriver_path = download_chromedriver_manually(chrome_version)
                    
                    if chromedriver_path and os.path.exists(chromedriver_path):
                        print(f"Using manually downloaded ChromeDriver at: {chromedriver_path}")
                        # Check compatibility for the manually downloaded driver
                        is_compatible = is_chromedriver_compatible(chromedriver_path)
                        print(f"Manual ChromeDriver compatibility: {is_compatible}")
                        
                        # Create a new service with the manually downloaded chromedriver
                        service = Service(executable_path=chromedriver_path)
                        # Create new options without user data dir to avoid conflicts
                        clean_options = Options()
                        clean_options.add_argument("--no-sandbox")
                        clean_options.add_argument("--disable-dev-shm-usage")
                        clean_options.add_argument("--disable-gpu")
                        
                        # Add chrome binary if found
                        if chrome_path:
                            clean_options.binary_location = chrome_path
                        
                        driver = webdriver.Chrome(service=service, options=clean_options)
                    else:
                        # Last fallback: Try with default Chrome settings without user profile
                        print("Trying with default Chrome settings without user profile...")
                        basic_options = Options()
                        basic_options.add_argument("--no-sandbox")
                        basic_options.add_argument("--disable-dev-shm-usage")
                        basic_options.add_argument("--disable-gpu")
                        
                        # Add chrome binary if found
                        if chrome_path:
                            basic_options.binary_location = chrome_path
                        
                        # Try one last time with the most basic setup
                        driver = webdriver.Chrome(options=basic_options)
        except Exception as e2:
            print(f"Error with all fallback approaches: {e2}")
            error_message = str(e2)
            
            # Special handling for common errors
            troubleshooting_tips = [
                "1. Make sure Chrome is installed",
                "2. Try running the script with admin privileges",
                "3. Check if ChromeDriver is in your PATH"
            ]
            
            if "not a valid Win32 application" in error_message or "WinError 193" in error_message:
                print("Detected WinError 193 - This usually means you have a 32-bit/64-bit mismatch")
                troubleshooting_tips.extend([
                    "4. Make sure you're using a ChromeDriver that matches your Chrome architecture (32-bit or 64-bit)",
                    "5. Try manually downloading ChromeDriver from https://chromedriver.chromium.org/downloads",
                    "6. Place the chromedriver.exe in the same directory as this script"
                ])
            
            if "session not created" in error_message:
                print("Detected 'session not created' error - This usually means version mismatch")
                troubleshooting_tips.extend([
                    "4. Make sure your ChromeDriver version matches your Chrome browser version",
                    "5. Update your Chrome browser to the latest version",
                    "6. Download the matching ChromeDriver from https://chromedriver.chromium.org/downloads"
                ])
            
            return {
                "video_url": youtube_url,
                "status": "Error",
                "message": "Failed to initialize Chrome",
                "error_details": error_message,
                "troubleshooting_tips": "\n".join(troubleshooting_tips)
            }
    
    if not driver:
        return {
            "video_url": youtube_url,
            "status": "Error",
            "message": "Failed to initialize browser"
        }
    
    try:
        # Navigate to the YouTube video
        print(f"Navigating to {youtube_url}")
        driver.get(youtube_url)
        
        # Wait for the video to load
        print("Waiting for video player to load...")
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "movie_player"))
        )
        print("Video loaded successfully")
        
        # Give Eightify time to load
        print("Waiting for Eightify to load...")
        time.sleep(10)
        
        # Look for the Eightify iframe
        try:
            print("Looking for Eightify iframe...")
            
            # Try to find the iframe directly
            iframe_found = False
            eightify_data = {
                "key_insights": "",
                "timestamped_summary": "",
                "top_comments": "",
                "transcript": ""
            }
    
            iframe_selectors = [
                "#eightify-iframe",
                "iframe[title*='Eightify']",
                "iframe[src*='eightify']",
                "iframe.eightify",
                "iframe"  # Last resort: try all iframes
            ]
            
            for selector in iframe_selectors:
                try:
                    iframes = driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"Found {len(iframes)} iframes with selector: {selector}")
                    
                    if iframes:
                        for iframe in iframes:
                            try:
                                # Check if this iframe is visible and seems to be Eightify
                                if iframe.is_displayed() and (iframe.get_attribute("id") == "eightify-iframe" or selector == "iframe"):
                                    print(f"Found potential Eightify iframe! ID: {iframe.get_attribute('id')}")
                    
                                    # Switch to the iframe
                                    driver.switch_to.frame(iframe)
                                    try:
                                        main_summarize_selectors = [
                                            "//button[contains(text(), 'Summarize Video')]",
                                            "//button[contains(text(), 'Summarize')]",
                                            "//button[.//span[contains(text(), 'Summarize')]]",
                                            "//div[@role='button' and contains(text(), 'Summarize')]",
                                            "button.SummaryButton_button__hMBbW",
                                            "button.summarize-button",
                                            "button.primary",
                                            "button.btn-primary",
                                            "button.cta",
                                            "div[role='button']"
                                        ]
                                        
                                        main_button_clicked = False
                                        for main_selector in main_summarize_selectors:
                                            if main_button_clicked:
                                                break
                                                
                                            try:
                                                if main_selector.startswith("//"):
                                                    # XPath selector
                                                    buttons = driver.find_elements(By.XPATH, main_selector)
                                                else:
                                                    # CSS selector
                                                    buttons = driver.find_elements(By.CSS_SELECTOR, main_selector)
                                                    
                                                for button in buttons:
                                                    if button.is_displayed():
                                                        print(f"Found main summarize button with selector: {main_selector}")
                                                        driver.execute_script("arguments[0].click();", button)
                                                        main_button_clicked = True
                                                        print("Clicked main summarize button, waiting for processing...")
                                                        time.sleep(20)  # Extended wait time for main processing
                                                        break
                                            except Exception as e:
                                                print(f"Error with main button selector {main_selector}: {e}")
                                                
                                        if main_button_clicked:
                                            print("Successfully clicked main summarize button. Now checking for tabs.")
                                    except Exception as main_btn_error:
                                        print(f"Error handling main summarize button: {main_btn_error}")
                                    
                                    # Find the "Summarize Video" button and click it if it exists
                                    try:
                                        # First try to detect if content is already generated
                                        content_present = False
                                        try:
                                            # Check if there's already content present
                                            existing_content = driver.find_elements(By.CSS_SELECTOR, ".SummaryTabsView_content__6OYs8, [class*='content'], .tab-content")
                                            for element in existing_content:
                                                if element.is_displayed() and len(element.text.strip()) > 50:
                                                    content_present = True
                                                    print("Content already present, no need to click the summarize button")
                                                    break
                                        except Exception:
                                            pass
                                    except Exception as btn_error:
                                        print(f"Error handling summarize button: {btn_error}")
                            
                                    tab_data = {}
                                    
                                    try:
                                        # First try to find the tabs with the specific class names from HTML
                                        tabs = driver.find_elements(By.CSS_SELECTOR, ".SummaryTabsView_item__Zjswl, .SummaryTabsView_tabs__69LdY > div, button[role='tab'], .tab, div[role='tab']")
                                        
                                        if tabs:
                                            print(f"Found {len(tabs)} tabs in the Eightify interface")
                                            
                                            # Define which tabs to process
                                            tab_types = ["key_insights", "timestamped_summary", "top_comments", "transcript"]
                                            
                                            # Process one tab at a time - First click all tabs and their buttons before extracting content
                                            print("FIRST PHASE: Clicking all tabs and their 'Summarize' buttons")
                                            for i, tab_type in enumerate(tab_types):
                                                try:
                                                    # Refind the tabs each time to avoid stale element references
                                                    tabs = driver.find_elements(By.CSS_SELECTOR, ".SummaryTabsView_item__Zjswl, .SummaryTabsView_tabs__69LdY > div, button[role='tab'], .tab, div[role='tab']")
                                                    if i >= len(tabs):
                                                        print(f"Not enough tabs found for {tab_type}, skipping")
                                                        continue
                                                        
                                                    tab = tabs[i]
                                                    print(f"Processing tab #{i}: {tab_type}")
                                                    
                                                    # Click the tab regardless of whether it's selected
                                                    print(f"Clicking tab for: {tab_type}")
                                                    driver.execute_script("arguments[0].click();", tab)
                                                    time.sleep(5)  # Wait for tab content to load
                                                    
                                                    summarize_selectors = [
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
                                                    
                                                    button_clicked = False
                                                    for btn_selector in summarize_selectors:
                                                        if button_clicked:
                                                            break
                                                            
                                                        try:
                                                            if btn_selector.startswith("//"):
                                                                
                                                                buttons = driver.find_elements(By.XPATH, btn_selector)
                                                            else:
                                                                
                                                                buttons = driver.find_elements(By.CSS_SELECTOR, btn_selector)
                                                                
                                                            for button in buttons:
                                                                if button.is_displayed():
                                                                    print(f"Found 'Summarize Video' button in {tab_type} tab with selector: {btn_selector}")
                                                                    driver.execute_script("arguments[0].click();", button)
                                                                    button_clicked = True
                                                                    print(f"Clicked 'Summarize Video' button in {tab_type} tab")
                                                                    time.sleep(5)  # Wait consistently after clicking each button
                                                                    break
                                                        except Exception as e:
                                                            print(f"Error with button selector {btn_selector} in {tab_type} tab: {e}")
                                                    
                                                    if not button_clicked:
                                                        print(f"Could not find 'Summarize Video' button in {tab_type} tab")
                                                        
                                                except Exception as tab_error:
                                                    print(f"Error accessing tab {i}: {tab_error}")
                                                    try:
                                                        # First switch back to default content
                                                        driver.switch_to.default_content()
                                                        time.sleep(1)
                                                        
                                                        # Find the iframe again
                                                        iframe = driver.find_element(By.CSS_SELECTOR, "#eightify-iframe")
                                                        driver.switch_to.frame(iframe)
                                                        print("Switched back to iframe context")
                                                    except Exception as recovery_error:
                                                        print(f"Failed to recover iframe context: {recovery_error}")
                                            
                                            # Wait for content to be generated in all tabs
                                            print("Waiting for all content to be generated (10 seconds)...")
                                            time.sleep(10)
                                            
                                            # SECOND PHASE: Now extract content from each tab
                                            print("SECOND PHASE: Extracting content from each tab")
                                            for i, tab_type in enumerate(tab_types):
                                                try:
                                                    # Refind the tabs each time to avoid stale element references
                                                    tabs = driver.find_elements(By.CSS_SELECTOR, ".SummaryTabsView_item__Zjswl, .SummaryTabsView_tabs__69LdY > div, button[role='tab'], .tab, div[role='tab']")
                                                    if i >= len(tabs):
                                                        print(f"Not enough tabs found for {tab_type}, skipping")
                                                        continue
                                                        
                                                    tab = tabs[i]
                                                    print(f"Extracting content from tab #{i}: {tab_type}")
                                                    
                                                    # Click the tab
                                                    print(f"Clicking tab for: {tab_type}")
                                                    driver.execute_script("arguments[0].click();", tab)
                                                    time.sleep(5) 
                                                    content_selectors = [
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
                                                    
                                                    content_found = False
                                                    for content_selector in content_selectors:
                                                        if content_found:
                                                            break
                                                            
                                                        try:
                                                            elements = driver.find_elements(By.CSS_SELECTOR, content_selector)
                                                            for element in elements:
                                                                if element.is_displayed():
                                                                    tab_content = element.text
                                                                    if tab_content and len(tab_content) > 50:
                                                                        tab_data[tab_type] = tab_content
                                                                        print(f"Extracted content from {tab_type} tab with selector {content_selector} ({len(tab_content)} chars)")
                                                                        content_found = True
                                                                        break
                                                        except Exception as selector_error:
                                                            print(f"Error with content selector {content_selector}: {selector_error}")
                                                            continue
                                                    
                                                    # If we still don't have content, try getting the entire body
                                                    if not content_found:
                                                        try:
                                                            body_text = driver.find_element(By.TAG_NAME, "body").text
                                                            if body_text and len(body_text) > 50:
                                                                tab_data[tab_type] = body_text
                                                                print(f"Extracted content from {tab_type} tab using body ({len(body_text)} chars)")
                                                                content_found = True
                                                        except Exception as body_error:
                                                            print(f"Error getting body text: {body_error}")
                                                        
                                                    # Take a screenshot of the tab content for debugging
                                                    # try:
                                                    #     driver.save_screenshot(f"{tab_type}_tab_content.png")
                                                    #     print(f"Saved screenshot of {tab_type} tab")
                                                    # except Exception as ss_error:
                                                    #     print(f"Could not save screenshot: {ss_error}")
                                                
                                                except Exception as tab_error:
                                                    # If we run into iframe context issues, try to switch back to the iframe
                                                    print(f"Error accessing tab {i}: {tab_error}")
                                                    try:
                                                        # First switch back to default content
                                                        driver.switch_to.default_content()
                                                        time.sleep(1)
                                                        
                                                        # Find the iframe again
                                                        iframe = driver.find_element(By.CSS_SELECTOR, "#eightify-iframe")
                                                        driver.switch_to.frame(iframe)
                                                        print("Switched back to iframe context")
                                                        
                                                        # Try accessing the tabs again
                                                        tabs = driver.find_elements(By.CSS_SELECTOR, ".SummaryTabsView_item__Zjswl, .SummaryTabsView_tabs__69LdY > div, button[role='tab'], .tab, div[role='tab']")
                                                        if i >= len(tabs):
                                                            print(f"Still not enough tabs found for {tab_type}, skipping")
                                                            continue
                                                        
                                                        tab = tabs[i]
                                                        print(f"Successfully recovered tab #{i}: {tab_type}")
                                                        
                                                        # Click the tab
                                                        print(f"Clicking recovered tab for: {tab_type}")
                                                        driver.execute_script("arguments[0].click();", tab)
                                                        time.sleep(3)
                                                        
                                                        # Try to extract content after recovery
                                                        try:
                                                            body_text = driver.find_element(By.TAG_NAME, "body").text
                                                            if body_text and len(body_text) > 50:
                                                                tab_data[tab_type] = body_text
                                                                print(f"Extracted content from recovered {tab_type} tab ({len(body_text)} chars)")
                                                        except Exception as recovery_content_error:
                                                            print(f"Error extracting content after recovery: {recovery_content_error}")
                                                    except Exception as recovery_error:
                                                        print(f"Failed to recover iframe context: {recovery_error}")
                                                        continue  # Skip to next tab
                                        
                                        # If no tabs found, try to get content directly
                                        if not any(tab_data.values()):
                                            print("No tab content found, trying to extract content directly")
                                            try:
                                                body_text = driver.find_element(By.TAG_NAME, "body").text
                                                if body_text:
                                                    # Try to identify which tab content we have based on patterns
                                                    if "Key Insights" in body_text or "Insights" in body_text:
                                                        tab_data["key_insights"] = body_text
                                                    elif "Transcript" in body_text and "00:00" in body_text:
                                                        tab_data["transcript"] = body_text
                                                    elif "Comments" in body_text:
                                                        tab_data["top_comments"] = body_text
                                                    else:
                                                        # Default to transcript if we can't identify
                                                        tab_data["transcript"] = body_text
                                            except Exception as direct_content_error:
                                                print(f"Error extracting direct content: {direct_content_error}")
                                    except Exception as content_error:
                                        print(f"Error extracting tab content: {content_error}")
                                    
                                    # Merge tab data with eightify_data, keeping existing data
                                    for key, value in tab_data.items():
                                        if value and (key not in eightify_data or not eightify_data[key]):
                                            eightify_data[key] = value
                                    
                                    # If we're still missing some tabs, try a direct extraction approach
                                    missing_tabs = [tab for tab in ["key_insights", "timestamped_summary", "top_comments", "transcript"] 
                                                  if not eightify_data.get(tab)]
                                    
                                    if missing_tabs:
                                        print(f"Still missing content for tabs: {missing_tabs}")
                                        print("Trying direct extraction approach...")
                                        
                                        # Get all text content from the iframe
                                        try:
                                            all_content = driver.find_element(By.TAG_NAME, "body").text
                                            
                                            # Try to segment the content by looking for section headers
                                            content_sections = {
                                                "key_insights": ["Key Insights", "Main Points", "Key Points", "Highlights"],
                                                "timestamped_summary": ["Timestamped Summary", "Summary", "Video Summary", "Timeline"],
                                                "top_comments": ["Top Comments", "Comments", "User Comments", "Best Comments"],
                                                "transcript": ["Transcript", "Full Transcript", "Video Transcript", "CC"]
                                            }
                                            
                                            # Look for section headers in the content
                                            for tab in missing_tabs:
                                                for header in content_sections[tab]:
                                                    if header in all_content:
                                                        # Find the section and extract it
                                                        start_idx = all_content.find(header)
                                                        if start_idx != -1:
                                                            # Find the next section header or use the end of text
                                                            end_idx = len(all_content)
                                                            for next_header in sum(content_sections.values(), []):
                                                                next_start = all_content.find(next_header, start_idx + len(header))
                                                                if next_start != -1 and next_start < end_idx:
                                                                    end_idx = next_start
                                                            
                                                            # Extract the section content
                                                            section_content = all_content[start_idx:end_idx].strip()
                                                            if len(section_content) > 50:
                                                                eightify_data[tab] = section_content
                                                                print(f"Extracted {tab} content through direct extraction ({len(section_content)} chars)")
                                                                break
                                        except Exception as direct_extract_error:
                                            print(f"Error in direct extraction: {direct_extract_error}")
                                    
                                    iframe_found = True
                            except Exception as iframe_error:
                                print(f"Error processing iframe: {iframe_error}")
                                driver.switch_to.default_content()  # Make sure we're back to the main content
                        
                        # If we've found some data, we can break the selector loop
                        if iframe_found and any(tab_data.values()):
                            break
                except Exception as selector_error:
                    print(f"Error with selector {selector}: {selector_error}")
            
            # Process transcript data if we found it
            if eightify_data.get("transcript"):
                print("Processing transcript text...")
                transcript_text = eightify_data["transcript"]
                print(f"First 100 characters: {transcript_text[:100]}...")
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
                        text = transcript_lines[i+1].strip()
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
                print("Successfully extracted Eightify data")
                for key, value in result.items():
                    if key not in ["video_url", "status", "structured_transcript"] and value:
                        print(f"- {key}: {len(value)} characters")
            else:
                result["message"] = "Could not locate Eightify data"
                result["next_steps"] = "1. Open the video in your normal browser and verify Eightify is working\n" \
                                "2. Check the saved HTML and screenshots for debugging"
                
            return result
        
        except Exception as e:
            print(f"Error during data extraction: {e}")
            
            with open("error_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            
            return {
                "video_url": youtube_url,
                "status": "Error",
                "message": f"Error during extraction: {str(e)}",
                "next_steps": "Check the saved HTML for debugging"
            }
                
    except Exception as e:
        print(f"Error: {str(e)}")
        if driver:
            print("Driver still active - browser control handed to main function")
            # No driver.quit() call here!

def close_existing_chrome(system):
    """Attempt to close any existing Chrome instances to avoid profile conflicts"""
    try:
        if system == "Windows":
            os.system("taskkill /f /im chrome.exe > nul 2>&1")
        elif system in ["Darwin", "Linux"]:
            os.system("pkill -f chrome > /dev/null 2>&1")
        print("Attempted to close existing Chrome instances")
        time.sleep(2)  # Give time for Chrome to fully close
    except:
        print("Failed to close Chrome, but continuing anyway")

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
    print(f"Eightify data saved to {output_file}")

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
        print(f"Navigating to {video_url}")
        driver.get(video_url)
        
        # Wait for the video to load
        print("Waiting for video player to load...")
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "movie_player"))
        )
        print("Video loaded successfully")
        
        # Give Eightify time to load
        print("Waiting for Eightify to load...")
        time.sleep(10)
        
        # Look for the Eightify iframe
        try:
            print("Looking for Eightify iframe...")
            
            # Try to find the iframe directly
            iframe_found = False
            eightify_data = {
                "video_url": video_url,
                "key_insights": "",
                "timestamped_summary": "",
                "top_comments": "",
                "transcript": ""
            }
            
            # Try to find the iframe by common selectors
            iframe_selectors = [
                "#eightify-iframe",
                "iframe[title*='Eightify']",
                "iframe[src*='eightify']",
                "iframe.eightify",
                "iframe"  # Last resort: try all iframes
            ]
            
            for selector in iframe_selectors:
                try:
                    iframes = driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"Found {len(iframes)} iframes with selector: {selector}")
                    
                    if iframes:
                        for iframe in iframes:
                            try:
                                # Check if this iframe is visible and seems to be Eightify
                                if iframe.is_displayed() and (iframe.get_attribute("id") == "eightify-iframe" or selector == "iframe"):
                                    print(f"Found potential Eightify iframe! ID: {iframe.get_attribute('id')}")
                                    
                                    # Switch to the iframe
                                    driver.switch_to.frame(iframe)
                                    
                                    # First look for a primary "Summarize Video" button that might be visible
                                    # before any tabs are accessible
                                    try:
                                        main_summarize_selectors = [
                                            "//button[contains(text(), 'Summarize Video')]",
                                            "//button[contains(text(), 'Summarize')]",
                                            "//button[.//span[contains(text(), 'Summarize')]]",
                                            "//div[@role='button' and contains(text(), 'Summarize')]",
                                            "button.SummaryButton_button__hMBbW",
                                            "button.summarize-button",
                                            "button.primary",
                                            "button.btn-primary",
                                            "button.cta",
                                            "div[role='button']"
                                        ]
                                        
                                        main_button_clicked = False
                                        for main_selector in main_summarize_selectors:
                                            if main_button_clicked:
                                                break
                                                
                                            try:
                                                if main_selector.startswith("//"):
                                                    # XPath selector
                                                    buttons = driver.find_elements(By.XPATH, main_selector)
                                                else:
                                                    # CSS selector
                                                    buttons = driver.find_elements(By.CSS_SELECTOR, main_selector)
                                                    
                                                for button in buttons:
                                                    if button.is_displayed():
                                                        print(f"Found main summarize button with selector: {main_selector}")
                                                        driver.execute_script("arguments[0].click();", button)
                                                        main_button_clicked = True
                                                        print("Clicked main summarize button, waiting for processing...")
                                                        time.sleep(20)  # Extended wait time for main processing
                                                        break
                                            except Exception as e:
                                                print(f"Error with main button selector {main_selector}: {e}")
                                                
                                        if main_button_clicked:
                                            print("Successfully clicked main summarize button. Now checking for tabs.")
                                    except Exception as main_btn_error:
                                        print(f"Error handling main summarize button: {main_btn_error}")
                                    
                                    # Find the "Summarize Video" button and click it if it exists
                                    try:
                                        # First try to detect if content is already generated
                                        content_present = False
                                        try:
                                            # Check if there's already content present
                                            existing_content = driver.find_elements(By.CSS_SELECTOR, ".SummaryTabsView_content__6OYs8, [class*='content'], .tab-content")
                                            for element in existing_content:
                                                if element.is_displayed() and len(element.text.strip()) > 50:
                                                    content_present = True
                                                    print("Content already present, no need to click the summarize button")
                                                    break
                                        except Exception:
                                            pass
                                    except Exception as btn_error:
                                        print(f"Error handling summarize button: {btn_error}")
                                    
                                    # Check if there are tabs for navigation
                                    tab_data = {}
                                    
                                    try:
                                        # First try to find the tabs with the specific class names from HTML
                                        tabs = driver.find_elements(By.CSS_SELECTOR, ".SummaryTabsView_item__Zjswl, .SummaryTabsView_tabs__69LdY > div, button[role='tab'], .tab, div[role='tab']")
                                        
                                        if tabs:
                                            print(f"Found {len(tabs)} tabs in the Eightify interface")
                                            
                                            # Define which tabs to process
                                            tab_types = ["key_insights", "timestamped_summary", "top_comments", "transcript"]
                                            
                                            # Process one tab at a time - First click all tabs and their buttons before extracting content
                                            print("FIRST PHASE: Clicking all tabs and their 'Summarize' buttons")
                                            for i, tab_type in enumerate(tab_types):
                                                try:
                                                    # Refind the tabs each time to avoid stale element references
                                                    tabs = driver.find_elements(By.CSS_SELECTOR, ".SummaryTabsView_item__Zjswl, .SummaryTabsView_tabs__69LdY > div, button[role='tab'], .tab, div[role='tab']")
                                                    if i >= len(tabs):
                                                        print(f"Not enough tabs found for {tab_type}, skipping")
                                                        continue
                                                        
                                                    tab = tabs[i]
                                                    print(f"Processing tab #{i}: {tab_type}")
                                                    
                                                    # Click the tab regardless of whether it's selected
                                                    print(f"Clicking tab for: {tab_type}")
                                                    driver.execute_script("arguments[0].click();", tab)
                                                    time.sleep(5)  # Wait for tab content to load
                                                    
                                                    # Look for and click "Summarize Video" button
                                                    summarize_selectors = [
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
                                                    
                                                    button_clicked = False
                                                    for btn_selector in summarize_selectors:
                                                        if button_clicked:
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
                                                                    print(f"Found 'Summarize Video' button in {tab_type} tab with selector: {btn_selector}")
                                                                    driver.execute_script("arguments[0].click();", button)
                                                                    button_clicked = True
                                                                    print(f"Clicked 'Summarize Video' button in {tab_type} tab")
                                                                    time.sleep(5)  # Wait consistently after clicking each button
                                                                    break
                                                        except Exception as e:
                                                            print(f"Error with button selector {btn_selector} in {tab_type} tab: {e}")
                                                    
                                                    if not button_clicked:
                                                        print(f"Could not find 'Summarize Video' button in {tab_type} tab")
                                                        
                                                    # Remove screenshot line
                                                    # driver.save_screenshot(f"{tab_type}_after_button_click.png")
                                                        
                                                except Exception as tab_error:
                                                    print(f"Error accessing tab {i}: {tab_error}")
                                                    try:
                                                        # First switch back to default content
                                                        driver.switch_to.default_content()
                                                        time.sleep(1)
                                                        
                                                        # Find the iframe again
                                                        iframe = driver.find_element(By.CSS_SELECTOR, "#eightify-iframe")
                                                        driver.switch_to.frame(iframe)
                                                        print("Switched back to iframe context")
                                                    except Exception as recovery_error:
                                                        print(f"Failed to recover iframe context: {recovery_error}")
                                            
                                            # Wait for content to be generated in all tabs
                                            print("Waiting for all content to be generated (10 seconds)...")
                                            time.sleep(10)
                                            
                                            # SECOND PHASE: Now extract content from each tab
                                            print("SECOND PHASE: Extracting content from each tab")
                                            for i, tab_type in enumerate(tab_types):
                                                try:
                                                    # Refind the tabs each time to avoid stale element references
                                                    tabs = driver.find_elements(By.CSS_SELECTOR, ".SummaryTabsView_item__Zjswl, .SummaryTabsView_tabs__69LdY > div, button[role='tab'], .tab, div[role='tab']")
                                                    if i >= len(tabs):
                                                        print(f"Not enough tabs found for {tab_type}, skipping")
                                                        continue
                                                        
                                                    tab = tabs[i]
                                                    print(f"Extracting content from tab #{i}: {tab_type}")
                                                    
                                                    # Click the tab
                                                    print(f"Clicking tab for: {tab_type}")
                                                    driver.execute_script("arguments[0].click();", tab)
                                                    time.sleep(5)  # Wait for tab content to load
                                                    
                                                    # Now try to extract the content
                                                    # Try multiple selectors to get tab content
                                                    content_selectors = [
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
                                                    
                                                    content_found = False
                                                    for content_selector in content_selectors:
                                                        if content_found:
                                                            break
                                                            
                                                        try:
                                                            elements = driver.find_elements(By.CSS_SELECTOR, content_selector)
                                                            for element in elements:
                                                                if element.is_displayed():
                                                                    tab_content = element.text
                                                                    if tab_content and len(tab_content) > 50:
                                                                        tab_data[tab_type] = tab_content
                                                                        print(f"Extracted content from {tab_type} tab with selector {content_selector} ({len(tab_content)} chars)")
                                                                        content_found = True
                                                                        break
                                                        except Exception as selector_error:
                                                            print(f"Error with content selector {content_selector}: {selector_error}")
                                                            continue
                                                    
                                                    # If we still don't have content, try getting the entire body
                                                    if not content_found:
                                                        try:
                                                            body_text = driver.find_element(By.TAG_NAME, "body").text
                                                            if body_text and len(body_text) > 50:
                                                                tab_data[tab_type] = body_text
                                                                print(f"Extracted content from {tab_type} tab using body ({len(body_text)} chars)")
                                                                content_found = True
                                                        except Exception as body_error:
                                                            print(f"Error getting body text: {body_error}")
                                                        
                                                    # Remove these screenshot lines
                                                    # try:
                                                    #     driver.save_screenshot(f"{tab_type}_tab_content.png")
                                                    #     print(f"Saved screenshot of {tab_type} tab")
                                                    # except Exception as ss_error:
                                                    #     print(f"Could not save screenshot: {ss_error}")
                                                
                                                except Exception as tab_error:
                                                    print(f"Error accessing tab {i}: {tab_error}")
                                            
                                            # Merge tab data with eightify_data
                                            for key, value in tab_data.items():
                                                if value:
                                                    eightify_data[key] = value
                                        
                                        # Switch back to main content
                                        driver.switch_to.default_content()
                                    except Exception as content_error:
                                        print(f"Error extracting tab content: {content_error}")
                                        driver.switch_to.default_content()
                                    
                                    iframe_found = True
                                    break
                            except Exception as iframe_error:
                                print(f"Error processing iframe: {iframe_error}")
                                driver.switch_to.default_content()  # Make sure we're back to the main content
                        
                        if iframe_found:
                            break
                except Exception as selector_error:
                    print(f"Error with selector {selector}: {selector_error}")
            
            # Process transcript data if we found it
            if eightify_data.get("transcript"):
                print("Processing transcript text...")
                transcript_text = eightify_data["transcript"]
                print(f"First 100 characters: {transcript_text[:100]}...")
                
                # Return the result with status
                eightify_data["status"] = "Success" if any(value for key, value in eightify_data.items() 
                                                    if key in ["key_insights", "timestamped_summary", "top_comments", "transcript"]) else "Error"
                
                return eightify_data
            else:
                # Return whatever data we have
                eightify_data["status"] = "Success" if any(value for key, value in eightify_data.items() 
                                                    if key in ["key_insights", "timestamped_summary", "top_comments", "transcript"]) else "Error"
                return eightify_data
        except Exception as e:
            print(f"Error extracting data: {e}")
            return {
                "video_url": video_url,
                "status": "Error",
                "message": f"Error during extraction: {str(e)}"
            }
    except Exception as e:
        print(f"Error navigating to URL: {e}")
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
        path to the chromedriver executable or None if download fails
    """
    try:
        if not chrome_version:
            chrome_version = get_chrome_version()
            
        if not chrome_version:
            print("Could not determine Chrome version, using latest ChromeDriver")
            chrome_driver_url = "https://chromedriver.storage.googleapis.com/LATEST_RELEASE"
            with urllib.request.urlopen(chrome_driver_url) as response:
                version = response.read().decode('utf-8').strip()
        else:
            # Extract major version (e.g., "94.0.4606.81" -> "94")
            major_version = chrome_version.split('.')[0]
            print(f"Detected Chrome major version: {major_version}")
            
            # Get the latest ChromeDriver version for this Chrome version
            chrome_driver_url = f"https://chromedriver.storage.googleapis.com/LATEST_RELEASE_{major_version}"
            try:
                with urllib.request.urlopen(chrome_driver_url) as response:
                    version = response.read().decode('utf-8').strip()
            except Exception as e:
                print(f"Error getting driver for version {major_version}: {e}")
                # Fallback to latest version
                chrome_driver_url = "https://chromedriver.storage.googleapis.com/LATEST_RELEASE"
                with urllib.request.urlopen(chrome_driver_url) as response:
                    version = response.read().decode('utf-8').strip()
                    
        print(f"Downloading ChromeDriver version: {version}")
        
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
        print(f"Downloading from: {download_url}")
        
        # Create temp directory for ChromeDriver
        driver_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver_temp")
        os.makedirs(driver_dir, exist_ok=True)
        
        zip_file_path = os.path.join(driver_dir, "chromedriver.zip")
        driver_path = os.path.join(driver_dir, "chromedriver.exe" if system == "Windows" else "chromedriver")
        
        # Download zip file
        urllib.request.urlretrieve(download_url, zip_file_path)
        
        # Extract zip file
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(driver_dir)
            
        # Make chromedriver executable on Linux/Mac
        if system != "Windows":
            os.chmod(driver_path, 0o755)
            
        print(f"ChromeDriver downloaded to: {driver_path}")
        return driver_path
        
    except Exception as e:
        print(f"Error downloading ChromeDriver: {e}")
        traceback.print_exc()
        return None

def check_chrome_installation():
    """
    Check if Chrome browser is properly installed and accessible
    """
    system = platform.system()
    chrome_executable = None
    
    if system == "Windows":
        # Common Chrome locations on Windows
        possible_paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            os.path.join(os.environ.get('LOCALAPPDATA', ''), "Google\\Chrome\\Application\\chrome.exe")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                chrome_executable = path
                break
    elif system == "Darwin":  # macOS
        if os.path.exists('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'):
            chrome_executable = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    else:  # Linux
        # Try to locate chrome using 'which'
        try:
            chrome_executable = subprocess.check_output(['which', 'google-chrome']).decode('utf-8').strip()
        except:
            try:
                chrome_executable = subprocess.check_output(['which', 'chrome']).decode('utf-8').strip()
            except:
                pass
    
    if chrome_executable and os.path.exists(chrome_executable):
        print(f"Found Chrome browser at: {chrome_executable}")
        return chrome_executable
    else:
        print("Warning: Chrome browser not found in common locations")
        return None

def find_existing_chromedriver():
    """
    Find existing ChromeDriver in the system PATH
    """
    system = platform.system()
    driver_executable = "chromedriver.exe" if system == "Windows" else "chromedriver"
    
    # Check in current directory first
    current_dir_driver = os.path.join(os.path.dirname(os.path.abspath(__file__)), driver_executable)
    if os.path.exists(current_dir_driver):
        print(f"Found ChromeDriver in current directory: {current_dir_driver}")
        return current_dir_driver
    
    # Check in PATH
    for path_dir in os.environ.get('PATH', '').split(os.pathsep):
        driver_path = os.path.join(path_dir, driver_executable)
        if os.path.exists(driver_path):
            print(f"Found ChromeDriver in PATH: {driver_path}")
            return driver_path
    
    # On Windows, check in Program Files and other common locations
    if system == "Windows":
        possible_paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chromedriver.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chromedriver.exe",
            os.path.join(os.environ.get('LOCALAPPDATA', ''), "Google\\Chrome\\Application\\chromedriver.exe"),
            # ChromeDriver might be in webdriver-manager cache
            os.path.join(os.environ.get('LOCALAPPDATA', ''), ".wdm\\drivers\\chromedriver\\win32\\*\\chromedriver.exe")
        ]
        
        for path in possible_paths:
            if '*' in path:  # Handle glob pattern
                matching_files = glob.glob(path)
                if matching_files:
                    # Sort by modified time to get the most recent one
                    newest_driver = max(matching_files, key=os.path.getmtime)
                    print(f"Found ChromeDriver using glob pattern: {newest_driver}")
                    return newest_driver
            elif os.path.exists(path):
                print(f"Found ChromeDriver in common location: {path}")
                return path
    
    print("Could not find existing ChromeDriver")
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
            print("Could not determine Chrome version for compatibility check")
            return False
        
        # Get ChromeDriver version
        system = platform.system()
        if system == "Windows":
            cmd = f'"{driver_path}" --version'
        else:
            cmd = f'"{driver_path}" --version'
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        driver_output = result.stdout
        
        # Parse the version number
        # Output is like: "ChromeDriver 94.0.4606.61"
        if driver_output and "ChromeDriver" in driver_output:
            driver_version_str = driver_output.split(' ')[1]
            driver_major = driver_version_str.split('.')[0]
            
            # Chrome version like "94.0.4606.81"
            chrome_major = chrome_version.split('.')[0]
            
            print(f"Chrome version: {chrome_version} (major: {chrome_major})")
            print(f"ChromeDriver version: {driver_version_str} (major: {driver_major})")
            
            # Major versions should match
            if driver_major == chrome_major:
                print("Chrome and ChromeDriver versions are compatible")
                return True
            else:
                print(f"Warning: Chrome version ({chrome_major}) and ChromeDriver version ({driver_major}) mismatch")
                return False
        else:
            print(f"Could not determine ChromeDriver version from output: {driver_output}")
            return False
    except Exception as e:
        print(f"Error checking ChromeDriver compatibility: {e}")
        return False

if __name__ == "__main__":
    # Suppress unnecessary logging
    import logging
    logging.basicConfig(level=logging.ERROR)
    
    # Global driver variable that will stay in scope
    global_driver = None
    
    try:
        print("\n===== Eightify Data Extractor =====\n")
        
        # Print system info
        system = platform.system()
        print(f"Operating System: {system}")
        chrome_version = get_chrome_version()
        print(f"Chrome Version: {chrome_version}")
        
        # Check for existing ChromeDriver
        existing_driver = find_existing_chromedriver()
        if existing_driver:
            print(f"Found existing ChromeDriver: {existing_driver}")
            if chrome_version:
                compatibility = is_chromedriver_compatible(existing_driver)
                print(f"ChromeDriver compatibility: {compatibility}")
                if not compatibility:
                    print("\n==== IMPORTANT: ChromeDriver Version Mismatch ====")
                    print("Your Chrome browser version doesn't match your ChromeDriver version.")
                    print("This may cause errors when running the script.")
                    print("\nYou can manually download the correct ChromeDriver version:")
                    print(f"1. Visit: https://chromedriver.chromium.org/downloads")
                    if chrome_version:
                        major_version = chrome_version.split('.')[0]
                        print(f"2. Download ChromeDriver version that matches Chrome {major_version}")
                    else:
                        print("2. Download ChromeDriver version that matches your Chrome version")
                    print("3. Extract the downloaded zip file")
                    print("4. Place chromedriver.exe in this script's directory")
                    print("================================================================\n")
        else:
            print("No ChromeDriver found in PATH or common locations")
            print("\n==== IMPORTANT: ChromeDriver Not Found ====")
            print("ChromeDriver is required to run this script.")
            print("\nYou can manually download ChromeDriver:")
            print("1. Visit: https://chromedriver.chromium.org/downloads")
            if chrome_version:
                major_version = chrome_version.split('.')[0]
                print(f"2. Download ChromeDriver version that matches Chrome {major_version}")
            else:
                print("2. Download ChromeDriver version that matches your Chrome version")
            print("3. Extract the downloaded zip file")
            print("4. Place chromedriver.exe in this script's directory")
            print("============================================\n")
            
        # Output file for all results
        output_file = "eightify_data.json"

        # Check for command-line arguments for input file
        if len(sys.argv) > 1:
            input_file = sys.argv[1]
            print(f"Using input file from command line: {input_file}")
        else:
            input_file = "video_urls.txt"

        # Check if input file exists
        if not os.path.exists(input_file):
            print(f"Error: {input_file} not found.")
            video_url = input("Enter YouTube video URL manually: ")
            urls_to_process = [video_url]
        else:
            # Read URLs from file
            with open(input_file, 'r', encoding='utf-8') as f:
                urls_to_process = [line.strip() for line in f if line.strip()]
            
            print(f"Found {len(urls_to_process)} URLs to process in {input_file}")
        
        # Initialize results dictionary
        all_results = {}
        
        # Try to load existing results if available
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    all_results = json.load(f)
                print(f"Loaded existing results from {output_file} with {len(all_results)} entries")
            except Exception as e:
                print(f"Error loading existing results: {e}")
        
        # Store the driver in the global variable
        def capture_driver(driver):
            global global_driver
            global_driver = driver
            return driver

        # Monkey patch the webdriver.Chrome to capture the driver object
        original_chrome = webdriver.Chrome
        webdriver.Chrome = lambda *args, **kwargs: capture_driver(original_chrome(*args, **kwargs))

        # Process each URL
        for i, video_url in enumerate(urls_to_process):
            # Skip URLs that have already been processed
            if video_url in all_results:
                print(f"\n[{i+1}/{len(urls_to_process)}] Skipping already processed URL: {video_url}")
                continue
                
            print(f"\n[{i+1}/{len(urls_to_process)}] Processing: {video_url}")
            
            # Disable warnings
            import warnings
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            
            # Initialize variables for retry mechanism
            max_retries = 2
            retry_count = 0
            success = False
            
            while retry_count <= max_retries and not success:
                try:
                    # If retry_count > 0, we're in a retry attempt
                    if retry_count > 0:
                        print(f"Retry attempt {retry_count}/{max_retries} for {video_url}")
                        
                        # Force a new browser instance for retries
                        if global_driver is not None:
                            try:
                                print("Closing existing browser for retry...")
                                global_driver.quit()
                            except Exception as close_error:
                                print(f"Error closing browser: {close_error}")
                            finally:
                                global_driver = None
                    
                    # Create a new browser instance if needed
                    if global_driver is None:
                        print("\nStarting data extraction with new browser instance...")
                        # Close any existing Chrome instances to avoid conflicts
                        close_existing_chrome(system)
                        # Initialize a new browser with the first URL
                        eightify_data = scrape_eightify_data(video_url, keep_browser_open=True, close_existing=True)
                    else:
                        # For subsequent URLs, first check if the driver is still responsive
                        try:
                            print("Checking if browser is still responsive...")
                            # Simple operation to check browser responsiveness
                            _ = global_driver.current_url
                            # Force a clean state by refreshing the page
                            global_driver.refresh()
                            time.sleep(3)
                            
                            print("Browser is responsive. Trying to process next URL...")
                            # Process the URL in the existing browser
                            eightify_data = process_next_url(global_driver, video_url)
                        except Exception as driver_error:
                            print(f"Browser is not responsive: {driver_error}")
                            print("Creating a new browser instance...")
                            # If driver is not responsive, recreate it
                            try:
                                if global_driver is not None:
                                    global_driver.quit()
                            except:
                                pass
                            global_driver = None
                            close_existing_chrome(system)
                            eightify_data = scrape_eightify_data(video_url, keep_browser_open=True, close_existing=True)
                    
                    # Check if extraction was successful
                    if (eightify_data.get("status") == "Success" or 
                        any(eightify_data.get(key, "") for key in ["key_insights", "timestamped_summary", "top_comments", "transcript"])):
                        success = True
                        print(f"Successfully extracted data for {video_url}")
                    else:
                        print(f"Extraction failed: {eightify_data.get('message', 'No error message')}")
                        retry_count += 1
                
                except Exception as extraction_error:
                    print(f"Error during extraction: {extraction_error}")
                    retry_count += 1
                    # Wait before retrying
                    time.sleep(5)
            
            # Create the data structure for this URL
            url_data = {
                "key_insights": eightify_data.get("key_insights", ""),
                "timestamped_summary": eightify_data.get("timestamped_summary", ""),
                "top_comments": eightify_data.get("top_comments", ""),
                "transcript": eightify_data.get("transcript", "")
            }
            
            # Add to results
            all_results[video_url] = url_data
            
            # Save all results after each URL is processed
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)
            print(f"Updated results saved to {output_file}")
            
            if not success:
                print(f"\n❌ Failed to extract data for {video_url} after {max_retries} retries")
            else:
                print(f"\n✅ Successfully extracted data for {video_url}!")
                items_found = sum(1 for key, value in url_data.items() if value)
                print(f"Found data in {items_found}/4 tabs")
            
            # Reset browser between videos if needed
            if not success or i == len(urls_to_process) - 1:
                continue
                
            # Prepare browser for next URL
            try:
                # If the browser is working well, create a new tab for the next URL
                if global_driver is not None:
                    print(f"Creating a clean new tab for next URL...")
                    # Create a new tab
                    global_driver.execute_script("window.open('about:blank', '_blank');")
                    time.sleep(2)
                    # Close the old tab
                    old_handle = global_driver.window_handles[0]
                    global_driver.switch_to.window(global_driver.window_handles[-1])
                    global_driver.close()
                    global_driver.switch_to.window(global_driver.window_handles[0])
                    time.sleep(2)
                    print(f"Ready to process next URL in clean tab...")
            except Exception as tab_error:
                print(f"Error preparing browser for next URL: {tab_error}")
                # If we can't create a new tab, try closing the browser to force a new instance next time
                try:
                    if global_driver is not None:
                        global_driver.quit()
                except:
                    pass
                global_driver = None
                print("Browser reset for next URL")
        
        # Always keep the browser open at the end
        if global_driver is not None:
            print("\n=============================================")
            print("BROWSER IS OPEN - DO NOT CLOSE THIS TERMINAL")
            print("=============================================")
            print("Press Ctrl+C when you want to close the browser")
            
            try:
                while True:
                    time.sleep(10)  # Sleep to reduce CPU usage
                    # Check if the driver is still responsive
                    try:
                        current_url = global_driver.current_url
                        print(f"Browser still open at: {current_url}")
                    except:
                        print("Browser was closed externally")
                        break
            except KeyboardInterrupt:
                print("\nKeyboard interrupt detected")
            
    except Exception as e:
        print(f"Error in main program: {e}")
        traceback.print_exc()
    finally:
        # Restore original Chrome class
        if 'original_chrome' in locals():
            webdriver.Chrome = original_chrome