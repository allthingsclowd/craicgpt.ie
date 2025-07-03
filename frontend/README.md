# Frontend - Static Newspaper Website

**Production-Ready Static Website with Multi-Provider Model Selection**

This directory contains the frontend components for the CraicGPT.ie newspaper website. The frontend is a static HTML/CSS/JavaScript application deployed to AWS S3 with CloudFront CDN distribution.

## 🏗️ Architecture

### **Static Website Components**
- **HTML Structure**: Semantic newspaper layout with content sections
- **CSS Styling**: Responsive design with newspaper aesthetic
- **JavaScript**: Dynamic content loading and date picker functionality
- **Assets**: Images, fonts, and vendor libraries

### **Content Integration**
- **Dynamic Loading**: Fetches generated content from S3 JSON files
- **Date Navigation**: Calendar picker for historical content browsing
- **Model Selection**: Radio buttons for choosing AI providers
- **Real-time Updates**: Automatic refresh when new content is available

## 📁 Directory Structure

```
frontend/
├── index.html                 # Main newspaper layout
├── static_assets/            
│   ├── style.css             # Main stylesheet
│   ├── main.js               # Content loading and UI logic
│   ├── images/               # Logo, placeholders, branding
│   │   ├── CraicGPT_240h.png
│   │   ├── GeekwiththePeak.png
│   │   └── placeholder_*.png
│   └── vendor/               # Third-party libraries
│       └── js-datepicker/    # Date picker component
└── README.md                 # This file
```

## 🎨 Design Features

### **Newspaper Layout**
- **Header**: Branded banner with newspaper title
- **Main Content**: Grid-based layout with articles and sidebar
- **Content Sections**:
  - Main Article (with hero image)
  - Comparison Article (with hero image) 
  - Author Bio section
  - LLM Feature story
  - Daily joke section
  - Sponsored content (4 advertisement slots)

### **Multi-Provider Interface**
- **LLM Selection**: Radio buttons for all supported text models
  - AWS Bedrock: Claude Sonnet, Titan Express, Claude Haiku
  - OpenAI: GPT-4, O3 Mini
  - Anthropic Direct: Claude 3.5 Sonnet, Claude 3 Opus  
  - Google: Gemini Pro, Gemini Ultra

- **Image Selection**: Radio buttons for image generation models
  - AWS Bedrock: Titan Image, Nova Canvas
  - OpenAI: DALL-E 3

### **User Experience**
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Progressive Loading**: Content loads gracefully with placeholders
- **Date Navigation**: Easy browsing of historical content
- **Provider Selection**: Clear labeling of model providers
- **Error Handling**: Graceful fallbacks for missing content

## 🔧 Technical Implementation

### **Content Loading Process**
1. **Date Selection**: User picks date via date picker or URL parameter
2. **Model Selection**: User chooses preferred AI providers via radio buttons
3. **JSON Fetching**: JavaScript fetches `paper_content.json` from S3
4. **Content Rendering**: Dynamic insertion of AI-generated content
5. **Image Loading**: Progressive loading of AI-generated images

### **S3 Content Structure**
The frontend expects content in this S3 structure:
```
s3://bucket/static_assets/content/website/YYYY/MM/DD/
├── paper_content.json        # Main content file
├── llm_01_model-slug_256.txt # Raw text files
├── img_01_model-slug_512.png # Generated images
└── ...                       # Additional content files
```

### **JSON Content Format**
```json
{
  "publicationDate": "2025-01-15",
  "metadata": {
    "bannerTitle": "The Artificially Intelligent Times",
    "defaultLLM": "anthropic.claude-3-sonnet-20240229-v1:0",
    "defaultImageGen": "amazon.titan-image-generator-v1"
  },
  "contentSlots": {
    "mainArticle": {
      "llmOutputs": {
        "gpt-4": {"title": "...", "text": "..."},
        "claude-3-5-sonnet": {"title": "...", "text": "..."}
      },
      "imageOutputs": {
        "dall-e-3": {"imageUrl": "img_01_dall-e-3_512.png", "imageAlt": "..."}
      }
    }
  }
}
```

