// /static_assets/main.js
// Author: graham land
// Date: 2023-10-27
// Purpose: Handles dynamic content loading and updates for the CraicGPT.ie website.

// IMPORTANT: Configure this URL to point to the root of your S3 bucket or CloudFront distribution
// where the 'static_assets/content/website/' directory is located.
// Example: "https://your-bucket-name.s3.your-region.amazonaws.com"
//      OR "https://d123abcdef8gh.cloudfront.net"
// Ensure it does NOT end with a trailing slash.
const S3_BUCKET_BASE_URL = "https://YOUR_S3_BUCKET_OR_CLOUDFRONT_URL_HERE"; // FIXME: USER CONFIGURATION REQUIRED

// Global variables to store fetched data and current selections
let currentPaperData = null;
let selectedLLM      = 'anthropic.claude-3-sonnet-20240229-v1';
let selectedImageGen = 'amazon.titan-image-generator-v1';
// ─── track which JSON file we just fetched ───────────────────────────────
let currentContentUrl = null;      // e.g. ".../2025/06/22/paper_content.json" // Updated comment

const MAX_FALLBACK_ATTEMPTS = 7;

const newspaperPlaceholders = {
    bannerTitle: "The Artificially Intelligent Times (Offline View)",
    currentDateText: "Date Not Available - Showing Default Layout",
    mainArticle: {
        title: "City Celebrates Annual Tech Chronicle Gala",
        text: "The grand ballroom buzzed with excitement as tech enthusiasts, innovators, and investors gathered for the annual Tech Chronicle Gala...",
        imageUrl: "static_assets/images/placeholder_article_main.png",
        imageAlt: "Illustration of a bustling city event with futuristic elements"
    },
    comparisonArticle: {
        title: "The AI Revolution: Perspectives from Two Leading Models",
        text: "In an unprecedented dialogue, two leading AI models, InnovateAI and LogicPrime, shared their 'thoughts' on the future of artificial intelligence...",
        imageUrl: "static_assets/images/placeholder_article_comparison.png",
        imageAlt: "Abstract representation of two AI entities in discussion"
    },
    llmStory: {
        content: "<p>Once upon a time, in a world woven from threads of pure data... Sparky became the official storyteller...</p>",
        imageUrl: "static_assets/images/placeholder_article_llm.png", // Added placeholder
        imageAlt: "Abstract representation of an LLM's story" // Added placeholder
    },
    joke: {
        content: "<p>Why did the programmer quit his job?...Because he didn't get arrays!</p>",
        imageUrl: "static_assets/images/placeholder_article_joke.png", // Added placeholder
        imageAlt: "Visual representation of a joke" // Added placeholder
    },
    authorBio: {
        text: "<p>Our esteemed editor, a sophisticated language model... Likes: clean data... Dislikes: infinite loops...</p>"
    },
    advertisements: [
        { imageUrl: "static_assets/images/placeholder_ad_1.png", imageAlt: "Placeholder Advertisement 1" },
        { imageUrl: "static_assets/images/placeholder_ad_2.png", imageAlt: "Placeholder Advertisement 2" },
        { imageUrl: "static_assets/images/placeholder_ad_3.png", imageAlt: "Placeholder Advertisement 3" },
        { imageUrl: "static_assets/images/placeholder_ad_4.png", imageAlt: "Placeholder Advertisement 4" }
    ]
};

// Helper function to get the currently selected LLM
function getSelectedLLM() {
    const checkedRadio = document.querySelector('input[name="llm_choice"]:checked');
    return checkedRadio ? checkedRadio.value : (currentPaperData?.metadata?.defaultLLM || selectedLLM);
}

// Helper function to get the currently selected Image Generator
function getSelectedImageGen() {
    const checkedRadio = document.querySelector('input[name="imagegen_choice"]:checked');
    return checkedRadio ? checkedRadio.value : (currentPaperData?.metadata?.defaultImageGen || selectedImageGen);
}

// Function to update the content of an HTML element
function updateElement(id, content, isHtml = false) {
    const element = document.getElementById(id);
    if (element) {
        if (content !== undefined && content !== null) {
            if (isHtml) {
                element.innerHTML = String(content);
            } else {
                element.textContent = String(content);
            }
        } else {
            if (isHtml) {
                element.innerHTML = '';
            } else {
                element.textContent = '';
            }
        }
    }
}

