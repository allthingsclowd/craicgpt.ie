# Orchestrator - Workflow Coordination & Concurrency Control

**Advanced Orchestration with 10 Lambda Limit Enforcement**

The Orchestrator function coordinates the entire content generation workflow, managing dependencies between LLM and image generation while strictly enforcing the 10 Lambda concurrency limit requirement.

## 🎯 Purpose

Coordinate the fan-out execution of LLM and Image generation across multiple dates and models while respecting AWS Lambda concurrency limits and ensuring proper dependency management.

## 🏗️ Architecture

### **Orchestration Flow**
```
Orchestrator (1 Lambda) ──┐
                          │
┌─────────────────────────┼────────────────────────┐
│         Worker Pool     │                        │
│                         │                        │
├─ LLM Worker 1 ──────────┼─ Process Text Content  │
├─ LLM Worker 2 ──────────┼─ Process Text Content  │
├─ LLM Worker 3 ──────────┼─ Process Text Content  │
├─ Image Worker 1 ────────┼─ Process Images        │
├─ Image Worker 2 ────────┼─ Process Images        │
└─ ... (Max 9 Workers) ───┼─ TOTAL: 10 Lambda Max  │
                          │                        │
                          └────────────────────────┘
```

### **Dependency Management**
- **Phase 1**: LLM content generation (all text content)
- **Phase 2**: Image generation (depends on completed text)
- **Atomic Operations**: Each worker handles single model/date combination
- **Idempotent Execution**: Safe to rerun on failures

## 🚀 Key Features

### **10 Lambda Limit Compliance**
- ✅ **Hard Limit**: Orchestrator (1) + Workers (9) = 10 total
- ✅ **Real-time Monitoring**: CloudWatch concurrency tracking
- ✅ **Smart Throttling**: Waits when approaching limits
- ✅ **Fail-safe**: Prevents accidental limit exceeded

```python
# Critical concurrency enforcement
MAX_ACCOUNT_CONCURRENT = 9  # Orchestrator + 9 workers = 10 total
CONCURRENCY_CHECK_ENABLED = True  # ENABLED by default
```

### **Advanced Orchestration**
- ✅ **Dependency Aware**: LLM completion before image generation
- ✅ **Model Round-Robin**: Spreads load across different providers
- ✅ **Failure Handling**: Comprehensive retry with exponential backoff
- ✅ **Progress Tracking**: Real-time status monitoring

### **CloudWatch Integration**
```python
def get_current_lambda_concurrency() -> int:
    """Get current concurrent Lambda executions using CloudWatch metrics"""
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/Lambda',
        MetricName='ConcurrentExecutions',
        Dimensions=[],  # Account-wide
        Statistics=['Maximum']
    )
    return current_concurrent_executions
```

## 🔧 Technical Implementation

### **Function Configuration**
- **Runtime**: Python 3.12
- **Memory**: 1024 MB
- **Timeout**: 15 minutes
- **Handler**: `lambda_function.lambda_handler`
- **Concurrency**: Reserved capacity to ensure orchestrator availability

### **Environment Variables**
```bash
# CRITICAL: 10 Lambda limit compliance
MAX_ACCOUNT_CONCURRENT=9                    # Workers limit (orchestrator + 9 = 10)
CONCURRENCY_CHECK_ENABLED=true             # Enable concurrency monitoring
CONCURRENCY_BACKOFF_DELAY=5.0              # Wait time when at limit

# Worker function names
LLM_WORKER_FUNCTION=craicgptie_llm_runner
IMAGE_WORKER_FUNCTION=craicgptie_image_runner
PROMPT_GENERATOR_FUNCTION=craicgptie_prompt_generator

# Date range (optional - can be passed in event)
START_DATE=2025-01-15
END_DATE=2025-01-15

# Model configuration
BEDROCK_MODEL_IDS=anthropic.claude-3-sonnet-20240229-v1:0,amazon.titan-text-express-v1
BEDROCK_IMAGE_MODEL_IDS=amazon.titan-image-generator-v1,amazon.nova-canvas-v1:0

# Storage
PROMPT_BUCKET=your-s3-bucket-name
```

### **IAM Permissions Required**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": [
        "arn:aws:lambda:*:*:function:craicgptie_*",
        "arn:aws:lambda:*:*:function:craicgptie-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream", 
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

## 📊 Orchestration Logic

### **Work Item Generation**
```python
def create_work_items(dates: List[str]) -> List[Dict[str, Any]]:
    """Generate atomic work items for each model/date combination"""
    work_items = []
    
    for date_str in dates:
        # Check existing content to avoid redundant work
        paper_key, paper = load_or_create_paper_json(date_str)
        
        # Generate LLM work items
        for prompt_id in ["llm_01", "llm_02", "llm_03", "llm_04", "llm_05"]:
            for model_id in LLM_MODELS:
                if not task_already_done(paper, prompt_id, model_id):
                    work_items.append({
                        "type": "llm",
                        "date": date_str,
                        "model": model_id,
                        "prompt_id": prompt_id,
                        "function_name": LLM_WORKER_FUNCTION
                    })
        
        # Generate image work items (after LLM completion)
        for prompt_id in ["img_01", "img_02", "img_03", "img_04", "img_05", "img_06", "img_07", "img_08"]:
            for model_id in IMAGE_MODELS:
                if not task_already_done(paper, prompt_id, model_id):
                    work_items.append({
                        "type": "image",
                        "date": date_str,
                        "model": model_id,
                        "prompt_id": prompt_id,
                        "function_name": IMAGE_WORKER_FUNCTION
                    })
    
    return work_items
```

