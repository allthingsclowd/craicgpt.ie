<p align="center">
  <img src="frontend/static_assets/images/CraicGPT_240h.png" alt="CraicGPT Logo" width="350"/>
  <img src="frontend/static_assets/images/GeekwiththePeak.png" alt="Geek with the Peak Logo" width="150"/>
</p>

# CraicGPT.ie - AI-Powered Digital Newspaper

**Learn AI in Code: From Basic LLM Calls to Advanced AI Agents**

A comprehensive educational project demonstrating practical AI integration, from simple API calls to sophisticated agent workflows. CraicGPT.ie generates a daily AI-powered newspaper while teaching developers how to work with Large Language Models (LLMs), image generation, and AI agent architectures.

## 📚 Project Vision & Learning Path

This repository serves as a **hands-on learning journey** through the evolving landscape of AI development:

### **Phase 1: Foundation - Basic LLM Integration** (Current)
- Direct API calls to LLM and image generation services
- Traditional embedded AI workflows
- RESTful API integration patterns
- Basic prompt engineering and response handling

### **Phase 2: Evolution - AI Agents** (Planned)
- Implementation of ReAct (Reasoning + Acting) agent patterns
- Tool-using AI with function calling
- Multi-step reasoning and decision making
- Agent-based content generation workflows

### **Phase 3: Future - Model Context Protocol (MCP)** (Planned) 
- MCP client and server implementations
- Standardized tool interfaces for AI agents
- Advanced inter-agent communication
- Production-ready agent architectures

---

## 🏗️ Architecture Overview

CraicGPT.ie is built as **two distinct applications** with different deployment strategies:

### **Frontend Application** ✅ **Production Ready**
- **Technology**: Static HTML/CSS/JavaScript newspaper layout
- **Hosting**: AWS S3 + CloudFront CDN with custom domain
- **Deployment**: Fully automated via Terraform (`terraform/frontend/`)
- **Features**: 
  - Model selection (LLM and Image Generation)
  - Date picker for historical content
  - Responsive newspaper layout
  - Real-time content updates

### **Backend Content Pipeline** ⚠️ **Manual Deployment** 
- **Technology**: 4 AWS Lambda functions in Python
- **Current State**: Manual deployment (Terraform boilerplate exists but unvalidated)
- **Architecture**: Event-driven serverless pipeline

---

## 🔧 Backend Lambda Architecture

The content generation pipeline consists of four specialized Lambda functions:

### **1. Prompt Generator** (`lambda_code/PromptGenerator/`)
- **Purpose**: Daily prompt generation for all content types
- **Trigger**: AWS EventBridge Scheduler (daily)
- **Output**: 13 prompts stored in S3
  - 5 LLM prompts (`llm_01` - `llm_05`)
  - 8 Image prompts (`img_01` - `img_08`)

### **2. Orchestrator** (`lambda_code/orchestrator/`)
- **Purpose**: Workflow coordination and dependency management
- **Trigger**: AWS EventBridge Scheduler (daily, after prompt generation)
- **Function**: 
  - Reads date range from environment variables
  - Invokes LLM and Image handlers sequentially
  - Manages model-specific rate limiting
  - Handles failures and retries with exponential backoff

### **3. LLM Handler** (`lambda_code/llmHandler/`)
- **Purpose**: Text content generation using various LLM providers
- **Models Supported**:
  - Anthropic Claude (Sonnet, Haiku)
  - Amazon Titan Text
  - Support for Cohere, AI21 (extensible)
- **Content Types**: Main articles, comparisons, stories, jokes, author bios

### **4. Image Generation Handler** (`lambda_code/imageGenHandler/`)
- **Purpose**: Visual content generation
- **Models Supported**:
  - Amazon Titan Image Generator
  - Amazon Nova Canvas
- **Content Types**: Article illustrations, advertisements, feature images

---

## 🚀 Current Status & Next Steps

### **✅ What's Working**
- Frontend website with full Terraform automation
- All 4 Lambda functions operational with manual deployment
- Daily content generation pipeline
- Multi-model support (LLM and Image)
- Rate limiting and error handling
- Rich logging and monitoring

### **🚧 Immediate Priorities**

1. **Backend Infrastructure Automation**
   - Validate and complete Terraform modules in `terraform/backend/`
   - IAM roles and policies for Lambda functions
   - EventBridge scheduler configuration
   - S3 bucket permissions and lifecycle policies

2. **CI/CD Pipeline Implementation**
   - GitHub Actions for security scanning
   - Automated testing and validation workflows
   - Multi-environment deployment (dev → prod)
   - Terraform best practices (remote state, locking)

