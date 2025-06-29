# CraicGPT Enhanced Prompt Generator

## Overview

The CraicGPT prompt generator has been completely refactored to provide truly dynamic daily content with clear separation of context sources and full date range support. This ensures each day's content is unique and contextually relevant.

## 🎯 Key Features

### ✨ Three Clear Context Sources

Every prompt is built from exactly three distinct context sources:

1. **BASE CONTEXT** - Consistent themes and purposes (easily configurable)
2. **DAILY CONTEXT** - Fresh news, events, and trends for specific dates  
3. **WEATHER/LOCATION** - Weather and location context for specific dates

### 🗓️ Date Range Support

All three Lambda functions now support date ranges:

- **Single date**: `{"date": "2025-01-15"}`
- **Date range**: `{"start_date": "2025-01-10", "end_date": "2025-01-15"}`
- **Custom dates**: `{"dates": ["2025-01-10", "2025-01-12", "2025-01-15"]}`

### 🌊 Enhanced Daily Variation

- Historical weather patterns for past dates
- Plausible news context for historical dates
- Seasonal local events
- Trending topic extraction
- Weather-aware image prompts

## 📁 Context Source Configuration

### 1. Base Context (Static, Easily Configurable)

Located in `BASE_CONTEXTS` dictionary:

```python
BASE_CONTEXTS = {
    "main_article": {
        "character": "Graz, 54 and a quarter, cybersecurity engineer",
        "style": "first-person diary form, dry wit of Adrian Mole",
        "location": "Pontesbury, Shropshire",
        "family": {
            "Lizzy": "brilliant wife who funds globe-trotting 'really important IT thingys'",
            "Noreen (19)": "'Steve Davis of kids', brilliant yet boring",
            # ... more family members
        },
        "tone": "self-deprecating, observational and silly",
        "length": "approximately 650 words",
        "requirements": "Mention one plausible local Shropshire event"
    },
    # ... other content types
}
```

**Easy to modify**: Simply update the dictionaries to change character traits, tone, requirements, etc.

### 2. Daily Context (Dynamic, Date-Specific)

Sources configured in `NEWS_SOURCES`:

```python
NEWS_SOURCES = {
    "tech": {
        "TheRegister": "https://www.theregister.com/",
        "BBCTech": "https://www.bbc.com/news/technology",
        "ArsTechnica": "https://arstechnica.com/",
        "TechCrunch": "https://techcrunch.com/"
    },
    "local": {
        "ShropshireStar": "https://www.shropshirestar.com/",
        "IrishTimes": "https://www.irishtimes.com/",
        "BBCShropshire": "https://www.bbc.co.uk/news/england/shropshire"
    },
    "security": {
        "KrebsOnSecurity": "https://krebsonsecurity.com/",
        "SchneierOnSecurity": "https://www.schneier.com/",
        "BleepingComputer": "https://www.bleepingcomputer.com/"
    }
}
```

### 3. Weather/Location Context (Dynamic, Date-Aware)

For current dates: Live BBC weather API with 3-layer fallback
For historical dates: Seasonal weather patterns based on month and location

## 🚀 Usage Examples

### Single Date Generation

```bash
# Prompt Generator
aws lambda invoke \
  --function-name craicgpt-prompt-generator \
  --payload '{"date": "2025-01-15"}' \
  response.json

# LLM Handler
aws lambda invoke \
  --function-name craicgpt-llm-handler \
  --payload '{"date": "2025-01-15"}' \
  response.json

# Image Handler  
aws lambda invoke \
  --function-name craicgpt-image-handler \
  --payload '{"date": "2025-01-15"}' \
  response.json
```

### Date Range Generation

```bash
# Generate content for a week
aws lambda invoke \
  --function-name craicgpt-prompt-generator \
  --payload '{"start_date": "2025-01-10", "end_date": "2025-01-16"}' \
  response.json

# Process the generated prompts
aws lambda invoke \
  --function-name craicgpt-llm-handler \
  --payload '{"start_date": "2025-01-10", "end_date": "2025-01-16"}' \
  response.json

aws lambda invoke \
  --function-name craicgpt-image-handler \
  --payload '{"start_date": "2025-01-10", "end_date": "2025-01-16"}' \
  response.json
```

### Custom Configuration

```bash
# Custom models and prompts
aws lambda invoke \
  --function-name craicgpt-llm-handler \
  --payload '{
    "dates": ["2025-01-15", "2025-01-20"], 
    "model_ids": ["anthropic.claude-3-sonnet-20240229-v1:0"],
    "prompt_ids": ["llm_01", "llm_03"]
  }' \
  response.json
```

## 📊 Sample Output Structure

### Prompt Generator Response

```json
{
  "status": "SUCCESS",
  "dates_processed": ["2025-01-10", "2025-01-11", "2025-01-12"],
  "prompts_generated": 36,
  "configuration": {
    "fresh_context_enabled": true,
    "historical_weather_enabled": true,
    "base_contexts_loaded": 5,
    "news_sources": 3
  },
  "sample_daily_context": {
    "date": "2025-01-10",
    "weather_source": "seasonal_pattern",
    "trending_topics": ["ai", "cybersecurity", "cloud"],
    "news_categories": ["tech", "local", "security"]
  }
}
```

### LLM Handler Response