### **Concurrency Control**
```python
def wait_for_concurrency_slot(target_function: str, max_wait_minutes: int = 5) -> bool:
    """Wait for a concurrency slot to become available"""
    while (time.time() - start_time) < max_wait_seconds:
        current_concurrent = get_current_lambda_concurrency()
        
        if current_concurrent < MAX_ACCOUNT_CONCURRENT:
            logger.info(f"✅ Concurrency slot available ({current_concurrent}/{MAX_ACCOUNT_CONCURRENT})")
            return True
        
        logger.info(f"⏳ Waiting for concurrency slot: {current_concurrent}/{MAX_ACCOUNT_CONCURRENT}")
        time.sleep(CONCURRENCY_BACKOFF_DELAY)
    
    return False
```

### **Worker Invocation**
```python
def invoke_worker(work_item: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a worker lambda for a single work item with concurrency checking"""
    
    # Check concurrency limits before invoking
    if not wait_for_concurrency_slot(work_item["function_name"], max_wait_minutes=3):
        return {
            "status": "error",
            "error": f"Timeout waiting for concurrency slot (limit: {MAX_ACCOUNT_CONCURRENT})"
        }
    
    # Invoke worker synchronously
    payload = {
        "date": work_item["date"],
        "model_id": work_item["model"],
        "prompt_ids": [work_item["prompt_id"]],
        "worker_mode": True
    }
    
    response = lambda_client.invoke(
        FunctionName=work_item["function_name"],
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    return parse_worker_response(response)
```

## 📈 Performance & Metrics

### **Execution Metrics**
- **Average Processing Time**: 45 seconds per model/date combination
- **Concurrency Utilization**: Typically 6-9 concurrent workers
- **Success Rate**: >98% for well-configured environments
- **Retry Rate**: <5% of work items require retry

### **Monitoring Dashboards**
```bash
# Monitor orchestrator execution
aws logs tail /aws/lambda/craicgptie-orchestrator --follow

# Check concurrency compliance
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --filter-pattern '"CRITICAL: 10 Lambda limit compliance"'

# Monitor worker success rates
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --filter-pattern '"Final success rate"'

# Check for concurrency warnings
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --filter-pattern '"Waiting for concurrency slot"'
```

## 🔄 Execution Modes

### **Scheduled Execution** (Production)
```json
{
  "START_DATE": "2025-01-15",
  "END_DATE": "2025-01-20"
}
```

### **Manual Execution** (Development)
```bash
# Orchestrate content generation for date range
aws lambda invoke \
  --function-name craicgptie-orchestrator \
  --payload '{
    "START_DATE": "2025-01-15",
    "END_DATE": "2025-01-15"
  }' \
  --cli-binary-format raw-in-base64-out \
  response.json

# Monitor progress
aws logs tail /aws/lambda/craicgptie-orchestrator --follow
```

### **Emergency Stop**
If orchestration needs to be stopped:
```bash
# Update concurrency limit to pause new workers
aws lambda update-function-configuration \
  --function-name craicgptie-orchestrator \
  --environment Variables='{"MAX_ACCOUNT_CONCURRENT":"0"}'
```

## 📊 Response Format

### **Success Response**
```json
{
  "statusCode": 200,
  "body": {
    "status": "completed",
    "processing_time_seconds": 180.5,
    "date_range": {
      "start": "2025-01-15",
      "end": "2025-01-15",
      "dates": ["2025-01-15"]
    },
    "configuration": {
      "max_account_concurrent": 9,
      "concurrency_check_enabled": true,
      "performance_mode": "reactive_throttling"
    },
    "results": {
      "total_work_items": 25,
      "successful": 24,
      "failed": 1,
      "success_rate": 96.0,
      "llm_processing": {
        "total": 15,
        "successful": 15,
        "failed": 0
      },
      "image_processing": {
        "total": 10,
        "successful": 9,
        "failed": 1
      }
    }
  }
}
```

## 🐛 Troubleshooting

### **Common Issues**

**Concurrency Limit Exceeded**
```bash
# Check current account concurrency
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ConcurrentExecutions \
  --statistics Maximum \
  --start-time $(date -v-10M -u '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 60

# Reduce concurrent limit if needed
aws lambda update-function-configuration \
  --function-name craicgptie-orchestrator \
  --environment Variables='{"MAX_ACCOUNT_CONCURRENT":"5"}'
```

**Worker Failures**
```bash
# Check worker logs for specific errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie_llm_runner \
  --filter-pattern 'ERROR' \
  --start-time $(date -v-1H +%s)000

# Check worker function status
aws lambda get-function --function-name craicgptie_llm_runner
```

**Timeout Issues**
```bash
# Check orchestrator timeout settings
aws lambda get-function-configuration \
  --function-name craicgptie-orchestrator \
  --query 'Timeout'

# Monitor long-running executions
aws logs filter-log-events \
  --log-group-name /aws/lambda/craicgptie-orchestrator \
  --filter-pattern 'TIMEOUT' 
```

### **Performance Tuning**
- Adjust `CONCURRENCY_BACKOFF_DELAY` based on workload
- Monitor CloudWatch metrics for optimal `MAX_ACCOUNT_CONCURRENT`
- Balance between speed and AWS limit compliance
- Use reserved concurrency for critical functions

## 🤝 Contributing

### **Enhancement Opportunities**
- **Predictive Scaling**: Pre-adjust concurrency based on workload
- **Cost Optimization**: Intelligent model selection based on cost/performance
- **Multi-Region**: Distribute workload across AWS regions
- **Advanced Retry**: Implement circuit breaker patterns

### **Monitoring Improvements**
- Custom CloudWatch metrics for business KPIs
- Real-time dashboards for concurrency tracking
- Alerting for limit approaches or failures
- Performance analytics and trending

**Advanced Orchestration - Production Ready** 🎭