// Function to update the source and alt text of an image element
// Now handles image data object which might include {url, alt, blocked}
function updateImage(id, imageData, defaultAltText, placeholderUrl = 'static_assets/images/placeholder.jpg', placeholderAlt = 'Content unavailable') {
    const imgElement = document.getElementById(id);
    if (imgElement) {
        if (imageData && (imageData.url || imageData.blocked)) {
            if (imageData.blocked) {
                imgElement.src = 'static_assets/images/blocked_image.png'; // Specific placeholder for blocked content
                imgElement.alt = imageData.alt || "Image generation blocked due to safety policy";
                imgElement.style.display = '';
            } else {
                imgElement.src = imageData.url;
                imgElement.alt = imageData.alt || defaultAltText || 'Dynamic image content';
                imgElement.style.display = '';
            }
        } else if (typeof imageData === 'string' && imageData) { // Backward compatibility for direct URL string
            imgElement.src = imageData;
            imgElement.alt = defaultAltText || 'Dynamic image content';
            imgElement.style.display = '';
        }
        else { // Fallback to placeholder
            imgElement.src = placeholderUrl;
            imgElement.alt = placeholderAlt;
            imgElement.style.display = ''; // Ensure placeholder is visible
        }
    }
}


// Function to render content based on currentPaperData and selections
function renderContent() {
    const basePath = currentContentUrl
        ? currentContentUrl.replace(/paper_content\.json$/i, '') // Updated filename
        : 'static_assets/content/website/fallback/'; // Fallback base path for placeholders if currentContentUrl is null

    // Processes image data which might be a string URL or an object {url, alt, blocked}
    // Prepends basePath if the URL is relative.
    function processImageData(imageData) {
        if (!imageData) return null;

        let url = '';
        let alt = 'Illustration'; // Default alt
        let blocked = false;

        if (typeof imageData === 'string') {
            url = imageData;
        } else if (typeof imageData === 'object') {
            url = imageData.url;
            alt = imageData.alt || alt;
            blocked = imageData.blocked || false;
        }

        if (blocked) {
            return { url: 'static_assets/images/blocked_image.png', alt: alt, blocked: true };
        }
        if (!url) return { url: null, alt: alt };


        if (/^(https?:)?\/\//.test(url) || url.startsWith('/') || url.startsWith('static_assets/')) {
            return { url: url, alt: alt };
        }
        return { url: basePath + url, alt: alt };
    }


    if (!currentPaperData || !currentPaperData.contentSlots) {
        console.warn("No paper data or content slots available. Rendering placeholders.");
        updateElement('main-article-title', newspaperPlaceholders.mainArticle.title, true);
        updateElement('main-article-text', newspaperPlaceholders.mainArticle.text, true);
        updateImage('main-article-image', processImageData(newspaperPlaceholders.mainArticle.imageUrl), newspaperPlaceholders.mainArticle.imageAlt);

        updateElement('comparison-article-title', newspaperPlaceholders.comparisonArticle.title, true);
        updateElement('comparison-article-text', newspaperPlaceholders.comparisonArticle.text, true);
        updateImage('comparison-article-image', processImageData(newspaperPlaceholders.comparisonArticle.imageUrl), newspaperPlaceholders.comparisonArticle.imageAlt);

        updateElement('llm-story-content', newspaperPlaceholders.llmStory.content, true);
        updateImage('llm-story-image', processImageData(newspaperPlaceholders.llmStory.imageUrl), newspaperPlaceholders.llmStory.imageAlt, 'static_assets/images/placeholder_article_llm.png', newspaperPlaceholders.llmStory.imageAlt);

        updateElement('joke-content', newspaperPlaceholders.joke.content, true);
        updateImage('joke-image', processImageData(newspaperPlaceholders.joke.imageUrl), newspaperPlaceholders.joke.imageAlt, 'static_assets/images/placeholder_article_joke.png', newspaperPlaceholders.joke.imageAlt);

        updateElement('author-bio', newspaperPlaceholders.authorBio.text, true);

        for (let i = 0; i < newspaperPlaceholders.advertisements.length; i++) {
            const adPlaceholder = newspaperPlaceholders.advertisements[i];
            const adElementContainer = document.getElementById(`ad-${i + 1}`);
            if (adElementContainer) {
                const imgElement = adElementContainer.querySelector('img');
                if (imgElement) {
                    // Placeholder URLs are already fully qualified or relative to static_assets root
                    imgElement.src = adPlaceholder.imageUrl;
                    imgElement.alt = adPlaceholder.imageAlt;
                    imgElement.style.display = '';
                }
            }
        }

        const bannerTitleElement = document.querySelector('#newspaper-banner h1');
        if (bannerTitleElement) {
            bannerTitleElement.textContent = newspaperPlaceholders.bannerTitle;
        }
        updateElement('current-date', newspaperPlaceholders.currentDateText, false);
        return;
    }

    selectedLLM = getSelectedLLM();
    selectedImageGen = getSelectedImageGen();
    // console.log(`Rendering with LLM: ${selectedLLM}, ImageGen: ${selectedImageGen}`);

    const slots = currentPaperData.contentSlots;

    // Helper to get specific image data (e.g., img_01, img_07) for a slot
    const getImageDataForSlotKey = (slotName, imageKey) => {
        const slotData = slots[slotName];
        // Image data is nested: slot -> imageOutputs -> selectedImageGenModel -> imageKey
        return slotData?.imageOutputs?.[selectedImageGen]?.[imageKey];
    };

    // Main Article (mapped to img_01)
    const mainArticleLlmData = slots.mainArticle?.llmOutputs?.[selectedLLM];
    updateElement('main-article-title', mainArticleLlmData?.title, true);
    updateElement('main-article-text', mainArticleLlmData?.text, true);
    const mainArticleImageProcessed = processImageData(getImageDataForSlotKey('mainArticle', 'img_01'));
    updateImage('main-article-image', mainArticleImageProcessed, 'Lead story illustration');


    // Comparison Article (mapped to img_02)
    const comparisonArticleLlmData = slots.comparisonArticle?.llmOutputs?.[selectedLLM];
    updateElement('comparison-article-title', comparisonArticleLlmData?.title, true);
    updateElement('comparison-article-text', comparisonArticleLlmData?.text, true);
    const comparisonArticleImageProcessed = processImageData(getImageDataForSlotKey('comparisonArticle', 'img_02'));
    updateImage('comparison-article-image', comparisonArticleImageProcessed, 'Comparison story illustration');

    // LLM Story (mapped to img_07)
    const llmStoryLlmData = slots.llmStory?.llmOutputs?.[selectedLLM];
    updateElement('llm-story-content', llmStoryLlmData?.content, true);
    const llmStoryImageProcessed = processImageData(getImageDataForSlotKey('llmStory', 'img_07'));
    updateImage('llm-story-image', llmStoryImageProcessed, 'LLM generated story illustration', newspaperPlaceholders.llmStory.imageUrl, newspaperPlaceholders.llmStory.imageAlt);


    // Joke (mapped to img_08)
    const jokeLlmData = slots.joke?.llmOutputs?.[selectedLLM];
    updateElement('joke-content', jokeLlmData?.content, true);
    const jokeImageProcessed = processImageData(getImageDataForSlotKey('joke', 'img_08'));
    updateImage('joke-image', jokeImageProcessed, 'Joke illustration', newspaperPlaceholders.joke.imageUrl, newspaperPlaceholders.joke.imageAlt);


    // Author Bio
    if (slots.authorBio && typeof slots.authorBio.text !== 'undefined') {
         updateElement('author-bio', slots.authorBio.text, true);
    } else {
        updateElement('author-bio', newspaperPlaceholders.authorBio.text, true);
    }

    // Advertisements (mapped to img_03, img_04, img_05, img_06)
    const adImageKeys = ['img_03', 'img_04', 'img_05', 'img_06'];
    for (let i = 0; i < adImageKeys.length; i++) {
        const adKey = adImageKeys[i];
        const adElementId = `ad-${i + 1}`;
        const adImgElement = document.getElementById(adElementId)?.querySelector('img');

        if (adImgElement) {
            const adImageData = getImageDataForSlotKey('advertisements', adKey);
            const processedAdImage = processImageData(adImageData);

            // Use specific placeholder for this ad if processedAdImage is null/invalid
            const placeholderAd = newspaperPlaceholders.advertisements[i] || { imageUrl: 'static_assets/images/placeholder_ad.png', imageAlt: 'Advertisement space unavailable' };
            updateImage(adImgElement.id, processedAdImage, `Advertisement ${i + 1}`, placeholderAd.imageUrl, placeholderAd.imageAlt);
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
         const pubDate = new Date(currentPaperData.publicationDate + 'T00:00:00');
         dateElement.textContent = pubDate.toLocaleDateString('en-IE', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        });
    } else if (dateElement) {
        dateElement.textContent = "Date not available";
    }
}

