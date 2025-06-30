// /static_assets/main.js
// Author: graham land
// Date: 2023-10-27
// Purpose: Handles dynamic content loading and updates for the CraicGPT.ie website.

// IMPORTANT: Configure this URL to point to the root of your S3 bucket or CloudFront distribution
// where the 'static_assets/content/website/' directory is located.
// Example: "https://your-bucket-name.s3.your-region.amazonaws.com"
//      OR "https://d123abcdef8gh.cloudfront.net"
// Ensure it does NOT end with a trailing slash.
const S3_BUCKET_BASE_URL = "https://craicgpt.ie"; // Fixed: Use the actual domain instead of AWS console URL

// Global variables to store fetched data and current selections
let currentPaperData = null;
let selectedLLM      = 'anthropic.claude-3-sonnet-20240229-v1:0';
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
        imageUrl: "static_assets/images/placeholder_article.png",
        imageAlt: "Illustration of a bustling city event with futuristic elements"
    },
    comparisonArticle: {
        title: "The AI Revolution: Perspectives from Two Leading Models",
        text: "In an unprecedented dialogue, two leading AI models, InnovateAI and LogicPrime, shared their 'thoughts' on the future of artificial intelligence...",
        imageUrl: "static_assets/images/placeholder_article.png",
        imageAlt: "Abstract representation of two AI entities in discussion"
    },
    llmStory: {
        content: "<p>Once upon a time, in a world woven from threads of pure data... Sparky became the official storyteller...</p>",
        imageUrl: "static_assets/images/placeholder_article.png", // Fixed: Use existing placeholder
        imageAlt: "Abstract representation of an LLM's story" // Added placeholder
    },
    joke: {
        content: "<p>Why did the programmer quit his job?...Because he didn't get arrays!</p>",
        imageUrl: "static_assets/images/placeholder_article.png", // Fixed: Use existing placeholder
        imageAlt: "Visual representation of a joke" // Added placeholder
    },
    authorBio: {
        text: "<p>Our esteemed editor, a sophisticated language model... Likes: clean data... Dislikes: infinite loops...</p>"
    },
    advertisements: [
        { imageUrl: "static_assets/images/placeholder_ad.png", imageAlt: "Placeholder Advertisement 1" },
        { imageUrl: "static_assets/images/placeholder_ad.png", imageAlt: "Placeholder Advertisement 2" },
        { imageUrl: "static_assets/images/placeholder_ad.png", imageAlt: "Placeholder Advertisement 3" },
        { imageUrl: "static_assets/images/placeholder_ad.png", imageAlt: "Placeholder Advertisement 4" }
    ]
};

// Helper function to get the currently selected LLM
function getSelectedLLM() {
    const checkedRadio = document.querySelector('input[name="llm_choice"]:checked');
    return checkedRadio ? checkedRadio.value : (currentPaperData?.metadata?.defaultLLM || 'anthropic.claude-3-sonnet-20240229-v1:0');
}

