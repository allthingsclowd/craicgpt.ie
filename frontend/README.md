# CraicGPT.ie Frontend

## Description

This directory contains the frontend code for CraicGPT.ie, a dynamically generated online newspaper. The interface is designed to mimic a traditional newspaper layout, presenting articles, features, and other content fetched from a backend service.

The frontend consists of three main files:
*   `index.html`: The main HTML structure of the webpage.
*   `static_assets/style.css`: Contains all the CSS rules for styling the page, including responsive design for various screen sizes. It defines the newspaper-like layout using CSS Grid.
*   `static_assets/main.js`: Handles the dynamic aspects of the site. It fetches content for the day's "newspaper" from a JSON endpoint and populates the relevant sections of the HTML page. It also manages displaying the current date.

## How It Works

1.  When a user visits `index.html`, the browser loads the basic page structure.
2.  The linked `static_assets/style.css` file is applied, styling the HTML elements to resemble a newspaper.
3.  The `static_assets/main.js` script executes on page load:
    *   It determines the current date.
    *   It constructs a URL to fetch a JSON file (e.g., `/content/YYYY/MM/DD/todays_paper.json`) which is expected to contain the day's content (headlines, articles, images, etc.).
    *   It sends an asynchronous request (fetch API) to this URL.
    *   Upon receiving a successful response, it parses the JSON data.
    *   It then dynamically updates the content of various HTML elements (identified by their IDs) with the data received from the JSON file. This includes article titles, text, image URLs, jokes, etc.
    *   It also updates the displayed date and the copyright year in the footer.
    *   If the content fetching fails, it displays an error message to the user.

## Prerequisites

*   **A modern web browser:** Chrome, Firefox, Safari, Edge, etc., that supports HTML5, CSS3, and modern JavaScript (ES6+).
*   **Web server (recommended for full functionality):**
    *   While `index.html` can be opened directly as a local file (`file:///...`), the dynamic content fetching via `main.js` (using `fetch` to `/content/...`) will likely fail due to Cross-Origin Resource Sharing (CORS) security restrictions in most browsers.
    *   To properly test the dynamic content loading, serve the `frontend` directory using a local web server (e.g., Python's `http.server`, Node.js `live-server` or `http-server`, Apache, Nginx).
*   **Dynamic Content Endpoint:** For full functionality, the backend service providing the `todays_paper.json` at the `/content/YYYY/MM/DD/` path must be operational and accessible to the frontend. The JSON file must conform to the structure expected by `main.js`.

## How to Test

1.  **Basic Structure & Styling (Offline):**
    *   Navigate to the `frontend` directory.
    *   Open `index.html` directly in your web browser.
    *   Verify that the page layout, fonts, and static elements (like the initial placeholder texts and author bio) are displayed correctly according to `style.css`.
    *   Note: Dynamic content (main article, comparison article, joke, etc.) will likely show "Loading..." or placeholder content and you might see errors in the browser console due to the fetch request failing.

2.  **Dynamic Content Loading (Online/With Server & Endpoint):**
    *   Serve the `frontend` directory using a local web server. For example, if you have Python installed, navigate to the parent directory of `frontend` in your terminal and run `python -m http.server` (or `python3 -m http.server`). Then access the page via `http://localhost:8000/frontend/`.
    *   Ensure the content endpoint (`/content/YYYY/MM/DD/todays_paper.json`, relative to the server root, or an absolute URL if `main.js` is modified) is active and returns valid JSON. You might need to create a sample `todays_paper.json` in the expected path within your local server's content directory for testing.
    *   Open the page through your local server in a web browser.
    *   Verify that all sections (main article, comparison article, date, joke, etc.) are populated with content fetched from the JSON file.
    *   Check the browser's developer console (usually F12) for any errors, especially related to the `fetch` request for `todays_paper.json`.
    *   Confirm that images are loaded if image URLs are provided in the JSON.

3.  **Responsiveness:**
    *   With the page open in your browser, resize the browser window to different widths (e.g., desktop, tablet, mobile sizes).
    *   Verify that the layout adjusts according to the responsive design rules in `style.css` (e.g., elements stacking, font size changes).

## How to Debug

*   **Browser Developer Tools:** This is your primary debugging tool.
    *   **Console:** Check for JavaScript errors, `console.log()` messages, and network request failures. The `main.js` script logs the fetched data and any errors encountered during the fetch process.
    *   **Network Tab:** Inspect the `fetch` request for `todays_paper.json`. Verify the request URL, status code, and the response payload. Check if the JSON is well-formed.
    *   **Elements Tab (Inspector):** Inspect the HTML structure to see if elements are rendered as expected and if dynamic content has been inserted correctly. Examine the CSS styles being applied to elements and debug any layout or styling issues.
*   **`console.log()` in `main.js`:**
    *   Add more `console.log()` statements at various points in `main.js` to trace the execution flow and inspect the values of variables (e.g., the constructed `contentUrl`, the `response` object, the parsed `data`).
*   **Mock Data for `todays_paper.json`:**
    *   If the backend endpoint is unavailable or unreliable during frontend development, you can create a local `todays_paper_example.json` file within the `frontend` directory (or `frontend/static_assets`).
    *   Temporarily modify the `contentUrl` variable in `main.js` to point to this local file:
        ```javascript
        // const contentUrl = `/content/${year}/${month}/${day}/todays_paper.json`;
        const contentUrl = 'todays_paper_example.json'; // Or 'static_assets/todays_paper_example.json'
        ```
    *   This allows you to test the content population logic independently of the backend. Remember to revert this change when deploying or testing with the actual backend.
*   **Validate HTML and CSS:** Use online validators (e.g., W3C HTML Validator, W3C CSS Validator) to check for syntax errors in your HTML and CSS files, although the current files are expected to be valid.
