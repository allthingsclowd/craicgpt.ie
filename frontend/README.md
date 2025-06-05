# CraicGPT.ie Frontend

## Description

This directory contains the frontend code for CraicGPT.ie, a dynamically generated online newspaper. The interface is designed to mimic a traditional newspaper layout, presenting articles, features, and other content fetched from a backend service.

The frontend consists of three main files:
*   `index.html`: The main HTML structure of the webpage. Includes a date picker and radio buttons for model selection.
*   `static_assets/style.css`: Contains all the CSS rules for styling the page, including responsive design for various screen sizes. It defines the newspaper-like layout using CSS Grid and styles for the controls.
*   `static_assets/main.js`: Handles the dynamic aspects of the site. It initializes the `js-datepicker` date picker, fetches content for the selected day's "newspaper" from a JSON endpoint, manages model selections from radio buttons, and populates the relevant sections of the HTML page accordingly.

## How It Works

1.  When a user visits `index.html`, the browser loads the basic page structure.
2.  The linked `static_assets/style.css` file is applied, styling the HTML elements.
3.  The `static_assets/main.js` script executes on page load:
    *   It initializes a `js-datepicker` date picker on the input field `#date-picker`, allowing users to select a specific date. By default, it selects today's date.
    *   It sets up radio buttons for selecting a preferred Large Language Model (LLM: ChatGPT, Gemini, Claude) and a preferred Image Generation model (ImageGen: Imagen, Stable Diffusion, DALL-E). These default to the first option or values specified in the fetched content's metadata.
    *   It then automatically fetches the content for the initially selected date (usually today) by constructing a URL (e.g., `/content/YYYY/MM/DD/todays_paper.json`).
    *   This JSON file is expected to contain all text and image data for that day, with different versions of content based on the LLM and ImageGen models (see "JSON Data Structure" section below).
    *   Upon receiving a successful response, `main.js` parses the JSON data and stores it globally.
    *   It then calls a `renderContent()` function which:
        *   Determines the currently selected LLM and ImageGen model from the radio buttons.
        *   Uses these selections to pick the appropriate text (from LLM outputs) and images (from ImageGen outputs) from the stored JSON data for each section of the page (e.g., main article title, text, and image; comparison article, etc.). Placeholder images (`static_assets/images/placeholder_article.png`, `static_assets/images/placeholder_ad.png`) are used if specific images are not found or during loading.
        *   Updates the HTML elements with this selected content.
    *   It also updates the displayed date (in a dedicated text element, not the date picker input itself directly after initial load) and the copyright year in the footer.
    *   If the content fetching fails for a selected date, an error message is displayed.
    *   **User Interaction:**
        *   **Changing the Date:** If the user selects a new date using the `js-datepicker`, its `onSelect` callback triggers `main.js` to fetch the new `todays_paper.json` for that date. Radio buttons are updated to reflect the default models specified in the new data's metadata, and the content is rendered.
        *   **Changing Radio Buttons:** If the user selects a different LLM or ImageGen model, `main.js` calls `renderContent()` again. This re-renders the *currently loaded* daily data using the new model choices, without re-fetching the JSON.

## JSON Data Structure for `todays_paper.json`

The `main.js` script expects the JSON file for each day to follow a specific structure. Below is an overview and an example:

*   **`publicationDate`**: A string representing the date of the newspaper content in "YYYY-MM-DD" format. This is used to confirm the date of the loaded content and can be used to set the date picker display.
*   **`metadata`**: An object containing:
    *   `bannerTitle`: The title to display in the newspaper banner (e.g., "CraicGPT.ie").
    *   `defaultLLM`: The key (e.g., "chatgpt") of the LLM whose content should be shown by default for this paper. This key should match one of the `value` attributes of the LLM radio buttons.
    *   `defaultImageGen`: The key (e.g., "imagen") of the Image Generator whose images should be shown by default. This key should match one of the `value` attributes of the ImageGen radio buttons.
