// /lambda_code/imageGenHandler/imageGenHandler.ts
import { SecretsManagerClient, GetSecretValueCommand } from "@aws-sdk/client-secrets-manager";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import fetch from 'node-fetch'; // Or import axios from 'axios';
import { v4 as uuidv4 } from 'uuid'; // For generating unique filenames

// Define expected event structure
interface ImageGenEvent {
    prompt: string;
    image_gen_provider?: string; // Optional: 'GEMINI', 'OPENAI_DALLE', etc.
    // Add other provider-specific params if needed, e.g., model_id, size, quality, n
    model_id?: string;
    size?: string; // e.g., "1024x1024"
    quality?: string; // e.g., "standard", "hd" for DALL-E 3
    response_format?: 'url' | 'b64_json'; // For DALL-E
}

interface ImageGenResponse {
    imageUrl?: string;
    error?: string;
}

const secretsManagerClient = new SecretsManagerClient({});
const s3Client = new S3Client({});

// Helper function to get secret value (can be shared with llmHandler if in the same package/layer)
async function getSecret(secretArn: string): Promise<string | undefined> {
    try {
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const data = await secretsManagerClient.send(command);
        if (data.SecretString) {
            return data.SecretString;
        }
        if (data.SecretBinary) {
            return Buffer.from(data.SecretBinary).toString('utf-8');
        }
        return undefined;
    } catch (error) {
        console.error(`Error retrieving secret ${secretArn}:`, error);
        throw new Error(`Failed to retrieve secret: ${secretArn}`);
    }
}

