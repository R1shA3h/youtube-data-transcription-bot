# YouTube Eightify Scraper

A robust Python tool to automatically extract video summaries, key insights, timestamped content, top comments, and transcripts from YouTube videos using the Eightify Chrome extension.

## Overview

This script automates the process of:
1. Opening YouTube videos
2. Activating the Eightify extension
3. Extracting all generated content
4. Saving it to a structured JSON file

## Features

- 🔄 **Batch Processing**: Process multiple YouTube URLs from a text file
- 💾 **Automatic Saving**: Saves data to JSON with proper structure
- 🔍 **Comprehensive Extraction**: Gets key insights, timestamped summaries, top comments, and full transcripts
- 🛡️ **Error Recovery**: Robust error handling with automatic retries and recovery
- 📊 **Detailed Logging**: Comprehensive logging of all operations
- 🔄 **Resume Capability**: Skips already processed URLs

## Requirements

- Python 3.6+
- Google Chrome browser installed
- Eightify extension installed in Chrome
- Dependencies listed in `requirements.txt`

## Installation

1. **Clone the repository:**
   ```
   git clone <repository-url>
   cd youtube
   ```

2. **Install the required packages:**
   ```
   pip install -r requirements.txt
   ```

3. **Ensure you have Chrome installed**

4. **Install the Eightify Chrome extension**:
   - Visit [Chrome Web Store](https://chrome.google.com/webstore/detail/eightify-ai-summary-for-y/cdgadkjijolebefmemciecfkbkbhikmn)
   - Add the extension to Chrome

## Usage

1. **Prepare your input file:**
   - Create a file named `video_urls.txt` in the same directory as the script
   - Add one YouTube URL per line
   - Lines starting with `#` will be ignored (for comments)

2. **Run the script:**
   ```
   python eightify_scraper.py
   ```

3. **Check the output:**
   - Results will be saved to `eightify_data.json`
   - The script will log progress to the console

## Advanced Features

### Custom Configuration

Edit the constants at the top of the script to customize:
- Wait times
- Content selectors
- Minimum content length thresholds

### Browser Reuse

The script intelligently reuses the browser session between videos to:
- Reduce startup time
- Preserve extension state
- Minimize resource usage

### Error Handling

The script includes sophisticated error recovery for:
- YouTube player errors ("Something went wrong")
- Extension loading failures
- Network interruptions
- Stale elements and other Selenium issues

## Troubleshooting

### ChromeDriver Issues

If you encounter ChromeDriver compatibility problems:
- The script will attempt to download the correct version automatically
- If automatic download fails, it will provide instructions for manual installation

### YouTube Blocking

If YouTube detects automation and blocks access:
- The script includes automatic refresh and retry logic
- Adjust the wait times in the script constants for more reliable operation

### Missing Content

If some tabs aren't being extracted:
- Check if all tab types exist in the Eightify UI
- Increase the `WAIT_TIME_TAB_CONTENT` constant
- Ensure you have a stable internet connection

## License

[Specify your license here]

## Acknowledgments

- This tool uses the Eightify extension, which is not affiliated with this project
- Built with Selenium WebDriver for browser automation