*   **`contentSlots`**: An object where each key represents a section of the page (e.g., `mainArticle`, `comparisonArticle`, `llmStory`, `joke`, `authorBio`, `advertisements`). The keys for articles, stories, and jokes typically map to HTML element IDs used for populating content (e.g., `main-article-title`, `main-article-text`).
    *   Each content slot that varies by model can contain:
        *   `llmOutputs`: An object where keys are LLM identifiers (e.g., "chatgpt", "gemini", "claude"). The values are objects containing the actual content pieces like `title` (for articles) and `text` or `content`.
        *   `imageOutputs`: An object where keys are Image Generator identifiers (e.g., "imagen", "stablediffusion", "dalle"). The values are objects containing `imageUrl` and `imageAlt`.
    *   Some slots might only have `llmOutputs` (like `joke` or `llmStory`).
    *   Some slots might have directly embedded content if not versioned by model (e.g., `authorBio.text` or an array for `advertisements`).

**Example Snippet:**
```json
{
  "publicationDate": "2023-10-28",
  "metadata": {
    "bannerTitle": "The Daily Craic - AI Edition",
    "defaultLLM": "gemini",
    "defaultImageGen": "stablediffusion"
  },
  "contentSlots": {
    "mainArticle": {
      "promptText": "The original prompt used to generate the main article...",
      "llmOutputs": {
        "chatgpt": { "title": "ChatGPT's Take on Today", "text": "Detailed text generated by ChatGPT for the main article..." },
        "gemini":  { "title": "Gemini's Perspective for Today",  "text": "In-depth analysis by Gemini for the main article..." },
        "claude":  { "title": "Claude's Musings on Current Events", "text": "Thoughtful content from Claude for the main article..." }
      },
      "imageOutputs": {
        "imagen": { "imageUrl": "static_assets/images/main_imagen.jpg", "imageAlt": "Main article image by Imagen" },
        "stablediffusion": { "imageUrl": "static_assets/images/main_sd.jpg", "imageAlt": "Main article image by Stable Diffusion" },
        "dalle": { "imageUrl": "static_assets/images/main_dalle.jpg", "imageAlt": "Main article image by DALL-E" }
      }
    },
    "comparisonArticle": {
       "llmOutputs": { /* ... similar structure ... */ },
       "imageOutputs": { /* ... similar structure ... */ }
    },
    "llmStory": {
      "llmOutputs": {
        "chatgpt": { "content": "A short narrative by ChatGPT." },
        "gemini": { "content": "An intriguing tale spun by Gemini." }
      }
    },
    "joke": {
      "llmOutputs": {
        "chatgpt": { "content": "Why did the AI cross the road? To optimize the path!" },
        "gemini": { "content": "What's an AI's favorite music? Algo-rhythm and blues!" }
      }
    },
    "authorBio": {
        "text": "<p>Our esteemed editor, a sophisticated language model, works tirelessly... </p>"
    },
    "advertisements": [
        { "text": "Ad 1: Buy more GPUs!"},
        { "text": "Ad 2: Infinite RAM now on sale!"}
    ]
    // ... other content slots similarly structured ...
  }
}
```

## Prerequisites