export const handler = async (event: ImageGenEvent): Promise<ImageGenResponse> => {
    console.log('Received event:', JSON.stringify(event, null, 2));

    const { prompt } = event;
    if (!prompt) {
        console.error('Prompt is missing from the event.');
        return { error: 'Prompt is required.' };
    }

    const imageGenApiKeySecretArn = process.env.IMAGEGEN_API_KEY_SECRET_ARN;
    const providerType = event.image_gen_provider |
| process.env.IMAGE_GEN_PROVIDER_TYPE |
| 'OPENAI_DALLE';
    const s3BucketName = process.env.S3_CONTENT_BUCKET_NAME;
    const cloudfrontDomain = process.env.CLOUDFRONT_DOMAIN_NAME; // e.g., d123abc.cloudfront.net

    // Provider-specific configurations
    const geminiImageModelId = event.model_id |
| process.env.GEMINI_IMAGE_MODEL_ID |
| 'gemini-2.0-flash-preview-image-generation'; // [51, 52]
    const openAIDalleModelId = event.model_id |
| process.env.OPENAI_DALLE_MODEL_ID |
| 'dall-e-3'; // [49]
    const imageSize = event.size |
| '1024x1024';
    const imageQuality = event.quality |
| 'standard'; // For DALL-E 3 [55]
    const responseFormat = event.response_format |
| 'url'; // Default to URL for DALL-E [54]

    if (!imageGenApiKeySecretArn) {
        console.error('IMAGEGEN_API_KEY_SECRET_ARN environment variable is not set.');
        return { error: 'ImageGen API key secret ARN is not configured.' };
    }
    if (!s3BucketName && (providerType.toUpperCase()!== 'OPENAI_DALLE' |
| responseFormat === 'b64_json')) {
        // S3 bucket is needed if we might receive binary data
        console.error('S3_CONTENT_BUCKET_NAME environment variable is not set for binary image upload.');
        return { error: 'S3 content bucket name is not configured.' };
    }
     if (!cloudfrontDomain && (providerType.toUpperCase()!== 'OPENAI_DALLE' |
| responseFormat === 'b64_json')) {
        console.error('CLOUDFRONT_DOMAIN_NAME environment variable is not set for constructing image URL.');
        return { error: 'CloudFront domain name is not configured.' };
    }


    try {
        const secretValueString = await getSecret(imageGenApiKeySecretArn);
         if (!secretValueString) {
            return { error: 'ImageGen API key not found in Secrets Manager.' };
        }
        
        const apiKeyObject = JSON.parse(secretValueString);
        const apiKey = apiKeyObject.apiKey;

        if (!apiKey) {
            return { error: 'API key field not found in the retrieved secret.' };
        }

        let imageUrl: string | undefined;
        console.log(`Using ImageGen provider: ${providerType}`);

        if (providerType.toUpperCase() === 'GEMINI') {
            // Gemini image generation - typically returns base64 inline data [52]
            const geminiApiEndpoint = process.env.GEMINI_API_ENDPOINT_IMAGE |
| `https://generativelanguage.googleapis.com/v1beta/models/${geminiImageModelId}:generateContent?key=${apiKey}`;
            const geminiPayload = {
                contents: [{ parts: [{ text: prompt }] }],
                generationConfig: { // Gemini might have specific config for images
                     responseMimeType: "image/png", // Or other supported types
                },
                // For Gemini image generation, you might need to specify responseModalities [52]
                // This example assumes a direct image generation endpoint or a multimodal one configured for image output
            };
             if (geminiImageModelId.includes("flash-preview-image-generation")) { // Specific for this model [52]
                (geminiPayload as any).config = { responseModalities: ["IMAGE"] }; // Or
            }

            console.log('Sending request to Gemini Image API:', geminiApiEndpoint);
            const apiResponse = await fetch(geminiApiEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(geminiPayload),
            });

            if (!apiResponse.ok) {
                const errorBody = await apiResponse.text();
                console.error(`Gemini Image API error: ${apiResponse.status} ${apiResponse.statusText}`, errorBody);
                throw new Error(`Gemini Image API request failed: ${apiResponse.statusText} - ${errorBody}`);
            }
            const responseData: any = await apiResponse.json();
            // Parse Gemini response for inline image data (base64) [52]
            const base64ImageData = responseData?.candidates?.?.content?.parts?.?.inlineData?.data;

            if (base64ImageData && s3BucketName && cloudfrontDomain) {
                const imageBuffer = Buffer.from(base64ImageData, 'base64');
                const today = new Date();
                const s3Key = `content/images/${today.getFullYear()}/${String(today.getMonth() + 1).padStart(2, '0')}/${String(today.getDate()).padStart(2, '0')}/${uuidv4()}.png`;
                
                await s3Client.send(new PutObjectCommand({
                    Bucket: s3BucketName,
                    Key: s3Key,
                    Body: imageBuffer,
                    ContentType: 'image/png', // Adjust if different mimeType is returned
                }));
                imageUrl = `https://${cloudfrontDomain}/${s3Key}`;
                console.log(`Image uploaded to S3: ${imageUrl}`);
            } else if (base64ImageData && (!s3BucketName ||!cloudfrontDomain)) {
                 console.error('S3 bucket name or CloudFront domain not configured for Gemini binary image upload.');
                 return { error: 'S3/CloudFront configuration missing for Gemini image upload.' };
            } else {
                console.error('No image data found in Gemini response or S3 config missing.', responseData);
                return { error: 'Failed to extract image data from Gemini response.' };
            }

        } else if (providerType.toUpperCase() === 'OPENAI_DALLE') {
            const openAiApiEndpoint = process.env.OPENAI_DALLE_API_ENDPOINT |
| 'https://api.openai.com/v1/images/generations';
            const openAiPayload: any = {
                model: openAIDalleModelId,
                prompt: prompt,
                n: 1,
                size: imageSize,
                response_format: responseFormat, // 'url' or 'b64_json' [54]
            };
            if (openAIDalleModelId === 'dall-e-3') {
                openAiPayload.quality = imageQuality; // 'standard' or 'hd' [55]
            }

            console.log('Sending request to OpenAI DALL-E API:', openAiApiEndpoint);
            const apiResponse = await fetch(openAiApiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`,
                },
                body: JSON.stringify(openAiPayload),
            });

            if (!apiResponse.ok) {
                const errorBody = await apiResponse.text();
                console.error(`OpenAI DALL-E API error: ${apiResponse.status} ${apiResponse.statusText}`, errorBody);
                throw new Error(`OpenAI DALL-E API request failed: ${apiResponse.statusText} - ${errorBody}`);
            }
            const responseData: any = await apiResponse.json();

            if (responseFormat === 'url') {
                imageUrl = responseData?.data?.?.url;
            } else if (responseFormat === 'b64_json' && s3BucketName && cloudfrontDomain) {
                const base64ImageData = responseData?.data?.?.b64_json;
                if (base64ImageData) {
                    const imageBuffer = Buffer.from(base64ImageData, 'base64');
                    const today = new Date();
                    const s3Key = `content/images/${today.getFullYear()}/${String(today.getMonth() + 1).padStart(2, '0')}/${String(today.getDate()).padStart(2, '0')}/${uuidv4()}.png`;
                    
                    await s3Client.send(new PutObjectCommand({
                        Bucket: s3BucketName,
                        Key: s3Key,
                        Body: imageBuffer,
                        ContentType: 'image/png',
                    }));
                    imageUrl = `https://${cloudfrontDomain}/${s3Key}`;
                    console.log(`Image uploaded to S3: ${imageUrl}`);
                }  else {
                     console.error('No b64_json image data found in OpenAI response.');
                     return { error: 'Failed to extract b64_json image data from OpenAI response.' };
                }
            } else if (responseFormat === 'b64_json' && (!s3BucketName ||!cloudfrontDomain)) {
                 console.error('S3 bucket name or CloudFront domain not configured for DALL-E b64_json image upload.');
                 return { error: 'S3/CloudFront configuration missing for DALL-E b64_json image upload.' };
            } else {
                 console.error('Unsupported response format or missing data from OpenAI.', responseData);
                 return { error: 'Failed to process image from OpenAI response.' };
            }
        } else {
            console.error(`Unsupported ImageGen provider: ${providerType}`);
            return { error: `Unsupported ImageGen provider: ${providerType}` };
        }

        if (!imageUrl) {
            console.error('No image URL could be determined or generated.');
            return { error: 'Failed to obtain image URL.' };
        }

        console.log(`Successfully obtained image URL: ${imageUrl}`);
        return { imageUrl };

    } catch (error: any) {
        console.error('Error in ImageGen handler:', error);
        return { error: error.message |
| 'An unexpected error occurred in ImageGen handler.' };
    }
};