## 🚀 Deployment

### **Terraform Automation**
The frontend is fully automated via Terraform in [`../terraform/frontend/`](../terraform/frontend/):
- **S3 Bucket**: Static website hosting with public read access
- **CloudFront**: CDN distribution with custom domain
- **Route 53**: DNS configuration for custom domain
- **SSL Certificate**: ACM certificate for HTTPS
- **Asset Upload**: Automatic upload of all frontend files

### **Deployment Commands**
```bash
cd terraform/frontend
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your domain settings
terraform init
terraform plan
terraform apply
```

### **Manual Asset Upload**
If needed, assets can be manually uploaded:
```bash
aws s3 sync frontend/ s3://your-bucket-name/ \
  --exclude "README.md" \
  --cache-control "max-age=86400"
```

## 🔧 Development

### **Local Testing**
```bash
# Serve locally for development
cd frontend
python -m http.server 8000
# Visit http://localhost:8000
```

### **Content Testing**
To test with live content, you need:
1. Generated content in S3 (run backend pipeline)
2. Proper CORS configuration on S3 bucket
3. Valid date parameter in URL: `?date=2025-01-15`

### **Model Selection Testing**
- Test all provider radio buttons work correctly
- Verify model ID values match backend expectations
- Ensure proper fallback behavior for missing models

## 📊 Performance

### **Optimization Features**
- **CDN Caching**: CloudFront caches static assets globally
- **Image Optimization**: Progressive JPEG and PNG compression
- **Minification**: CSS and JS assets are minimized
- **Lazy Loading**: Images load progressively as needed
- **Caching Headers**: Appropriate cache control for different asset types

### **Performance Metrics**
- **First Contentful Paint**: < 2 seconds
- **Largest Contentful Paint**: < 3 seconds
- **Time to Interactive**: < 4 seconds
- **Cumulative Layout Shift**: < 0.1

## 🔐 Security

### **Content Security**
- **HTTPS Only**: All content served over encrypted connections
- **CORS Configuration**: Proper cross-origin resource sharing setup
- **Content Validation**: JavaScript validates content structure
- **XSS Prevention**: HTML content is properly escaped

### **Access Control**
- **S3 Bucket Policy**: Read-only public access for website content
- **CloudFront Security**: Security headers and origin access identity
- **Domain Security**: Proper DNS and certificate configuration

## 🐛 Troubleshooting

### **Common Issues**

**Content Not Loading**
- Check S3 bucket permissions and CORS configuration
- Verify content exists for the selected date
- Check browser console for JavaScript errors

**Images Not Displaying**
- Verify image files exist in S3 with correct naming
- Check image URLs in paper_content.json
- Ensure proper Content-Type headers

**Date Picker Issues**
- Verify date format (YYYY-MM-DD)
- Check URL parameter format
- Ensure date picker library is loaded

**Model Selection Not Working**
- Verify radio button values match backend model IDs
- Check JavaScript model selection logic
- Ensure proper form handling

### **Development Tools**
```bash
# Check S3 content
aws s3 ls s3://your-bucket/static_assets/content/website/2025/01/15/

# Test CORS configuration
curl -H "Origin: https://craicgpt.ie" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Content-Type" \
  -X OPTIONS \
  https://your-bucket.s3.amazonaws.com/

# Monitor CloudFront logs
aws logs filter-log-events \
  --log-group-name /aws/cloudfront/distribution-id
```

## 🤝 Contributing

### **Frontend Contributions Welcome**
- **UI/UX Improvements**: Enhanced newspaper design and user experience
- **Mobile Optimization**: Better responsive design for mobile devices
- **Accessibility**: WCAG compliance and screen reader support
- **Performance**: Further optimization of loading and rendering
- **Features**: Additional functionality like content sharing or printing

### **Development Guidelines**
- Follow semantic HTML structure
- Use CSS Grid and Flexbox for layouts
- Write vanilla JavaScript (no framework dependencies)
- Optimize images and assets for web delivery
- Test across multiple browsers and devices

**Static Website - Production Ready** 🌐