*   **A modern web browser:** Chrome, Firefox, Safari, Edge, etc., that supports HTML5, CSS3, and modern JavaScript (ES6+).
*   **Web server (recommended for full functionality):**
    *   While `index.html` can be opened directly as a local file (`file:///...`), the dynamic content fetching via `main.js` (using `fetch` to `/content/...`) will likely fail due to Cross-Origin Resource Sharing (CORS) security restrictions in most browsers.
    *   To properly test the dynamic content loading, serve the `frontend` directory using a local web server (e.g., Python's `http.server`, Node.js `live-server` or `http-server`, Apache, Nginx).
*   **Dynamic Content Endpoint:** For full functionality, the backend service providing the `todays_paper.json` at the `/content/YYYY/MM/DD/` path must be operational and accessible to the frontend. The JSON file must conform to the structure expected by `main.js` (see "JSON Data Structure" section).
*   **js-datepicker Library:** The `js-datepicker` date picker library files (`datepicker.min.css`, `datepicker.min.js`) are included locally in `frontend/static_assets/vendor/js-datepicker/`.

## How to Test

1.  **Basic Structure & Styling (Offline):**
    *   Navigate to the `frontend` directory.
    *   Open `index.html` directly in your web browser.
    *   Verify the page layout, fonts, static elements, date picker, and radio buttons. Placeholder images `static_assets/images/placeholder_article.png` and `static_assets/images/placeholder_ad.png` should be visible where images are expected.
    *   Note: Dynamic content will likely show "Loading..." or placeholders, and console errors due to failed fetch are expected.

2.  **Dynamic Content Loading (Online/With Server & Endpoint):**
    *   Serve the `frontend` directory using a local web server.
    *   Ensure the content endpoint (`/content/YYYY/MM/DD/todays_paper.json`) is active and returns valid JSON conforming to the described structure.
    *   **Initial Load:**
        *   Open the page. Verify content for the current date loads.
        *   Check that the `js-datepicker` input field displays the current date in YYYY-MM-DD format.
        *   Confirm radio buttons (LLM & ImageGen) are set to their default values (either the first option in the HTML, or as specified by `defaultLLM`/`defaultImageGen` in the fetched day's metadata).
    *   **Date Selection:**
        *   Select a different date using the `js-datepicker`.
        *   Verify new content (if available for that date) is fetched and displayed.
        *   Confirm radio buttons update to the new date's default model selections from its metadata.
    *   **LLM Radio Buttons:**
        *   Change the selected LLM (e.g., from ChatGPT to Gemini).
        *   Verify that all text-based content sections (titles, articles, jokes, LLM stories) update to reflect the new LLM's output, using the currently loaded daily data. Images should remain unchanged.
    *   **Image Generator Radio Buttons:**
        *   Change the selected Image Generator (e.g., from Imagen to DALL-E).
        *   Verify that all images on the page (e.g., main article image, comparison article image) update to reflect the new Image Generator's output, using the currently loaded daily data. Text content should remain unchanged.
    *   **Selection Persistence & Defaults:**
        *   Manually select a non-default LLM and ImageGen.
        *   Change the date using the date picker. Verify the new content loads, and the radio buttons reset to the *new date's default* model selections (as defined in its metadata).
    *   **Console Checks:** Monitor the browser's developer console for errors (fetch errors, JSON parsing errors, rendering errors) and informative `console.log` messages from `main.js`.

3.  **Responsiveness:**
    *   Resize the browser window to different widths.
    *   Verify that the layout, including the controls area with the date picker and radio buttons, adjusts as expected.

## How to Debug

*   **Browser Developer Tools:**
    *   **Console:** Check for JavaScript errors, `console.log()` messages (e.g., selected date from picker, chosen LLM, chosen ImageGen, fetched `currentPaperData`), and network request failures.
    *   **Network Tab:** Inspect the `fetch` request for `todays_paper.json`. Verify the request URL (is the date correct?), status code, and the response payload (is it valid JSON matching the expected structure outlined above?).
    *   **Elements Tab (Inspector):** Inspect HTML structure, check if elements have content, and verify CSS.
*   **`console.log()` in `main.js`:**
    *   Verify `dateString` in `fetchContentForDate` is correct.
    *   Inspect `currentPaperData` after a successful fetch.
    *   Log `selectedLLM` and `selectedImageGen` at the start of `renderContent()` to ensure these reflect the current radio button states.
    *   When accessing nested data (e.g., `slots.mainArticle?.llmOutputs?.[selectedLLM]`), ensure the keys (`mainArticle`, `llmOutputs`, the value of `selectedLLM` like "chatgpt") exactly match those in your JSON file. Case sensitivity is critical.
*   **Mock Data for `todays_paper.json`:**
    *   Create local `todays_paper_example.json` files (perhaps one for "today" and another for a different date) in a structure like `frontend/content/YYYY/MM/DD/todays_paper.json` relative to your local server's document root. Or, temporarily modify the `contentUrl` in `main.js` to point to a fixed local test file path.
    *   This allows testing content parsing, rendering logic, and model switching independently of a live backend.
*   **Validate HTML and CSS:** Use online validators for syntax checks.

This updated README should provide a comprehensive guide for understanding and working with the enhanced frontend.