// Function to fetch content for a given date string (YYYY-MM-DD)
function fetchContentForDate(dateString, attemptNumber = 0, originalDateStringForAlert = null) {
    // console.log(`Fetching content for date: ${dateString}, Attempt: ${attemptNumber + 1}`);
    if (!dateString || !/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
        console.error("Invalid date string format provided. Expected YYYY-MM-DD. Received:", dateString);
        currentPaperData = null;
        renderContent(); // Render placeholders
        return;
    }

    if (attemptNumber === 0) {
        originalDateStringForAlert = dateString;
    }

    const [yearStr, monthStr, dayStr] = dateString.split('-');
    // Construct the full URL using the S3_BUCKET_BASE_URL
    const relativePath = `static_assets/content/website/${yearStr}/${monthStr}/${dayStr}/paper_content.json`;
    const fullS3Url = `${S3_BUCKET_BASE_URL}/${relativePath}`;

    currentContentUrl = fullS3Url; // Store the full S3 URL

    console.log("Attempting to fetch paper_content.json from:", fullS3Url); // Added for debugging
    fetch(fullS3Url) // Fetch from the full S3 URL
        .then(response => {
            if (!response.ok) {
                // Use fullS3Url in error message for clarity, as contentUrl is not defined in this scope anymore
                throw new Error(`Network response was not ok: ${response.statusText} (Status: ${response.status}) for URL: ${fullS3Url}`);
            }
            return response.json();
        })
        .then(data => {
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
                const loadedDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));

                const pickerInstance = datePickerElement.datepicker;
                const originalOnSelect = pickerInstance.options.onSelect;
                pickerInstance.options.onSelect = () => {}; // Temporarily disable
                pickerInstance.setDate(loadedDate, true);  // Set date, don't trigger onSelect
                pickerInstance.options.onSelect = originalOnSelect; // Restore
            }
            renderContent();
        })
        .catch(error => {
            console.warn(`Failed to fetch content for ${dateString} (Attempt ${attemptNumber + 1}/${MAX_FALLBACK_ATTEMPTS + 1}): ${error.message}`);
            if (attemptNumber < MAX_FALLBACK_ATTEMPTS) {
                if (attemptNumber === 0) {
                     alert(`Content for ${originalDateStringForAlert} is not available. Attempting to find the latest available content...`);
                }
                const currentDateObj = new Date(parseInt(yearStr), parseInt(monthStr) - 1, parseInt(dayStr));
                currentDateObj.setDate(currentDateObj.getDate() - 1);
                const prevDateString = `${currentDateObj.getFullYear()}-${String(currentDateObj.getMonth() + 1).padStart(2, '0')}-${String(currentDateObj.getDate()).padStart(2, '0')}`;
                fetchContentForDate(prevDateString, attemptNumber + 1, originalDateStringForAlert);
            } else {
                console.error(`All fallback attempts failed for ${originalDateStringForAlert}.`);
                currentPaperData = null;
                renderContent(); // Show placeholders

                const datePickerElement = document.getElementById('date-picker');
                if (datePickerElement && datePickerElement.datepicker && originalDateStringForAlert) {
                    const parts = originalDateStringForAlert.split('-');
                    const originalDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                    const pickerInstance = datePickerElement.datepicker;
                    const originalOnSelect = pickerInstance.options.onSelect;
                    pickerInstance.options.onSelect = () => {};
                    pickerInstance.setDate(originalDate, true);
                    pickerInstance.options.onSelect = originalOnSelect;
                }
                 if (attemptNumber === MAX_FALLBACK_ATTEMPTS) {
                    alert(`Content for ${originalDateStringForAlert} and nearby dates could not be loaded. Displaying default layout.`);
                }
            }
        });
}

window.addEventListener('load', () => {
    const datePickerInput = document.getElementById('date-picker');
    if (datePickerInput) {
        datepicker(datePickerInput, {
            formatter: (input, date) => {
                input.value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
            },
            onSelect: (instance, date) => {
                if (date) {
                    const dateStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
                    fetchContentForDate(dateStr);
                }
            },
            dateSelected: new Date()
        });
    } else {
        console.error("#date-picker element not found!");
    }

    const today = new Date();
    const initialDateToLoad = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    fetchContentForDate(initialDateToLoad);

    const footerYearElement = document.getElementById('footer-year');
    if (footerYearElement) {
        footerYearElement.textContent = new Date().getFullYear();
    }

    document.querySelectorAll('input[name="llm_choice"], input[name="imagegen_choice"]').forEach(radio => {
        radio.addEventListener('change', () => {
            if (currentPaperData) {
                renderContent();
            } else {
                const datePickerValue = document.getElementById('date-picker').value;
                fetchContentForDate(datePickerValue || initialDateToLoad);
            }
        });
    });
});