```json
{
  "status": "SUCCESS",
  "processing_time_seconds": 45.2,
  "dates_processed": 3,
  "dates_failed": 0,
  "total_dates": 3,
  "prompt_ids": ["llm_01", "llm_02", "llm_03", "llm_04"],
  "models_used": ["anthropic.claude-3-sonnet-20240229-v1:0"],
  "results": {
    "2025-01-10": {
      "llm_01": {
        "anthropic.claude-3-sonnet-20240229-v1:0": "results/2025-01-10/llm_01/anthropic_claude-3-sonnet-20240229-v1_0.txt"
      }
    }
  }
}
```

## 🏗️ Prompt Structure Examples

### Main Article Prompt Structure

```
WRITING STYLE: approximately 650 words in first-person diary form, dry wit of Adrian Mole
CHARACTER: Graz, 54 and a quarter, cybersecurity engineer in Pontesbury, Shropshire
TONE: self-deprecating, observational and silly
REQUIREMENT: Mention one plausible local Shropshire event

FAMILY MEMBERS:
• Lizzy - brilliant wife who funds globe-trotting "really important IT thingys"
• Noreen (19) - "Steve Davis of kids", brilliant yet boring
• Saoirse (17) - grunge guitarist saving to visit a Parisian grave
• Terry (13) - rugby-obsessed son you "fake-coach"
• Eddie - over-mortgaged black cockapoo
• Puddle - impulsively-adopted white kitten

WEATHER CONTEXT:
• Today: Mild but damp in Pontesbury, Shropshire
• Tonight: Cloudy and cold expected

LOCAL EVENTS:
• Pontesbury village pub quiz night in January
• Pontesbury local craft fair in January

TECH NEWS CONTEXT:
• AI developments continue to shape industry trends
• New cybersecurity challenges emerge in 2025
• Cloud computing adoption accelerates across sectors

TRENDING TOPICS: ai, cybersecurity, cloud, quantum

Write your diary entry for **Wednesday 15 January 2025**. Include references to the weather, a local event, family antics, and weave in current tech trends naturally.
```

## 🔧 Configuration

### Environment Variables

```bash
# Required
PROMPT_BUCKET=your-s3-bucket-name
BEDROCK_MODEL_IDS=anthropic.claude-3-sonnet-20240229-v1:0,cohere.command-r-v1:0
BEDROCK_IMAGE_MODEL_IDS=amazon.titan-image-generator-v1,amazon.nova-canvas-v1:0

# Optional (defaults shown)
ENABLE_FRESH_CONTEXT=true
ENABLE_HISTORICAL_WEATHER=true
AWS_REGION=eu-west-1
ALLOW_EMBED_MODELS=false
```

### Customizing Base Contexts

To modify character traits, tone, or requirements:

1. Edit the `BASE_CONTEXTS` dictionary in `lambda_function.py`
2. Update family members, character descriptions, or writing styles
3. Modify content requirements or formats
4. Redeploy the Lambda function

### Adding News Sources

To add new news sources:

1. Update the `NEWS_SOURCES` dictionary
2. Add new categories or sources within existing categories
3. The system will automatically scrape headlines from new sources

## 🌍 Historical Date Handling

### Weather for Historical Dates

- **Recent dates** (±2 days): Live BBC weather API
- **Historical dates**: Seasonal weather patterns based on:
  - Month-appropriate weather for Shropshire
  - Realistic seasonal variations
  - Consistent regional characteristics

### News for Historical Dates

- **Current dates**: Live headline scraping
- **Historical dates**: Contextually appropriate headlines based on:
  - Date and seasonal context
  - Industry trends for that time period
  - Plausible local and regional events

### Local Events

Generated based on:
- Season-appropriate activities
- British village life patterns
- Pontesbury/Shropshire context
- Month-specific events

## 🔍 Debugging and Monitoring

### Logging

All functions provide comprehensive logging:
- Date processing progress
- Context source success/failure
- Model invocation details
- Token usage tracking (LLM handler)
- Image generation statistics

### Storage Structure

```
s3://your-bucket/
├── static_assets/content/prompts/YYYY/MM/DD/
│   ├── llm_01.json  # Main article prompt + context summary
│   ├── llm_02.json  # Comparison article prompt
│   ├── img_01.json  # Main article image prompt
│   └── ...
├── static_assets/content/website/YYYY/MM/DD/
│   ├── paper_content.json  # Final compiled newspaper
│   ├── img_01_model_512.png  # Generated images
│   └── ...
└── results/YYYY-MM-DD/prompt_id/
    └── model_slug.txt  # Raw LLM outputs
```

## 🎨 Benefits of New Structure

1. **Clear Separation**: Easy to see and modify each context source
2. **Daily Variation**: Each day gets genuinely unique context
3. **Historical Support**: Generate content for any date range
4. **Easy Configuration**: Modify base contexts without code changes
5. **Resilient**: Multiple fallbacks for weather and news
6. **Scalable**: Process multiple dates efficiently
7. **Debuggable**: Clear logging and storage structure

## 🚀 Quick Start for Development

1. **Test single date**:
   ```bash
   aws lambda invoke --function-name craicgpt-prompt-generator \
     --payload '{"date": "2025-01-15"}' response.json
   ```

2. **Verify prompts created**:
   ```bash
   aws s3 ls s3://your-bucket/static_assets/content/prompts/2025/01/15/
   ```

3. **Generate content**:
   ```bash
   aws lambda invoke --function-name craicgpt-llm-handler \
     --payload '{"date": "2025-01-15"}' response.json
   ```

4. **Check results**:
   ```bash
   aws s3 ls s3://your-bucket/static_assets/content/website/2025/01/15/
   ```

This enhanced structure ensures every day's content is truly unique while maintaining the character and tone that makes CraicGPT special! 