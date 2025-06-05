// /static_assets/main.js
// Author: graham land
// Date: 2023-10-27
// Purpose: Handles dynamic content loading and updates for the CraicGPT.ie website.

// Global variables to store fetched data and current selections
let currentPaperData = null;
let selectedLLM = ''; // Will be updated by radio button interactions
let selectedImageGen = ''; // Will be updated by radio button interactions

// Helper function to get the currently selected LLM
function getSelectedLLM() {
    const checkedRadio = document.querySelector('input[name="llm_choice"]:checked');
    // Fallback to defaultLLM from data, or 'chatgpt' if nothing is available
    return checkedRadio ? checkedRadio.value : (currentPaperData?.metadata?.defaultLLM || 'chatgpt');
}

// Helper function to get the currently selected Image Generator
function getSelectedImageGen() {
    const checkedRadio = document.querySelector('input[name="imagegen_choice"]:checked');
    // Fallback to defaultImageGen from data, or 'imagen' if nothing is available
    return checkedRadio ? checkedRadio.value : (currentPaperData?.metadata?.defaultImageGen || 'imagen');
}

// Function to update the content of an HTML element
// id: The ID of the HTML element to update
// content: The new content for the element
// isHtml: Boolean, true if content is HTML, false if plain text (defaults to false)
// wrapperTag: The HTML tag to use as a wrapper if content is missing (defaults to 'p') - currently unused but kept for potential future use.
function updateElement(id, content, isHtml = false, wrapperTag = 'p') {
    const element = document.getElementById(id);
    if (element) {
        if (content !== undefined && content !== null) {
            if (isHtml) {
                element.innerHTML = String(content);
            } else {
                element.textContent = String(content);
            }
        } else {
            // If content is undefined or null, clear the element or set a default.
            if (isHtml) {
                element.innerHTML = '';
            } else {
                element.textContent = '';
            }
            // console.warn(`Content for element ID '${id}' was undefined or null. Element cleared.`);
        }
    } else {
        // console.warn(`Element with ID '${id}' not found.`);
    }
}

// Function to update the source and alt text of an image element
// id: The ID of the HTML image element
// imageUrl: The URL of the new image
// altText: The alternative text for the image
function updateImage(id, imageUrl, altText) {
    const imgElement = document.getElementById(id);
    if (imgElement) {
        if (imageUrl) {
            imgElement.src = imageUrl;
            imgElement.alt = altText || 'Dynamic image content';
            imgElement.style.display = ''; // Ensure image is visible
        } else {
            // If no image URL, clear src, alt, and hide the image or set a placeholder
            imgElement.src = 'placeholder.jpg'; // Default placeholder
            imgElement.alt = 'Content unavailable';
            // console.warn(`Image URL for element ID '${id}' was undefined or null. Image reset to placeholder.`);
        }
    } else {
        // console.warn(`Image element with ID '${id}' not found.`);
    }
}

