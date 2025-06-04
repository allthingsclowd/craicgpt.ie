// /lambda_code/llmHandler/llmHandler.ts
import { SecretsManagerClient, GetSecretValueCommand } from "@aws-sdk/client-secrets-manager";
import fetch from 'node-fetch'; // Or import axios from 'axios';

// Define expected event structure
interface LLMEvent {
    prompt: string;
    llm_provider?: string; // Optional: 'GEMINI', 'OPENAI_CHATGPT', etc.
    // Add other provider-specific params if needed, e.g., model_id, temperature
    model_id?: string;
    temperature?: number;
    max_tokens?: number;
}

interface LLMResponse {
    generatedText?: string;
    error?: string;
}

const secretsManagerClient = new SecretsManagerClient({});

// Helper function to get secret value
async function getSecret(secretArn: string): Promise<string | undefined> {
    try {
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const data = await secretsManagerClient.send(command);
        if (data.SecretString) {
            return data.SecretString;
        }
        if (data.SecretBinary) {
            // If SecretBinary is used, it needs to be decoded (e.g., base64)
            return Buffer.from(data.SecretBinary).toString('utf-8');
        }
        return undefined;
    } catch (error) {
        console.error(`Error retrieving secret ${secretArn}:`, error);
        throw new Error(`Failed to retrieve secret: ${secretArn}`);
    }
}

export const handler = async (event: LLMEvent): Promise<LLMResponse> => {
    console.log('Received event:', JSON.stringify(event, null, 2));

    const { prompt } = event;
    if (!prompt) {
        console.error('Prompt is missing from the event.');
        return { error: 'Prompt is required.' };
    }

    const llmApiKeySecretArn = process.env.LLM_API_KEY_SECRET_ARN;
    const providerType = event.llm_provider |
| process.env.LLM_PROVIDER_TYPE |
| 'OPENAI_CHATGPT'; // Default provider
    
    // Provider-specific configurations (could also come from env vars or a config file)
    const geminiModelId = event.model_id |
| process.env.GEMINI_MODEL_ID |
| 'gemini-pro'; // [42]
    const openAIModelId = event.model_id |
| process.env.OPENAI_MODEL_ID |
| 'gpt-4o'; // Example model

    if (!llmApiKeySecretArn) {
        console.error('LLM_API_KEY_SECRET_ARN environment variable is not set.');
        return { error: 'LLM API key secret ARN is not configured.' };
    }

    try {
        const secretValueString = await getSecret(llmApiKeySecretArn);
        if (!secretValueString) {
            return { error: 'LLM API key not found in Secrets Manager.' };
        }
        
        const apiKeyObject = JSON.parse(secretValueString); // Assuming secret is stored as JSON: {"apiKey": "value"}
        const apiKey = apiKeyObject.apiKey;

        if (!apiKey) {
            return { error: 'API key field not found in the retrieved secret.' };
        }

        let llmApiResponse;
        let generatedText: string | undefined;

        console.log(`Using LLM provider: ${providerType}`);

        if (providerType.toUpperCase() === 'GEMINI') {
            const geminiApiEndpoint = process.env.GEMINI_API_ENDPOINT |
| `https://generativelanguage.googleapis.com/v1beta/models/${geminiModelId}:generateContent?key=${apiKey}`;
            const geminiPayload = {
                contents: [{ parts: [{ text: prompt }] }],
                // generationConfig: { // Optional: add temperature, maxOutputTokens etc.
                //   temperature: event.temperature |
| 0.7,
                //   maxOutputTokens: event.max_tokens |
| 1024,
                // }
            };
            console.log('Sending request to Gemini API:', geminiApiEndpoint);
            llmApiResponse = await fetch(geminiApiEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(geminiPayload),
            });
            if (!llmApiResponse.ok) {
                const errorBody = await llmApiResponse.text();
                console.error(`Gemini API error: ${llmApiResponse.status} ${llmApiResponse.statusText}`, errorBody);
                throw new Error(`Gemini API request failed: ${llmApiResponse.statusText} - ${errorBody}`);
            }
            const geminiData: any = await llmApiResponse.json();
            // Adjust parsing based on actual Gemini API response structure [42, 43]
            generatedText = geminiData?.candidates?.?.content?.parts?.?.text;

        } else if (providerType.toUpperCase() === 'OPENAI_CHATGPT') {
            const openAiApiEndpoint = process.env.OPENAI_API_ENDPOINT |
| 'https://api.openai.com/v1/chat/completions';
            const openAiPayload = {
                model: openAIModelId,
                messages: [{ role: 'user', content: prompt }],
                // temperature: event.temperature |
| 0.7,
                // max_tokens: event.max_tokens |
| 1024,
            };
            console.log('Sending request to OpenAI API:', openAiApiEndpoint);
            llmApiResponse = await fetch(openAiApiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`,
                },
                body: JSON.stringify(openAiPayload),
            });
            if (!llmApiResponse.ok) {
                const errorBody = await llmApiResponse.text();
                console.error(`OpenAI API error: ${llmApiResponse.status} ${llmApiResponse.statusText}`, errorBody);
                throw new Error(`OpenAI API request failed: ${llmApiResponse.statusText} - ${errorBody}`);
            }
            const openAiData: any = await llmApiResponse.json();
            // Adjust parsing based on actual OpenAI API response structure [44, 45]
            generatedText = openAiData?.choices?.?.message?.content;
        } else {
            console.error(`Unsupported LLM provider: ${providerType}`);
            return { error: `Unsupported LLM provider: ${providerType}` };
        }

        if (!generatedText) {
            console.error('No generated text found in LLM response.');
            return { error: 'Failed to extract generated text from LLM response.' };
        }

        console.log('Successfully generated text from LLM.');
        return { generatedText };

    } catch (error: any) {
        console.error('Error in LLM handler:', error);
        return { error: error.message |
| 'An unexpected error occurred in LLM handler.' };
    }
};