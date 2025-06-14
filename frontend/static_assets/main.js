// /static_assets/main.js
// Author: graham land
// Date: 2023-10-27
// Purpose: Handles dynamic content loading and updates for the CraicGPT.ie website.

// Global variables to store fetched data and current selections
let currentPaperData = null;
let selectedLLM = ''; // Will be updated by radio button interactions
let selectedImageGen = ''; // Will be updated by radio button interactions
const MAX_FALLBACK_ATTEMPTS = 7;

const newspaperPlaceholders = {
    mainArticle: {
        title: "City Celebrates Annual Tech Chronicle Gala",
        text: "The grand ballroom buzzed with excitement as tech enthusiasts, innovators, and investors gathered for the annual Tech Chronicle Gala. The event, known for showcasing cutting-edge technology and fostering collaboration, did not disappoint. Highlights included a keynote from visionary Dr. Aris Thorne and the unveiling of several groundbreaking startups. Attendees enjoyed an evening of networking, demonstrations, and discussions about the future of technology.",
        imageUrl: "static_assets/images/placeholder_article_main.png",
        imageAlt: "Illustration of a bustling city event with futuristic elements"
    },
    comparisonArticle: {
        title: "The AI Revolution: Perspectives from Two Leading Models",
        text: "In an unprecedented dialogue, two leading AI models, InnovateAI and LogicPrime, shared their 'thoughts' on the future of artificial intelligence. InnovateAI emphasized the potential for creative collaboration between humans and AI, while LogicPrime focused on the analytical power AI brings to complex problem-solving. Both agreed that ethical considerations and responsible development are paramount as AI technology continues to evolve.",
        imageUrl: "static_assets/images/placeholder_article_comparison.png",
        imageAlt: "Abstract representation of two AI entities in discussion"
    },
    llmStory: {
        content: "<p>Once upon a time, in a world woven from threads of pure data, lived a little algorithm named Sparky. Sparky wasn't like the other, more serious algorithms who crunched numbers for Big Corp Inc. Sparky loved to tell stories. One day, Sparky wove a tale so captivating it made the data servers hum with delight, a story about a brave little byte who dared to dream of the Cloud. And so, Sparky became the official storyteller of the digital kingdom, reminding everyone that even in a world of logic, there's always room for a little imagination.</p>"
    },
    joke: {
        content: "<p>Why did the programmer quit his job?</p><p>Because he didn't get arrays!</p>"
    },
    authorBio: { // This can be used to ensure consistency if the existing one is modified
        text: "<p>Our esteemed editor, a sophisticated language model, works tirelessly (without coffee breaks!) to bring you the latest insights and ramblings from the digital ether. Likes: clean data, efficient algorithms. Dislikes: infinite loops, existential questions before the first byte of the day.</p>"
    },
    advertisements: [
        { imageUrl: "static_assets/images/placeholder_ad_1.png", imageAlt: "Placeholder Advertisement: 'Innovate Tomorrow with Nebula Cloud Solutions'" },
        { imageUrl: "static_assets/images/placeholder_ad_2.png", imageAlt: "Placeholder Advertisement: 'Quantum Leap Coffee - Brewed for Peak Performance'" },
        { imageUrl: "static_assets/images/placeholder_ad_3.png", imageAlt: "Placeholder Advertisement: 'SecureSphere VPN - Your Digital Fortress'" },
        { imageUrl: "static_assets/images/placeholder_ad_4.png", imageAlt: "Placeholder Advertisement: 'CodeCleanse IDE - Write Flawless Code, Faster'" }
    ]
};

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
        console.warn("No paper data or content slots available. Rendering placeholders.");
        // Populate with placeholders
        updateElement('main-article-title', newspaperPlaceholders.mainArticle.title, true);
        updateElement('main-article-text', newspaperPlaceholders.mainArticle.text, true);
        updateImage('main-article-image', newspaperPlaceholders.mainArticle.imageUrl, newspaperPlaceholders.mainArticle.imageAlt);

        updateElement('comparison-article-title', newspaperPlaceholders.comparisonArticle.title, true);
        updateElement('comparison-article-text', newspaperPlaceholders.comparisonArticle.text, true);
        updateImage('comparison-article-image', newspaperPlaceholders.comparisonArticle.imageUrl, newspaperPlaceholders.comparisonArticle.imageAlt);

        updateElement('llm-story-content', newspaperPlaceholders.llmStory.content, true);
        updateElement('joke-content', newspaperPlaceholders.joke.content, true);
        updateElement('author-bio', newspaperPlaceholders.authorBio.text, true);

        for (let i = 0; i < newspaperPlaceholders.advertisements.length; i++) {
            const adPlaceholder = newspaperPlaceholders.advertisements[i];
            const adElementContainer = document.getElementById(`ad-${i + 1}`);
            if (adElementContainer) {
                const imgElement = adElementContainer.querySelector('img');
                if (imgElement) {
                    imgElement.src = adPlaceholder.imageUrl;
                    imgElement.alt = adPlaceholder.imageAlt;
                    imgElement.style.display = ''; // Ensure visible
                }
            }
        }

        // Clear other specific elements that might hold old data or set to default
        const bannerTitleElement = document.querySelector('#newspaper-banner h1');
        if (bannerTitleElement) bannerTitleElement.textContent = 'CraicGPT.ie'; // Default banner title
        updateElement('current-date', 'No date selected', false); // Default date message
        // The line below is removed as per instructions, placeholders are shown instead.
        // mainContent.innerHTML = '<p class="error-message">Content is currently unavailable. Please select a date.</p>';
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
    const adImageGenOutput = slots.advertisements?.imageOutputs?.[selectedImageGen];
    if (adImageGenOutput && Array.isArray(adImageGenOutput)) {
        for (let i = 0; i < 4; i++) {
            const adData = adImageGenOutput[i];
            const adElementContainer = document.getElementById(`ad-${i + 1}`); // Gets the div container
            if (adElementContainer) {
                const imgElement = adElementContainer.querySelector('img'); // Gets the <img> tag within the div
                if (imgElement) {
                    if (adData && adData.imageUrl) {
                        imgElement.src = adData.imageUrl;
                        imgElement.alt = adData.imageAlt || 'Advertisement';
                        imgElement.style.display = ''; // Ensure image is visible if previously hidden
                    } else {
                        // Fallback if specific adData (e.g., for ad_2) is missing but array exists
                        imgElement.src = 'static_assets/images/placeholder_ad.png'; // Default placeholder
                        imgElement.alt = 'Advertisement space unavailable';
                    }
                } else {
                    // This case should ideally not happen if HTML structure is consistent
                    // console.warn(`Image element within ad container ad-${i + 1} not found.`);
                }
            }
        }
    } else { // Fallback if 'advertisements.imageOutputs[selectedImageGen]' path is broken or missing
        for (let i = 0; i < 4; i++) {
            const adElementContainer = document.getElementById(`ad-${i + 1}`);
            if (adElementContainer) {
                const imgElement = adElementContainer.querySelector('img');
                if (imgElement) {
                    imgElement.src = 'static_assets/images/placeholder_ad.png'; // Default placeholder
                    imgElement.alt = 'Advertisements not available for selected generator';
                }
            }
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
function fetchContentForDate(dateString, attemptNumber = 0, originalDateStringForAlert = null) {
    console.log(`Fetching content for date: ${dateString}, Attempt: ${attemptNumber + 1}`);
    if (!dateString || !/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
        console.error("Invalid date string format provided to fetchContentForDate. Expected YYYY-MM-DD. Received:", dateString);
        const mainContent = document.getElementById('main-content');
        if (mainContent) {
            mainContent.innerHTML = '<p class="error-message">Invalid date format selected. Please use YYYY-MM-DD.</p>';
        }
        currentPaperData = null;
        renderContent();
        return;
    }

    if (attemptNumber === 0) {
        originalDateStringForAlert = dateString;
    }

    const [yearStr, monthStr, dayStr] = dateString.split('-');
    const year = parseInt(yearStr, 10);
    const jsMonth = parseInt(monthStr, 10) - 1;
    const day = parseInt(dayStr, 10);

    // const contentUrl = `/content/${yearStr}/${monthStr}/${dayStr}/todays_paper.json`;
    const contentUrl = `static_assets/sample_data/${yearStr}/${monthStr}/${dayStr}/todays_paper.json`;

    fetch(contentUrl)
        .then(response => {
            if (!response.ok) {
                const status = response.status;
                throw new Error(`Network response was not ok: ${response.statusText} (Status: ${status}) for URL: ${contentUrl}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Fetched content successfully for:", data.publicationDate);
            currentPaperData = data;

            if (attemptNumber > 0 && originalDateStringForAlert !== currentPaperData.publicationDate) {
                alert(`Content for ${originalDateStringForAlert} was not found. Showing available content for ${currentPaperData.publicationDate}.`);
            }
            
            if (currentPaperData.metadata?.defaultLLM) {
                const defaultLLMRadio = document.querySelector(`input[name="llm_choice"][value="${currentPaperData.metadata.defaultLLM}"]`);
                if (defaultLLMRadio) defaultLLMRadio.checked = true;
            }
            if (currentPaperData.metadata?.defaultImageGen) {
                const defaultImageGenRadio = document.querySelector(`input[name="imagegen_choice"][value="${currentPaperData.metadata.defaultImageGen}"]`);
                if (defaultImageGenRadio) defaultImageGenRadio.checked = true;
            }

            const datePickerElement = document.getElementById('date-picker');
            if (datePickerElement && datePickerElement.datepicker && currentPaperData.publicationDate) {
                const parts = currentPaperData.publicationDate.split('-');
                const loadedYear = parseInt(parts[0], 10);
                const loadedMonth = parseInt(parts[1], 10) - 1;
                const loadedDay = parseInt(parts[2], 10);
                const newDateToSet = new Date(loadedYear, loadedMonth, loadedDay);

                const pickerInstance = datePickerElement.datepicker;
                const originalOnSelect = pickerInstance.options.onSelect;
                pickerInstance.options.onSelect = () => {};
                pickerInstance.setDate(newDateToSet, true);
                pickerInstance.options.onSelect = originalOnSelect;
            }
            renderContent();
        })
        .catch(error => {
            console.warn(`Failed to fetch content for ${dateString} (Attempt ${attemptNumber + 1}/${MAX_FALLBACK_ATTEMPTS + 1}): ${error.message}`);

            if (attemptNumber < MAX_FALLBACK_ATTEMPTS) {
                if (attemptNumber === 0) {
                     alert(`Content for ${originalDateStringForAlert} is not available. Attempting to find the latest available content...`);
                }

                const currentDateObj = new Date(year, jsMonth, day);
                currentDateObj.setDate(currentDateObj.getDate() - 1);

                const prevYear = currentDateObj.getFullYear();
                const prevMonthStr = String(currentDateObj.getMonth() + 1).padStart(2, '0');
                const prevDayStr = String(currentDateObj.getDate()).padStart(2, '0');
                const previousDateString = `${prevYear}-${prevMonthStr}-${prevDayStr}`;

                fetchContentForDate(previousDateString, attemptNumber + 1, originalDateStringForAlert);
            } else {
                console.error(`All fallback attempts failed. No content found for ${originalDateStringForAlert} or nearby dates.`);
                currentPaperData = null;
                // Call renderContent to display placeholders.
                // renderContent() will handle updating the main content area with placeholders
                // and setting a generic message for the date display like "No date selected" or "Date not available".
                renderContent();

                // The following lines are commented out to allow renderContent() to manage the display of placeholders.
                // const mainContent = document.getElementById('main-content');
                // if (mainContent) {
                //     mainContent.innerHTML = `<p class="error-message">Sorry, content for ${originalDateStringForAlert} and the previous ${MAX_FALLBACK_ATTEMPTS} days is unavailable. Please try a different date range.</p>`;
                // }

                // The specific error message for 'current-date' is also removed.
                // renderContent() will set a generic one like "No date selected" or "Date not available".
                // const dateElement = document.getElementById('current-date');
                // if (dateElement) {
                //     dateElement.textContent = `Failed to load content for ${originalDateStringForAlert}`;
                // }

                const datePickerElement = document.getElementById('date-picker');
                if (datePickerElement && datePickerElement.datepicker && originalDateStringForAlert) {
                    const parts = originalDateStringForAlert.split('-');
                    const originalYear = parseInt(parts[0], 10);
                    const originalMonth = parseInt(parts[1], 10) - 1;
                    const originalDay = parseInt(parts[2], 10);
                    const originalDateToSet = new Date(originalYear, originalMonth, originalDay);

                    const pickerInstance = datePickerElement.datepicker;
                    const originalOnSelect = pickerInstance.options.onSelect;
                    pickerInstance.options.onSelect = () => {};
                    pickerInstance.setDate(originalDateToSet, true);
                    pickerInstance.options.onSelect = originalOnSelect;
                }
            }
        });
}
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