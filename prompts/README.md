# Prompts - Base Templates and Examples

**Foundation Prompt Engineering for CraicGPT Multi-Provider AI System**

This directory contains the base prompt templates and examples used throughout the CraicGPT.ie system. These prompts serve as the foundation for content generation across all supported AI providers and demonstrate best practices in prompt engineering.

## 🎯 Purpose

Provide a centralized collection of prompt templates, examples, and documentation to:
- Ensure consistent content generation across all AI providers
- Demonstrate prompt engineering best practices
- Enable easy customization and experimentation
- Document the evolution of the CraicGPT concept and implementation

## 📁 Directory Contents

### **Initial Project Vision**
- **`initial-prompt.txt`**: Original concept and requirements for CraicGPT.ie
- **`second-major-prompt.txt`**: Follow-up specifications and refinements

### **Prompt Categories** (Generated dynamically by system)
Daily generated prompts are stored in S3 with the following structure:
```
s3://bucket/static_assets/content/prompts/YYYY/MM/DD/
├── llm_01.json    # Main article prompt
├── llm_02.json    # Comparison article prompt  
├── llm_03.json    # LLM story prompt
├── llm_04.json    # Daily joke prompt
├── llm_05.json    # Author bio prompt
├── img_01.json    # Main article image prompt
├── img_02.json    # Comparison image prompt
├── img_03.json    # Advertisement 1 prompt
├── img_04.json    # Advertisement 2 prompt
├── img_05.json    # Advertisement 3 prompt
├── img_06.json    # Advertisement 4 prompt
├── img_07.json    # LLM story image prompt
└── img_08.json    # Joke image prompt
```

## 🏗️ Prompt Engineering Architecture

### **Multi-Provider Optimization**
All prompts are engineered to work effectively across:
- **AWS Bedrock**: Claude models, Titan Text/Image, Nova Canvas
- **OpenAI**: GPT-4, O3 Mini, DALL-E 3
- **Anthropic Direct**: Claude 3.5 Sonnet, Claude 3 Opus
- **Google Gemini**: Gemini Pro, Gemini Ultra

### **Prompt Engineering Parameters**
Each prompt includes explicit parameters for educational demonstration:

```json
{
  "prompt_engineering_parameters": {
    "temperature": {
      "factual_content": 0.2,
      "balanced_content": 0.6,
      "creative_content": 0.9
    },
    "max_tokens": {
      "short_form": 150,
      "medium_form": 500,
      "long_form": 800
    },
    "top_p": {
      "focused": 0.3,
      "balanced": 0.7,
      "creative": 0.95
    }
  }
}
```

## 📊 Content Generation Framework

### **LLM Content Types**

#### **Main Article (llm_01)**
**Purpose**: Primary newspaper article with title and comprehensive text
**Template Structure**:
```
You are an AI journalist writing for 'The Artificially Intelligent Times'. 

Context: [Weather, News Headlines, Tech Trends]
Task: Write a compelling main article about [topic]
Format: JSON with "title" and "text" fields
Style: Professional journalism with engaging narrative
Length: 600-800 words
Parameters: Temperature 0.6, Max Tokens 800, Top-P 0.7
```

#### **Comparison Article (llm_02)**
**Purpose**: Technical comparison of AI models and capabilities
**Template Structure**:
```
You are a tech analyst for 'The Artificially Intelligent Times'.

Context: [Current AI developments, Model releases]
Task: Create a detailed comparison of AI models
Format: JSON with "title" and "text" fields  
Style: Technical but accessible, data-driven
Length: 500-700 words
Parameters: Temperature 0.2, Max Tokens 700, Top-P 0.3
```

#### **LLM Story (llm_03)**
**Purpose**: Feature story about AI and technology trends
**Template Structure**:
```
You are a feature writer exploring AI's impact on society.

Context: [Personal anecdotes, Local events, Tech trends]
Task: Write an engaging story about AI in daily life
Format: JSON with "content" field
Style: Narrative storytelling with personal touch
Length: 400-600 words
Parameters: Temperature 0.7, Max Tokens 600, Top-P 0.8
```

#### **Daily Joke (llm_04)**
**Purpose**: AI-themed humor and light content
**Template Structure**:
```
You are a comedy writer for 'The Artificially Intelligent Times'.

Context: [Current events, AI developments]
Task: Create a witty, family-friendly AI joke
Format: JSON with "content" field
Style: Clean humor, wordplay, AI references
Length: 50-150 words
Parameters: Temperature 0.9, Max Tokens 150, Top-P 0.95
```

#### **Author Bio (llm_05)**
**Purpose**: Personal background and website purpose explanation
**Template Structure**:
```
You are writing an author bio for Graham Land, creator of CraicGPT.ie.

Context: [Personal details, Website purpose, AI enthusiasm]
Task: Create an engaging author biography
Format: JSON with "content" field
Style: Professional yet approachable, personal
Length: 150-300 words
Parameters: Temperature 0.6, Max Tokens 300, Top-P 0.7
```

### **Image Generation Prompts**

#### **Main Article Image (img_01)**
**Template Structure**:
```
Create a professional newspaper illustration for an article about [topic].

Style: Editorial illustration, clean design, newspaper appropriate
Content: [Article summary for visual context]
Requirements: 512x512 pixels, high contrast, readable
Avoid: Text overlays, copyrighted characters, inappropriate content
```

