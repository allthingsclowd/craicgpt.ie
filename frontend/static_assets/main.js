// /static_assets/main.js
window.addEventListener('load', () => {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-indexed
    const day = String(today.getDate()).padStart(2, '0');

    const contentUrl = `/content/${year}/${month}/${day}/todays_paper.json`;
    // For local testing, you might point to a local file or a fixed CloudFront URL
    // const contentUrl = 'todays_paper_example.json'; 

    // Update current date display
    const dateElement = document.getElementById('current-date');
    if (dateElement) {
        dateElement.textContent = today.toLocaleDateString('en-IE', { 
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' 
        });
    }
    
    // Update footer year
    const footerYearElement = document.getElementById('footer-year');
    if (footerYearElement) {
        footerYearElement.textContent = year;
    }

    fetch(contentUrl)
       .then(response => {
            if (!response.ok) {
                throw new Error(`Network response was not ok: ${response.statusText} (Status: ${response.status})`);
            }
            return response.json();
        })
       .then(data => {
            console.log("Fetched content:", data); // For debugging
            updateElement('newspaper-banner', data.banner?.title, true, 'h1');
            updateElement('current-date', data.date, false); // Date is already set above, but can be overridden by JSON

            // Main Article
            updateElement('main-article-title', data.mainArticle?.title, true, 'h2');
            updateImage('main-article-image', data.mainArticle?.imageUrl, data.mainArticle?.imageAlt);
            updateElement('main-article-text', data.mainArticle?.text, true);

            // Comparison Article
            updateElement('comparison-article-title', data.comparisonArticle?.title, true, 'h2');
            updateImage('comparison-article-image', data.comparisonArticle?.imageUrl, data.comparisonArticle?.imageAlt);
            updateElement('comparison-article-text', data.comparisonArticle?.text, true);
            
            // Author Bio (can be static or dynamic)
            if (data.authorBio) {
                updateElement('author-bio', data.authorBio, true);
            }

            // LLM Story
            updateElement('llm-story-content', data.llmStory?.content, true);
            
            // Joke
            updateElement('joke-content', data.joke?.content, true);

            // Advertisements
            if (data.advertisements && Array.isArray(data.advertisements)) {
                for (let i = 0; i < 4; i++) {
                    if (data.advertisements[i]) {
                        updateElement(`ad-${i + 1}`, data.advertisements[i].text, true);
                        // Could also handle ad images if structure supports it:
                        // updateImage(`ad-${i+1}-image`, data.advertisements[i].imageUrl, data.advertisements[i].imageAlt);
                    } else {
                        updateElement(`ad-${i + 1}`, 'Advertisement space available.', false);
                    }
                }
            }
        })
       .catch(error => {
            console.error('Error fetching or parsing daily content:', error);
            // Display a user-friendly error message on the page
            const mainContent = document.getElementById('main-content');
            if (mainContent) {
                mainContent.innerHTML = `<p class="error-message">Sorry, we couldn't load today's Craic. The AI might be on a tea break. Please try again later. (Error: ${error.message})</p>`;
            }
            // Fallback for critical elements if needed
            updateElement('newspaper-banner', 'CraicGPT.ie - Offline Edition', true, 'h1');
            updateElement('main-article-title', 'Content Unavailable', true, 'h2');
        });
});

function updateElement(id, content, isHtml = false, wrapperTag = 'p') {
    const element = document.getElementById(id);
    if (element && content!== undefined && content!== null) {
        if (isHtml) {
            // Ensure content is a string before setting innerHTML
            element.innerHTML = String(content); 
        } else {
            element.textContent = String(content);
        }
    } else if (element) {
        // Optionally clear or set default text if content is not available
        // element.innerHTML = `<${wrapperTag}>Content for ${id} not available.</${wrapperTag}>`;
        console.warn(`Content for element ID '${id}' not found in JSON or element does not exist.`);
    }
}

function updateImage(id, imageUrl, altText) {
    const imgElement = document.getElementById(id);
    if (imgElement && imageUrl) {
        imgElement.src = imageUrl;
        imgElement.alt = altText |
| 'Dynamic image content';
    } else if (imgElement) {
        // imgElement.style.display = 'none'; // Hide if no image URL
        console.warn(`Image URL for element ID '${id}' not found in JSON or element does not exist.`);
    }
}