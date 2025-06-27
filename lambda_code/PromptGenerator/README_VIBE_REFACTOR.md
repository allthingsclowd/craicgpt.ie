# Prompt Generator - VIBE EDITION ✨

## Overview

The prompt generator lambda function has been completely refactored using **vibe coding style** to create a more engaging, context-aware content generation system. This refactor maintains all existing storage naming conventions while adding powerful new features.

## 🎯 Key Features

### ✨ Vibe Coding Style
- **Emoji-rich comments** and function names
- **Playful documentation** with personality
- **Clear, descriptive naming** conventions
- **Modular, maintainable structure**

### 🌊 Optional Context Mechanisms

#### Fresh Context (Optional)
- **Environment Variable**: `ENABLE_FRESH_CONTEXT` (default: false)
- **Sources**: Tech news, local news, security blogs
- **Usage**: Injects current headlines and trends into prompts
- **Categories**:
  - `tech_vibes`: TheRegister, BBC Tech, ArsTechnica, TechCrunch
  - `local_vibes`: Shropshire Star, Pontesbury Parish Council, Irish Times
  - `security_vibes`: Aqua Blog, Schneier on Security, Krebs on Security

#### Historical Context (Optional)
- **Environment Variable**: `ENABLE_HISTORICAL_CONTEXT` (default: false)
- **Scope**: 7-day review of published content
- **Usage**: Maintains story continuity and avoids repetition
- **Access**: Requires `s3:GetObject` permission

## 📝 Prompt Structure

### LLM Prompts (4 total)

| ID | Type | Content | Temperature | Context |
|----|------|---------|-------------|---------|
| `llm_01` | main-article-text | Graz's diary entry | 0.9 | Weather, local events, family antics |
| `llm_02` | comparison-article-text | Top-10 LLMs ranking | 0.7 | Tech trends, AI developments |
| `llm_03` | llm-story-content | Everyday LLM story | 0.9 | Local vibes, relatable scenarios |
| `llm_04` | joke-content | AI humor one-liner | 0.8 | AI headlines, Sam Altman references |

### Image Prompts (8 total)

| ID | Type | Content | Size |
|----|------|---------|------|
| `img_01` | article-image | Graz's family comic scene | 1024x1024 |
| `img_02` | comparison-article-image | LLM capability chart | 1024x1024 |
| `img_03` | ad-1 | Quantum password post-its | 1024x1024 |
| `img_04` | ad-2 | LLM-Os cereal box | 1024x1024 |
| `img_05` | ad-3 | Promptesbury travel poster | 1024x1024 |
| `img_06` | ad-4 | TOKEN Nº5 perfume | 1024x1024 |
| `img_07` | llm-story-image | Postman origami scene | 1024x1024 |
| `img_08` | joke-image | Sam Altman Clippy cartoon | 1024x1024 |

## 🔧 Environment Variables

```bash
# Required
PROMPT_BUCKET=your-s3-bucket-name

# Model Configuration
BEDROCK_MODEL_IDS=anthropic.claude-3-sonnet-20240229-v1:0
BEDROCK_IMAGE_MODEL_IDS=stability.stable-diffusion-xl-v1

# Optional Features
ENABLE_FRESH_CONTEXT=false
ENABLE_HISTORICAL_CONTEXT=false
```

## 🏗️ Architecture

### Data Classes
- **`VibeContext`**: Container for all context data
- **`PromptConfig`**: Configuration for each prompt type

### Core Functions
- **`build_vibe_context()`**: Gathers all context data
- **`get_historical_context()`**: Retrieves 7-day content history
- **`extract_trending_themes()`**: Identifies trending topics
- **`build_*_prompt()`**: Individual prompt builders

### Storage Structure
```
static_assets/content/prompts/YYYY/MM/DD/
├── llm_01.json (main article)
├── llm_02.json (comparison article)
├── llm_03.json (LLM story)
├── llm_04.json (joke)
├── img_01.json (main article image)
├── img_02.json (comparison image)
├── img_03.json (ad 1)
├── img_04.json (ad 2)
├── img_05.json (ad 3)
├── img_06.json (ad 4)
├── img_07.json (LLM story image)
└── img_08.json (joke image)
```

## 🚀 Usage Examples

### Basic Usage
```python
# Lambda handler automatically generates all prompts
response = lambda_handler({}, None)
# Returns: {"status": "VIBES_OK ✨", "saved_prompts": 12, ...}
```

### With Context Features Enabled
```bash
# Enable fresh context from trending websites
ENABLE_FRESH_CONTEXT=true

# Enable historical context for story continuity
ENABLE_HISTORICAL_CONTEXT=true
```

## 🔍 Context Injection Examples

### Fresh Context in Main Article
```
🌤️ Weather Vibes:
  • Today: Sunny with scattered clouds
  • Tonight: Clear skies, perfect for stargazing

📰 Tech Vibes:
  • OpenAI releases GPT-5 with quantum capabilities
  • New cybersecurity breach affects major cloud provider
  • AI regulation talks heat up in Brussels

🔥 Trending Vibes: ai, cybersecurity, quantum, regulation

Date: **Monday 15 January 2025**
```

### Historical Context
```
📚 Historical context from the last 7 days:
Last week Graz mentioned the new quantum computer at the local library and how Eddie the cockapoo tried to eat the instruction manual. The family went to the Shropshire tech fair where Saoirse performed with her grunge band...

Use this context to maintain story continuity and avoid repetition.
```

## 🎨 Vibe Features

### Trending Theme Detection
Automatically identifies trending topics from headlines:
- AI/ML developments
- Cybersecurity news
- Cloud computing updates
- Startup funding
- Conference announcements

### Weather Integration
Three-layer weather extraction:
1. BBC JSON API
2. BBC RSS feed
3. BBC HTML scraping
4. Fallback to generic message

### Content Continuity
Historical context helps maintain:
- Character development
- Story arcs
- Relationship dynamics
- Local event references

## 🔐 IAM Permissions

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::your-bucket/static_assets/content/prompts/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject"
            ],
            "Resource": "arn:aws:s3:::your-bucket/static_assets/content/website/*"
        }
    ]
}
```

## 🎯 Benefits

1. **Maintains Compatibility**: All existing storage paths and naming conventions preserved
2. **Enhanced Context**: Optional fresh and historical context injection
3. **Better Content**: More engaging, current, and continuous storytelling
4. **Scalable**: Easy to add new context sources or prompt types
5. **Maintainable**: Clear structure with vibe coding style
6. **Flexible**: Context features can be enabled/disabled via environment variables

## 🚀 Future Enhancements

- **Sentiment Analysis**: Analyze context sentiment for tone matching
- **Topic Clustering**: Group related headlines for better context
- **Personalization**: User-specific context injection
- **Multi-language**: Support for additional languages
- **A/B Testing**: Context variation testing

---

*Built with maximum vibes and minimum bugs ✨* 