3. **Production Hardening**
   - Comprehensive error handling and monitoring
   - Performance optimization and cost management
   - Security scanning and compliance
   - Documentation and runbooks

---

## 📁 Repository Structure

```
craicgpt.ie/
├── frontend/                    # Static website (Terraform ✅)
│   ├── index.html              # Main newspaper layout
│   ├── static_assets/          # CSS, JS, images
│   └── README.md               # Frontend documentation
├── lambda_code/                # Backend functions (Manual ⚠️)
│   ├── PromptGenerator/        # Daily prompt generation
│   ├── orchestrator/           # Workflow coordination
│   ├── llmHandler/             # LLM content generation  
│   └── imageGenHandler/        # Image generation
├── terraform/                  # Infrastructure as Code
│   ├── frontend/               # Website deployment (Working ✅)
│   └── backend/                # Lambda infrastructure (Boilerplate ⚠️)
├── prompts/                    # Base prompt templates
├── test_*.py                   # Test utilities and validation
└── README.md                   # This file
```

---

## 🛠️ Prerequisites & Setup

### **Required Tools**
- **Terraform** >= 1.8.0
- **AWS CLI** with configured credentials
- **Python** 3.11+ (for Lambda functions)
- **Node.js** (for frontend tooling, optional)

### **AWS Requirements**
- AWS account with appropriate IAM permissions
- Domain name registered (for custom domain)
- Route 53 hosted zone (for DNS management)

### **Quick Start - Frontend Deployment**

1. **Configure Variables**
   ```bash
   cd terraform/frontend
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your domain and settings
   ```

2. **Deploy Infrastructure**
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

3. **Upload Frontend Assets**
   ```bash
   # Assets are automatically uploaded during Terraform deployment
   ```

### **Manual Backend Deployment**
Currently requires manual Lambda function deployment through AWS Console or CLI. See individual function READMEs for deployment instructions.

---

## 🎯 Learning Objectives

### **Phase 1: LLM Integration Fundamentals**
- **API Integration**: REST calls to various LLM providers
- **Prompt Engineering**: Crafting effective prompts for different content types
- **Response Handling**: Parsing and processing LLM outputs
- **Error Resilience**: Timeout handling, retries, and fallbacks
- **Rate Limiting**: Managing API quotas and costs
- **Multi-Model Support**: Abstracting provider differences

### **Phase 2: AI Agent Development** (Coming Soon)
- **ReAct Pattern**: Reasoning and Acting in iterative loops
- **Tool Integration**: Function calling and external API usage
- **Decision Making**: Multi-step reasoning and planning
- **Memory Management**: Maintaining context across interactions
- **Agent Orchestration**: Coordinating multiple specialized agents

### **Phase 3: MCP Implementation** (Future)
- **Protocol Implementation**: MCP client and server development
- **Tool Standardization**: Universal tool interfaces
- **Agent Communication**: Inter-agent messaging and coordination
- **Production Deployment**: Scalable agent architectures

---

## 🤝 Contributing

We welcome contributions at all levels! Whether you're learning AI development or an experienced practitioner, there are opportunities to help:

### **Beginner-Friendly**
- Documentation improvements
- Frontend enhancements
- Test case development
- Bug reports and feature requests

### **Intermediate**
- Backend Terraform completion
- CI/CD pipeline implementation
- Performance optimizations
- Additional LLM provider integrations

### **Advanced**
- Agent architecture design (Phase 2)
- MCP implementation (Phase 3)
- Advanced monitoring and observability
- Security and compliance enhancements

---

## 📖 Educational Resources

### **Key Concepts Demonstrated**
- **Serverless Architecture**: AWS Lambda event-driven design
- **Infrastructure as Code**: Terraform best practices
- **API Design**: RESTful patterns and error handling
- **Content Generation**: Practical LLM and image model usage
- **Workflow Orchestration**: Dependency management and scheduling

### **Technologies Showcased**
- **AWS Services**: Lambda, S3, CloudFront, EventBridge, IAM
- **AI/ML Services**: Amazon Bedrock, Anthropic Claude, Titan models
- **Infrastructure**: Terraform, GitHub Actions (planned)
- **Frontend**: Modern JavaScript, CSS Grid, responsive design

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙋‍♂️ Support & Community

- **Issues**: Report bugs and request features via GitHub Issues
- **Discussions**: Join conversations about AI development patterns
- **Documentation**: Comprehensive guides for each phase of development

**Learn AI in Code - Start Your Journey Today!** 🚀