// Function to render content based on currentPaperData and selections
function renderContent() {
    if (!currentPaperData || !currentPaperData.contentSlots) {
        console.warn("No paper data or content slots available to render.");
        const mainContent = document.getElementById('main-content');
        if (mainContent) {
            mainContent.innerHTML = '<p class="error-message">Content is currently unavailable. Please select a date.</p>';
        }
        // Clear other specific elements that might hold old data
        const bannerTitleElement = document.querySelector('#newspaper-banner h1');
        if (bannerTitleElement) bannerTitleElement.textContent = 'CraicGPT.ie';
        updateElement('current-date', 'No date selected', false);
        // Clear article sections
        updateElement('main-article-title', '', true);
        updateElement('main-article-text', '', true);
        updateImage('main-article-image', null, '');
        updateElement('comparison-article-title', '', true);
        updateElement('comparison-article-text', '', true);
        updateImage('comparison-article-image', null, '');
        updateElement('llm-story-content', '', true);
        updateElement('joke-content', '', true);
        return;
    }

    selectedLLM = getSelectedLLM();
    selectedImageGen = getSelectedImageGen();
    console.log(`Rendering with LLM: ${selectedLLM}, ImageGen: ${selectedImageGen}`);

    const slots = currentPaperData.contentSlots;

    // Main Article
    const mainArticleLlmData = slots.mainArticle?.llmOutputs?.[selectedLLM];
    updateElement('main-article-title', mainArticleLlmData?.title, true);
    updateElement('main-article-text', mainArticleLlmData?.text, true);
    const mainArticleImageData = slots.mainArticle?.imageOutputs?.[selectedImageGen];
    updateImage('main-article-image', mainArticleImageData?.imageUrl, mainArticleImageData?.imageAlt);

    // Comparison Article
    const comparisonArticleLlmData = slots.comparisonArticle?.llmOutputs?.[selectedLLM];
    updateElement('comparison-article-title', comparisonArticleLlmData?.title, true);
    updateElement('comparison-article-text', comparisonArticleLlmData?.text, true);
    const comparisonArticleImageData = slots.comparisonArticle?.imageOutputs?.[selectedImageGen];
    updateImage('comparison-article-image', comparisonArticleImageData?.imageUrl, comparisonArticleImageData?.imageAlt);

    // LLM Story
    const llmStoryData = slots.llmStory?.llmOutputs?.[selectedLLM];
    updateElement('llm-story-content', llmStoryData?.content, true);

    // Joke
    const jokeData = slots.joke?.llmOutputs?.[selectedLLM];
    updateElement('joke-content', jokeData?.content, true);

    // Author Bio (assuming single version for now)
    if (slots.authorBio && typeof slots.authorBio.text !== 'undefined') {
         updateElement('author-bio', slots.authorBio.text, true);
    } else {
        updateElement('author-bio', "<p>Our esteemed editor, a sophisticated language model, works tirelessly (without coffee breaks!) to bring you the latest insights and ramblings from the digital ether. Likes: clean data, efficient algorithms. Dislikes: infinite loops, existential questions before the first byte of the day.</p>", true);
    }

    // Advertisements
    if (slots.advertisements && Array.isArray(slots.advertisements)) {
        for (let i = 0; i < 4; i++) {
            if (slots.advertisements[i] && typeof slots.advertisements[i].text !== 'undefined') {
                updateElement(`ad-${i + 1}`, slots.advertisements[i].text, true);
            } else {
                updateElement(`ad-${i + 1}`, 'Advertisement space available.', false);
            }
        }
    } else { // Fallback if ads structure is missing
        for (let i = 0; i < 4; i++) {
            updateElement(`ad-${i + 1}`, 'Advertisement space available.', false);
        }
    }

    // Update banner title from metadata
    const bannerTitleElement = document.querySelector('#newspaper-banner h1');
    if (bannerTitleElement) {
        bannerTitleElement.textContent = currentPaperData.metadata?.bannerTitle || 'CraicGPT.ie';
    }

    // Update displayed date from publicationDate
    const dateElement = document.getElementById('current-date');
    if (dateElement && currentPaperData.publicationDate) {
         const pubDate = new Date(currentPaperData.publicationDate + 'T00:00:00'); // Ensure correct parsing by setting time locally
         dateElement.textContent = pubDate.toLocaleDateString('en-IE', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        });
    } else if (dateElement) {
        dateElement.textContent = "Date not available";
    }
}

// Function to fetch content for a given date string (YYYY-MM-DD)
function fetchContentForDate(dateString) {
    console.log(`Fetching content for date: ${dateString}`);
    if (!dateString || !/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
        console.error("Invalid date string format provided to fetchContentForDate. Expected YYYY-MM-DD. Received:", dateString);
        const mainContent = document.getElementById('main-content');
        if (mainContent) {
            mainContent.innerHTML = '<p class="error-message">Invalid date format selected. Please use YYYY-MM-DD.</p>';
        }
        currentPaperData = null;
        renderContent(); // Attempt to render a cleared state
        return;
    }

    const [year, month, day] = dateString.split('-');
    const contentUrl = `/content/${year}/${month}/${day}/todays_paper.json`;
    // const contentUrl = 'todays_paper_example.json'; // For local testing

    fetch(contentUrl)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Network response was not ok: ${response.statusText} (Status: ${response.status}) for URL: ${contentUrl}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Fetched content:", data);
            currentPaperData = data;
            
            // Set radio buttons to default selections from metadata, if available
            if (currentPaperData.metadata?.defaultLLM) {
                const defaultLLMRadio = document.getElementById(`llm-${currentPaperData.metadata.defaultLLM}`);
                if (defaultLLMRadio) defaultLLMRadio.checked = true;
            }
            if (currentPaperData.metadata?.defaultLLM) {
                const llmRadio = document.querySelector(`input[name="llm_choice"][value="${currentPaperData.metadata.defaultLLM}"]`);
                if (llmRadio) llmRadio.checked = true;
                else console.warn(`Default LLM radio for value "${currentPaperData.metadata.defaultLLM}" not found.`);
            }
            if (currentPaperData.metadata?.defaultImageGen) {
                const imageGenRadio = document.querySelector(`input[name="imagegen_choice"][value="${currentPaperData.metadata.defaultImageGen}"]`);
                if (imageGenRadio) imageGenRadio.checked = true;
                else console.warn(`Default ImageGen radio for value "${currentPaperData.metadata.defaultImageGen}" not found.`);
            }

            const datePickerInstance = document.querySelector("#date-picker")._flatpickr;
            if (datePickerInstance && currentPaperData.publicationDate) {
                // Ensure not to trigger Flatpickr's onChange during this programmatic set
                datePickerInstance.setDate(currentPaperData.publicationDate, false);
            }
            renderContent(); // Render after setting defaults and date picker
        })
        .catch(error => {
            console.error('Error fetching or parsing daily content:', error);
            currentPaperData = null;
            renderContent();

            const mainContent = document.getElementById('main-content');
            if (mainContent) {
                mainContent.innerHTML = `<p class="error-message">Sorry, we couldn't load the Craic for ${dateString}. The AI might have been napping. Please try another date or check back later. (Error: ${error.message})</p>`;
            }
            const bannerTitleElement = document.querySelector('#newspaper-banner h1');
            if (bannerTitleElement) {
                 bannerTitleElement.textContent = 'CraicGPT.ie - Offline Edition';
            }
            const dateElement = document.getElementById('current-date');
            if (dateElement) {
                dateElement.textContent = `Failed to load content for ${dateString}`;
            }
        });
}