#### **Advertisement Images (img_03-06)**
**Template Structure**:
```
Design a clean, professional advertisement for [product/service].

Style: Modern, minimalist, commercial design
Layout: Product-focused with clear visual hierarchy
Colors: Professional palette, brand-appropriate
Requirements: 512x512 pixels, commercial quality
```

#### **Joke Illustration (img_08)**
**Template Structure**:
```
Create a humorous, family-friendly illustration for an AI joke.

Style: Cartoon-like, whimsical, approachable
Content: [Joke context for visual representation]
Mood: Light-hearted, fun, engaging
Requirements: 512x512 pixels, colorful, expressive
```

## 🔧 Context Integration

### **Weather Context Influence**
- **Mood Setting**: Weather conditions influence article tone and opening material
- **Natural Integration**: Seamlessly woven into content for authenticity
- **Seasonal Relevance**: Connects current conditions to broader themes

### **News Headlines Integration**
- **"Headline Hijacking"**: Personal connection to current events
- **Relevance Bridge**: Links global news to AI and technology topics
- **Topical Currency**: Ensures content feels current and relevant

### **Family and Personal Context**
- **"Family Follies"**: Personal anecdotes and relatable situations
- **Local Connection**: Shropshire and Pontesbury references for authenticity
- **Work Integration**: IT professional perspective on technology

### **Tech Trends Context**
- **Industry Insight**: Current AI and technology developments
- **Professional Perspective**: Technical accuracy with accessibility
- **Future Speculation**: Informed predictions and analysis

## 📈 Prompt Optimization Strategies

### **Provider-Specific Adaptations**
- **Claude Models**: Emphasis on nuanced reasoning and detailed analysis
- **GPT Models**: Focus on creative expression and engaging narratives
- **Gemini Models**: Leverage multimodal capabilities and structured output
- **Image Models**: Optimize for style consistency and quality output

### **Performance Metrics**
- **Content Quality**: Human evaluation of output relevance and engagement
- **Consistency**: Cross-provider comparison for similar topics
- **Efficiency**: Token usage and generation time optimization
- **Success Rate**: Percentage of successful prompt executions

### **A/B Testing Framework**
- **Template Variations**: Test different prompt structures
- **Parameter Tuning**: Optimize temperature, top-p, and token limits
- **Context Experiments**: Evaluate different context integration approaches
- **Style Comparisons**: Compare formal vs. conversational tones

## 🔍 Example Prompt Evolution

### **Original Concept (initial-prompt.txt)**
The initial vision focused on:
- Traditional newspaper layout and style
- Multi-provider AI comparison capabilities
- Daily content generation automation
- Educational demonstration of AI differences

### **Refined Implementation**
Evolution toward:
- Explicit prompt engineering parameters
- Comprehensive context integration
- Provider-specific optimizations
- Educational value and transparency

### **Current Best Practices**
- Clear task definition and expected output format
- Explicit parameter settings for educational value
- Rich context integration for authentic content
- Cross-provider compatibility and optimization

## 🧪 Testing and Validation

### **Prompt Testing Framework**
```bash
# Test individual prompt types
aws lambda invoke \
  --function-name craicgptie_prompt_generator \
  --payload '{"START_DATE":"2025-01-15","END_DATE":"2025-01-15"}' \
  test-prompts.json

# Validate generated prompts
aws s3 cp s3://bucket/static_assets/content/prompts/2025/01/15/llm_01.json - | jq .

# Test with specific models
aws lambda invoke \
  --function-name craicgptie_llm_runner \
  --payload '{"date":"2025-01-15","model_id":"gpt-4","prompt_ids":["llm_01"]}' \
  test-output.json
```

### **Quality Validation**
- **Content Relevance**: Does output match prompt expectations?
- **Format Compliance**: Proper JSON structure and required fields?
- **Educational Value**: Clear demonstration of prompt engineering?
- **Cross-Provider Consistency**: Similar quality across all models?

## 🤝 Contributing

### **Adding New Prompt Templates**
1. Define prompt purpose and target content type
2. Create base template with clear instructions
3. Add provider-specific optimizations
4. Include explicit parameter settings
5. Test across all supported models
6. Document expected output format

### **Improving Existing Prompts**
1. Analyze current performance metrics
2. Identify optimization opportunities
3. Test variations with A/B framework
4. Validate improvements across providers
5. Update documentation and examples

### **Context Enhancement**
1. Identify new context sources
2. Develop integration strategies
3. Test impact on content quality
4. Optimize for multiple prompt types
5. Document context influence patterns

## 🔗 Integration with System Components

### **PromptGenerator Lambda**
- Reads base templates from this directory
- Applies context and customization
- Generates daily prompt files for all content types
- Stores optimized prompts in S3 for worker consumption

### **LLM and Image Handlers**
- Consume generated prompts from S3 storage
- Apply provider-specific parameter settings
- Execute content generation with optimized prompts
- Return structured output matching prompt specifications

### **Frontend Display**
- Showcases prompt engineering parameters for educational value
- Demonstrates differences in provider outputs from same prompts
- Provides transparency into AI content generation process

**Foundation Prompt Engineering - Educational and Production Ready** 📝