// Helper function to get the currently selected Image Generator
function getSelectedImageGen() {
    const checkedRadio = document.querySelector('input[name="imagegen_choice"]:checked');
    return checkedRadio ? checkedRadio.value : (currentPaperData?.metadata?.defaultImageGen || 'amazon.titan-image-generator-v1');
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
function updateImage(id, imageData, defaultAltText, placeholderUrl = 'static_assets/images/placeholder_article.png', placeholderAlt = 'Content unavailable') {
    console.log(`updateImage called: id="${id}", imageData=`, imageData, `defaultAltText="${defaultAltText}"`);
    
    const imgElement = document.getElementById(id);
    console.log(`updateImage: imgElement=`, imgElement);
    
    if (imgElement) {
        if (imageData && (imageData.url || imageData.blocked)) {
            if (imageData.blocked) {
                console.log(`updateImage: Setting blocked image for ${id}`);
                imgElement.src = 'static_assets/images/placeholder_article.png';
                imgElement.alt = imageData.alt || "Image generation blocked due to safety policy";
                imgElement.style.display = '';
            } else {
                console.log(`updateImage: Setting image URL for ${id}: ${imageData.url}`);
                imgElement.src = imageData.url;
                imgElement.alt = imageData.alt || defaultAltText || 'Dynamic image content';
                imgElement.style.display = '';
            }
        } else if (typeof imageData === 'string' && imageData) { // Backward compatibility for direct URL string
            console.log(`updateImage: Setting direct URL string for ${id}: ${imageData}`);
            imgElement.src = imageData;
            imgElement.alt = defaultAltText || 'Dynamic image content';
            imgElement.style.display = '';
        }
        else { // Fallback to placeholder
            console.log(`updateImage: Setting placeholder for ${id}: ${placeholderUrl}`);
            imgElement.src = placeholderUrl;
            imgElement.alt = placeholderAlt;
            imgElement.style.display = ''; // Ensure placeholder is visible
        }
    } else {
        console.error(`updateImage: Element with id "${id}" not found`);
    }
}


// Function to render content based on currentPaperData and selections
function renderContent() {
    // Clear prompt cache when content changes (e.g., switching LLM models)
    if (typeof currentPromptCache !== 'undefined') {
        currentPromptCache.clear();
    }
    
    const basePath = currentContentUrl
        ? currentContentUrl.replace(/paper_content\.json(\?.*)?$/i, '') // Remove filename and any query parameters
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
            // Handle both old format {url, alt, blocked} and new format {imageUrl, imageAlt, blocked}
            url = imageData.url || imageData.imageUrl;
            alt = imageData.alt || imageData.imageAlt || alt;
            blocked = imageData.blocked || false;
        }

        if (blocked) {
            return { url: 'static_assets/images/placeholder_article.png', alt: alt, blocked: true };
        }
        if (!url) return { url: null, alt: alt };

        let finalUrl;
        if (/^(https?:)?\/\//.test(url) || url.startsWith('/') || url.startsWith('static_assets/')) {
            finalUrl = url;
        } else {
            finalUrl = basePath + url;
        }
        
        console.log(`Image processing: input="${url}", basePath="${basePath}", finalUrl="${finalUrl}"`);
        return { url: finalUrl, alt: alt };
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
        updateImage('llm-story-image', processImageData(newspaperPlaceholders.llmStory.imageUrl), newspaperPlaceholders.llmStory.imageAlt, 'static_assets/images/placeholder_article.png', newspaperPlaceholders.llmStory.imageAlt);

        updateElement('joke-content', newspaperPlaceholders.joke.content, true);
        updateImage('joke-image', processImageData(newspaperPlaceholders.joke.imageUrl), newspaperPlaceholders.joke.imageAlt, 'static_assets/images/placeholder_article.png', newspaperPlaceholders.joke.imageAlt);

        updateElement('author-bio', newspaperPlaceholders.authorBio.text, true);

        for (let i = 0; i < newspaperPlaceholders.advertisements.length; i++) {
            const adPlaceholder = newspaperPlaceholders.advertisements[i];
            const sponsorElementContainer = document.getElementById(`sponsor-${i + 1}`);
            if (sponsorElementContainer) {
                const imgElement = sponsorElementContainer.querySelector('img');
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
        console.log(`getImageDataForSlotKey: slotName="${slotName}", imageKey="${imageKey}"`);
        console.log(`getImageDataForSlotKey: slotData=`, slotData);
        
        if (!slotData?.imageOutputs) {
            console.log(`getImageDataForSlotKey: No imageOutputs found for slot "${slotName}"`);
            return null;
        }
        
        // Use the full model ID instead of extracting slug
        const modelId = selectedImageGen;
        console.log(`getImageDataForSlotKey: selectedImageGen="${selectedImageGen}", modelId="${modelId}"`);
        console.log(`getImageDataForSlotKey: imageOutputs=`, slotData.imageOutputs);
        
        // All slots now use the same structure: data stored as an object with prompt IDs as keys
        const modelOutputs = slotData.imageOutputs[modelId];
        console.log(`getImageDataForSlotKey: modelOutputs=`, modelOutputs);
        const result = modelOutputs?.[imageKey] || null;
        console.log(`getImageDataForSlotKey: result=`, result);
        return result;
    };

    // Helper to get LLM data using full model ID
    const getLlmDataForSlot = (slotName) => {
        const slotData = slots[slotName];
        if (!slotData?.llmOutputs) return null;
        
        // Use the full model ID instead of extracting slug
        const modelId = selectedLLM;
        return slotData.llmOutputs[modelId] || null;
    };

    // Main Article (mapped to img_01)
    const mainArticleLlmData = getLlmDataForSlot('mainArticle');
    updateElement('main-article-title', mainArticleLlmData?.title, true);
    updateElement('main-article-text', mainArticleLlmData?.text, true);
    const mainArticleImageData = getImageDataForSlotKey('mainArticle', 'img_01');
    console.log('Main article image data:', mainArticleImageData);
    const mainArticleImageProcessed = processImageData(mainArticleImageData);
    console.log('Main article image processed:', mainArticleImageProcessed);
    updateImage('main-article-image', mainArticleImageProcessed, 'Lead story illustration');


    // Comparison Article (mapped to img_02)
    const comparisonArticleLlmData = getLlmDataForSlot('comparisonArticle');
    updateElement('comparison-article-title', comparisonArticleLlmData?.title, true);
    updateElement('comparison-article-text', comparisonArticleLlmData?.text, true);
    const comparisonArticleImageData = getImageDataForSlotKey('comparisonArticle', 'img_02');
    console.log('Comparison article image data:', comparisonArticleImageData);
    const comparisonArticleImageProcessed = processImageData(comparisonArticleImageData);
    console.log('Comparison article image processed:', comparisonArticleImageProcessed);
    updateImage('comparison-article-image', comparisonArticleImageProcessed, 'Comparison story illustration');

    // LLM Story (mapped to img_07)
    const llmStoryLlmData = getLlmDataForSlot('llmStory');
    updateElement('llm-story-content', llmStoryLlmData?.content, true);
    const llmStoryImageData = getImageDataForSlotKey('llmStory', 'img_07');
    console.log('LLM story image data:', llmStoryImageData);
    const llmStoryImageProcessed = processImageData(llmStoryImageData);
    console.log('LLM story image processed:', llmStoryImageProcessed);
    updateImage('llm-story-image', llmStoryImageProcessed, 'LLM generated story illustration', newspaperPlaceholders.llmStory.imageUrl, newspaperPlaceholders.llmStory.imageAlt);


    // Joke (mapped to img_08)
    const jokeLlmData = getLlmDataForSlot('joke');
    updateElement('joke-content', jokeLlmData?.content, true);
    const jokeImageData = getImageDataForSlotKey('joke', 'img_08');
    console.log('Joke image data:', jokeImageData);
    const jokeImageProcessed = processImageData(jokeImageData);
    console.log('Joke image processed:', jokeImageProcessed);
    updateImage('joke-image', jokeImageProcessed, 'Joke illustration', newspaperPlaceholders.joke.imageUrl, newspaperPlaceholders.joke.imageAlt);


    // Author Bio
    const authorBioLlmData = getLlmDataForSlot('authorBio');
    updateElement('author-bio', authorBioLlmData?.content, true);

    // Sponsored Content - now handled as individual slots (advertisement1, advertisement2, etc.)
    const sponsorSlots = ['advertisement1', 'advertisement2', 'advertisement3', 'advertisement4'];
    const sponsorImageKeys = ['img_03', 'img_04', 'img_05', 'img_06'];
    
    for (let i = 0; i < sponsorSlots.length; i++) {
        const sponsorSlot = sponsorSlots[i];
        const sponsorKey = sponsorImageKeys[i];
        const sponsorElementId = `sponsor-${i + 1}`;
        const sponsorImgElement = document.getElementById(sponsorElementId)?.querySelector('img');

        if (sponsorImgElement) {
            const sponsorImageData = getImageDataForSlotKey(sponsorSlot, sponsorKey);
            console.log(`Sponsor ${i + 1} image data:`, sponsorImageData);
            const processedSponsorImage = processImageData(sponsorImageData);
            console.log(`Sponsor ${i + 1} image processed:`, processedSponsorImage);

            // Use specific placeholder for this sponsor if processedSponsorImage is null/invalid
            const placeholderSponsor = newspaperPlaceholders.advertisements[i] || { imageUrl: 'static_assets/images/placeholder_ad.png', imageAlt: 'Sponsored content unavailable' };
            
            if (processedSponsorImage && processedSponsorImage.url) {
                sponsorImgElement.src = processedSponsorImage.url;
                sponsorImgElement.alt = processedSponsorImage.alt || `Sponsored Content ${i + 1}`;
            } else {
                sponsorImgElement.src = placeholderSponsor.imageUrl;
                sponsorImgElement.alt = placeholderSponsor.imageAlt;
            }
            sponsorImgElement.style.display = '';
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
    const fullS3Url = `${S3_BUCKET_BASE_URL}/${relativePath}?v=${Date.now()}`;

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
    
    // Initialize prompt tooltips
    initializePromptTooltips();
});

// ========== PROMPT TOOLTIP SYSTEM ==========

let promptTooltip = null;
let tooltipTimeout = null;
let currentPromptCache = new Map();

// Create the tooltip element on page load
function createPromptTooltip() {
    if (promptTooltip) return;
    
    promptTooltip = document.createElement('div');
    promptTooltip.className = 'prompt-tooltip';
    promptTooltip.innerHTML = `
        <div class="prompt-tooltip-header"></div>
        <div class="prompt-tooltip-content"></div>
    `;
    document.body.appendChild(promptTooltip);
}

// Position tooltip near mouse cursor but keep it on screen
function positionTooltip(event) {
    if (!promptTooltip) return;
    
    const rect = promptTooltip.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    
    let x = event.clientX + 15;
    let y = event.clientY + 15;
    
    // Adjust if tooltip would go off right edge
    if (x + rect.width > viewportWidth) {
        x = event.clientX - rect.width - 15;
    }
    
    // Adjust if tooltip would go off bottom edge
    if (y + rect.height > viewportHeight) {
        y = event.clientY - rect.height - 15;
    }
    
    // Ensure tooltip doesn't go off top or left edges
    x = Math.max(10, x);
    y = Math.max(10, y);
    
    promptTooltip.style.left = x + 'px';
    promptTooltip.style.top = y + 'px';
}

// Fetch prompt data from S3
async function fetchPromptData(promptFile) {
    // Check cache first
    if (currentPromptCache.has(promptFile)) {
        return currentPromptCache.get(promptFile);
    }
    
    try {
        // Extract date from current content URL to build prompt path
        let promptUrl;
        
        if (currentContentUrl) {
            // Extract YYYY/MM/DD from the current content URL
            const contentUrlMatch = currentContentUrl.match(/static_assets\/content\/website\/(\d{4})\/(\d{2})\/(\d{2})/);
            if (contentUrlMatch) {
                const [, year, month, day] = contentUrlMatch;
                // Prompts are in static_assets/content/prompts/YYYY/MM/DD/ not website/YYYY/MM/DD/
                promptUrl = `${S3_BUCKET_BASE_URL}/static_assets/content/prompts/${year}/${month}/${day}/${promptFile}?v=${Date.now()}`;
            } else {
                // Fallback if we can't parse the date
                promptUrl = `${S3_BUCKET_BASE_URL}/static_assets/content/prompts/fallback/${promptFile}?v=${Date.now()}`;
            }
        } else {
            // Fallback when no content URL is available
            promptUrl = `${S3_BUCKET_BASE_URL}/static_assets/content/prompts/fallback/${promptFile}?v=${Date.now()}`;
        }
        
        console.log(`Fetching prompt from: ${promptUrl}`);
        
        const response = await fetch(promptUrl);
        if (!response.ok) {
            throw new Error(`Failed to fetch prompt: ${response.status}`);
        }
        
        const promptData = await response.json();
        
        // Cache the result
        currentPromptCache.set(promptFile, promptData);
        
        return promptData;
    } catch (error) {
        console.error(`Error fetching prompt ${promptFile}:`, error);
        return null;
    }
}

// Show tooltip with prompt content
async function showPromptTooltip(element, event) {
    if (!promptTooltip) createPromptTooltip();
    
    const promptType = element.dataset.promptType;
    const promptFile = element.dataset.promptFile;
    
    if (!promptType || !promptFile) return;
    
    // Clear any existing timeout
    clearTimeout(tooltipTimeout);
    
    // Show loading state
    const header = promptTooltip.querySelector('.prompt-tooltip-header');
    const content = promptTooltip.querySelector('.prompt-tooltip-content');
    
    header.textContent = `${promptType.toUpperCase()} Prompt - Loading...`;
    content.textContent = 'Fetching prompt data...';
    
    // Position and show tooltip
    positionTooltip(event);
    promptTooltip.classList.add('visible');
    
    // Fetch prompt data
    const promptData = await fetchPromptData(promptFile);
    
    if (promptData) {
        // Update header
        const promptTypeName = promptType === 'llm' ? 'LLM' : 'Image Generation';
        header.textContent = `${promptTypeName} Prompt (${promptFile})`;
        
        // Format content based on prompt type
        if (promptType === 'llm') {
            // For LLM prompts, show the main prompt content
            if (promptData.prompt) {
                content.textContent = promptData.prompt;
            } else if (promptData.messages && Array.isArray(promptData.messages)) {
                // Handle messages format (like Claude)
                const messagesText = promptData.messages
                    .map(msg => `${msg.role}: ${msg.content}`)
                    .join('\n\n');
                content.textContent = messagesText;
            } else {
                content.textContent = JSON.stringify(promptData, null, 2);
            }
        } else if (promptType === 'image') {
            // For image prompts, show the text prompt and any relevant config
            let imagePromptText = '';
            
            if (promptData.textPrompt || promptData.text_prompts) {
                imagePromptText = promptData.textPrompt || 
                    (promptData.text_prompts && promptData.text_prompts[0]?.text) || 
                    'No text prompt found';
            } else if (promptData.prompt) {
                imagePromptText = promptData.prompt;
            } else {
                imagePromptText = JSON.stringify(promptData, null, 2);
            }
            
            content.textContent = imagePromptText;
            
            // Add configuration info if available
            if (promptData.width && promptData.height) {
                content.textContent += `\n\nDimensions: ${promptData.width}x${promptData.height}`;
            }
            if (promptData.numberOfImages) {
                content.textContent += `\nNumber of images: ${promptData.numberOfImages}`;
            }
        }
    } else {
        header.textContent = `${promptType.toUpperCase()} Prompt - Error`;
        content.textContent = 'Failed to load prompt data. The prompt file may not exist for this date.';
    }
    
    // Set auto-hide timeout (10 seconds)
    tooltipTimeout = setTimeout(() => {
        hidePromptTooltip();
    }, 10000);
}

// Hide tooltip
function hidePromptTooltip() {
    if (promptTooltip) {
        promptTooltip.classList.remove('visible');
    }
    clearTimeout(tooltipTimeout);
}

// Initialize tooltip event listeners
function initializePromptTooltips() {
    // Create tooltip element
    createPromptTooltip();
    
    // Add event listeners for all elements with prompt data
    document.addEventListener('mouseover', (event) => {
        const target = event.target.closest('[data-prompt-type]');
        if (target) {
            showPromptTooltip(target, event);
        }
    });
    
    document.addEventListener('mouseout', (event) => {
        const target = event.target.closest('[data-prompt-type]');
        if (target) {
            // Check if we're really leaving the element (not just moving to a child)
            if (!target.contains(event.relatedTarget)) {
                hidePromptTooltip();
            }
        }
    });
    
    // Hide tooltip when scrolling or resizing
    document.addEventListener('scroll', hidePromptTooltip);
    window.addEventListener('resize', hidePromptTooltip);
    
    // Update prompt cache clearing
    const originalFetchContentForDate = window.fetchContentForDate || fetchContentForDate;
    window.fetchContentForDate = function(...args) {
        currentPromptCache.clear(); // Clear cache when loading new date
        return originalFetchContentForDate.apply(this, args);
    };
}