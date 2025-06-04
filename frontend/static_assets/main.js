// /static_assets/main.js
// Author: graham land
// Date: 2023-10-27
// Purpose: Handles dynamic content loading and updates for the CraicGPT.ie website.

// Main function that runs when the window has finished loading
window.addEventListener('load', () => {
    // Create a new Date object to get the current date
    const today = new Date();
    // Get the current year
    const year = today.getFullYear();
    // Get the current month (0-indexed, so add 1) and pad with a leading zero if needed
    const month = String(today.getMonth() + 1).padStart(2, '0');
    // Get the current day and pad with a leading zero if needed
    const day = String(today.getDate()).padStart(2, '0');

    // Construct the URL for fetching the day's content from a JSON file
    const contentUrl = `/content/${year}/${month}/${day}/todays_paper.json`;
    // For local testing, you might point to a local file or a fixed CloudFront URL
    // const contentUrl = 'todays_paper_example.json'; 

    // Update current date display on the page
    const dateElement = document.getElementById('current-date');
    if (dateElement) {
        // Format the date to a long form (e.g., "Monday, 27 October 2023")
        dateElement.textContent = today.toLocaleDateString('en-IE', { 
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' 
        });
    }
    
    // Update footer year with the current year
    const footerYearElement = document.getElementById('footer-year');
    if (footerYearElement) {
        footerYearElement.textContent = year;
    }

    // Fetch the content from the constructed URL
    fetch(contentUrl)
       .then(response => {
            // Check if the network response is successful
            if (!response.ok) {
                // If not successful, throw an error with the status text and code
                throw new Error(`Network response was not ok: ${response.statusText} (Status: ${response.status})`);
            }
            // If successful, parse the response body as JSON
            return response.json();
        })
       .then(data => {
            // Log the fetched content for debugging purposes
            console.log("Fetched content:", data);

            // Update various sections of the page with the fetched data
            // Update newspaper banner title
            updateElement('newspaper-banner', data.banner?.title, true, 'h1');
            // Update current date (can be overridden by JSON, though already set above)
            updateElement('current-date', data.date, false);

            // Update Main Article section
            updateElement('main-article-title', data.mainArticle?.title, true, 'h2');
            updateImage('main-article-image', data.mainArticle?.imageUrl, data.mainArticle?.imageAlt);
            updateElement('main-article-text', data.mainArticle?.text, true);

            // Update Comparison Article section
            updateElement('comparison-article-title', data.comparisonArticle?.title, true, 'h2');
            updateImage('comparison-article-image', data.comparisonArticle?.imageUrl, data.comparisonArticle?.imageAlt);
            updateElement('comparison-article-text', data.comparisonArticle?.text, true);
            
            // Update Author Bio (can be static or dynamic from JSON)
            if (data.authorBio) {
                updateElement('author-bio', data.authorBio, true);
            }

            // Update LLM Story section
            updateElement('llm-story-content', data.llmStory?.content, true);
            
            // Update Joke section
            updateElement('joke-content', data.joke?.content, true);

            // Update Advertisements section
            if (data.advertisements && Array.isArray(data.advertisements)) {
                // Loop through up to 4 advertisements
                for (let i = 0; i < 4; i++) {
                    if (data.advertisements[i]) {
                        // Update ad text if data exists
                        updateElement(`ad-${i + 1}`, data.advertisements[i].text, true);
                        // Could also handle ad images if structure supports it:
                        // updateImage(`ad-${i+1}-image`, data.advertisements[i].imageUrl, data.advertisements[i].imageAlt);
                    } else {
                        // If no data for an ad, display a placeholder message
                        updateElement(`ad-${i + 1}`, 'Advertisement space available.', false);
                    }
                }
            }
        })
       .catch(error => {
            // Handle errors during the fetch operation or JSON parsing
            console.error('Error fetching or parsing daily content:', error);
            // Display a user-friendly error message on the page
            const mainContent = document.getElementById('main-content');
            if (mainContent) {
                mainContent.innerHTML = `<p class="error-message">Sorry, we couldn't load today's Craic. The AI might be on a tea break. Please try again later. (Error: ${error.message})</p>`;
            }
            // Provide fallback content for critical elements in case of an error
            //updateElement('newspaper-banner', 'CraicGPT.ie - Offline Edition', true, 'h1');
            updateElement('main-article-title', 'Content Unavailable', true, 'h2');
        });
});

// Function to update the content of an HTML element
// id: The ID of the HTML element to update
// content: The new content for the element
// isHtml: Boolean, true if content is HTML, false if plain text (defaults to false)
// wrapperTag: The HTML tag to use as a wrapper if content is missing (defaults to 'p')
function updateElement(id, content, isHtml = false, wrapperTag = 'p') {
    // Get the HTML element by its ID
    const element = document.getElementById(id);
    // Check if the element exists and content is provided
    if (element && content!== undefined && content!== null) {
        if (isHtml) {
            // If content is HTML, set the innerHTML property (ensure content is a string)
            element.innerHTML = String(content); 
        } else {
            // If content is plain text, set the textContent property (ensure content is a string)
            element.textContent = String(content);
        }
    } else if (element) {
        // Optional: If element exists but content is missing, clear or set default text
        // element.innerHTML = `<${wrapperTag}>Content for ${id} not available.</${wrapperTag}>`;
        // Log a warning if content for the element is not found or the element doesn't exist
        console.warn(`Content for element ID '${id}' not found in JSON or element does not exist.`);
    }
}

// Function to update the source and alt text of an image element
// id: The ID of the HTML image element
// imageUrl: The URL of the new image
// altText: The alternative text for the image
function updateImage(id, imageUrl, altText) {
    // Get the image element by its ID
    const imgElement = document.getElementById(id);
    // Check if the image element exists and an image URL is provided
    if (imgElement && imageUrl) {
        // Set the src attribute to the new image URL
        imgElement.src = imageUrl;
        // Set the alt attribute (use provided altText or a default value)
        imgElement.alt = altText || 'Dynamic image content';
    } else if (imgElement) {
        // Optional: If image URL is missing, hide the image or take other action
        // imgElement.style.display = 'none';
        // Log a warning if the image URL is not found or the element doesn't exist
        console.warn(`Image URL for element ID '${id}' not found in JSON or element does not exist.`);
    }
}