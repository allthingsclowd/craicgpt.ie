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

            // Update js-datepicker instance if it exists and a publicationDate is available
            const datePickerElement = document.getElementById('date-picker');
            if (datePickerElement && datePickerElement.datepicker && currentPaperData.publicationDate) {
                // Parse publicationDate from JSON (YYYY-MM-DD string) into a Date object
                const parts = currentPaperData.publicationDate.split('-');
                const year = parseInt(parts[0], 10);
                const month = parseInt(parts[1], 10) - 1; // Month is 0-indexed in JS Date
                const day = parseInt(parts[2], 10);
                const newDateToSet = new Date(year, month, day);
                // Programmatically set the date of the js-datepicker.
                // The third argument 'true' usually means to prevent onSelect from firing.
                // Behavior might vary; check js-datepicker docs if re-fetch loop occurs.
                datePickerElement.datepicker.setDate(newDateToSet, true);
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
    const datePickerInput = document.getElementById('date-picker');
    if (!datePickerInput) {
        console.error("#date-picker element not found!");
        // Potentially stop further JS execution or UI updates dependent on the picker
        // For now, other parts like radio buttons might still work if data is fetched by other means.
    } else {
        const picker = datepicker(datePickerInput, {
            formatter: (input, date, instance) => {
                // Format the date displayed in the input field
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                input.value = `${year}-${month}-${day}`; // Set the input value
            },
            onSelect: (instance, date) => {
                // This function is called when a date is picked.
                if (date) {
                    const year = date.getFullYear();
                    const month = String(date.getMonth() + 1).padStart(2, '0');
                    const day = String(date.getDate()).padStart(2, '0');
                    const dateStr = `${year}-${month}-${day}`;

                    console.log("Date selected via js-datepicker:", dateStr);
                    fetchContentForDate(dateStr);
                } else {
                    console.log("Date cleared or selection invalid via js-datepicker.");
                    currentPaperData = null;
                    renderContent();
                }
            },
            dateSelected: new Date() // Set default date to today
        });
        // Example: Storing the instance if needed globally, though it's better to manage scope.
        // window.craicDatePicker = picker;
    }

    // Initial content load for today's date.
    // js-datepicker with `dateSelected: new Date()` should display today's date.
    // The onSelect handler will be triggered by the initial selection or a manual selection.
    // However, to ensure content loads on the very first page load with the default date,
    // an explicit fetch is still a good idea, especially if onSelect isn't triggered by dateSelected.
    const today = new Date();
    const initialDateToLoad = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
    fetchContentForDate(initialDateToLoad);
    // If datePickerInput exists, its value will be formatted by the picker's formatter
    // or by the setDate call in fetchContentForDate's success logic.

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
                // Attempt to load data for the currently selected date in the text input
                const datePickerValue = document.getElementById('date-picker').value;
                const dateStrToFetch = (/^\d{4}-\d{2}-\d{2}$/.test(datePickerValue)) ?
                                       datePickerValue :
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
                const datePickerValue = document.getElementById('date-picker').value;
                const dateStrToFetch = (/^\d{4}-\d{2}-\d{2}$/.test(datePickerValue)) ?
                                       datePickerValue :
                                       new Date().getFullYear() + '-' + String(new Date().getMonth() + 1).padStart(2, '0') + '-' + String(new Date().getDate()).padStart(2, '0');
                fetchContentForDate(dateStrToFetch);
            }
        });
    });
});