// Main function that runs when the window has finished loading
window.addEventListener('load', () => {
    // Initialize Flatpickr
    flatpickr("#date-picker", {
        dateFormat: "Y-m-d",
        defaultDate: "today", // This should ideally trigger onChange for initial load.
        onChange: function(selectedDates, dateStr, instance) {
            console.log("Date selected via Flatpickr:", dateStr);
            fetchContentForDate(dateStr); // Fetch and render content for the newly selected date
        }
    });

    // Robust initial load: Flatpickr's defaultDate: "today" should trigger its onChange.
    // If there's a concern it might not, or if a date other than "today" was default,
    // this explicit fetch ensures content loading.
    // However, modern Flatpickr usually handles defaultDate triggering onChange.
    // For this iteration, we'll rely on Flatpickr's onChange for the initial load triggered by defaultDate.
    // If issues arise, the explicit fetch method below can be reinstated:
    /*
    const initialDatePickerInstance = document.querySelector("#date-picker")._flatpickr;
    let initialDateToLoad = new Date().getFullYear() + '-' + String(new Date().getMonth() + 1).padStart(2, '0') + '-' + String(new Date().getDate()).padStart(2, '0');
    if (initialDatePickerInstance.selectedDates.length > 0) {
        initialDateToLoad = initialDatePickerInstance.formatDate(initialDatePickerInstance.selectedDates[0], "Y-m-d");
    }
    fetchContentForDate(initialDateToLoad);
    */

    // Update footer year with the current year
    const footerYearElement = document.getElementById('footer-year');
    if (footerYearElement) {
        footerYearElement.textContent = new Date().getFullYear();
    }

    // Add Event Listeners to Radio Buttons
    const llmRadioButtons = document.querySelectorAll('input[name="llm_choice"]');
    llmRadioButtons.forEach(radio => {
        radio.addEventListener('change', () => {
            console.log('LLM choice changed:', radio.value);
            if (currentPaperData) { // Only render if data is loaded
                renderContent();
            } else {
                console.warn("LLM choice changed, but no currentPaperData to render.");
                // Attempt to load data for the currently selected date in the picker
                const datePickerInstance = document.querySelector("#date-picker")._flatpickr;
                const currentDateInPicker = datePickerInstance.selectedDates[0];
                const dateStrToFetch = currentDateInPicker ?
                                       datePickerInstance.formatDate(currentDateInPicker, "Y-m-d") :
                                       new Date().getFullYear() + '-' + String(new Date().getMonth() + 1).padStart(2, '0') + '-' + String(new Date().getDate()).padStart(2, '0');
                fetchContentForDate(dateStrToFetch);
            }
        });
    });

    const imageGenRadioButtons = document.querySelectorAll('input[name="imagegen_choice"]');
    imageGenRadioButtons.forEach(radio => {
        radio.addEventListener('change', () => {
            console.log('ImageGen choice changed:', radio.value);
            if (currentPaperData) { // Only render if data is loaded
                renderContent();
            } else {
                console.warn("ImageGen choice changed, but no currentPaperData to render.");
                const datePickerInstance = document.querySelector("#date-picker")._flatpickr;
                const currentDateInPicker = datePickerInstance.selectedDates[0];
                const dateStrToFetch = currentDateInPicker ?
                                       datePickerInstance.formatDate(currentDateInPicker, "Y-m-d") :
                                       new Date().getFullYear() + '-' + String(new Date().getMonth() + 1).padStart(2, '0') + '-' + String(new Date().getDate()).padStart(2, '0');
                fetchContentForDate(dateStrToFetch);
            }
        });
    });
});