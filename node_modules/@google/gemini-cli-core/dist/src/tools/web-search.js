/**
 * @license
 * Copyright 2025 Google LLC
 * SPDX-License-Identifier: Apache-2.0
 */
import { BaseDeclarativeTool, BaseToolInvocation, Kind, } from './tools.js';
import { getErrorMessage } from '../utils/errors.js';
import { getResponseText } from '../utils/generateContentResponseUtilities.js';
class WebSearchToolInvocation extends BaseToolInvocation {
    config;
    constructor(config, params) {
        super(params);
        this.config = config;
    }
    getDescription() {
        return `Searching the web for: "${this.params.query}"`;
    }
    async execute(signal) {
        const geminiClient = this.config.getGeminiClient();
        try {
            const response = await geminiClient.generateContent([{ role: 'user', parts: [{ text: this.params.query }] }], { tools: [{ googleSearch: {} }] }, signal);
            const responseText = getResponseText(response);
            const groundingMetadata = response.candidates?.[0]?.groundingMetadata;
            const sources = groundingMetadata?.groundingChunks;
            const groundingSupports = groundingMetadata?.groundingSupports;
            if (!responseText || !responseText.trim()) {
                return {
                    llmContent: `No search results or information found for query: "${this.params.query}"`,
                    returnDisplay: 'No information found.',
                };
            }
            let modifiedResponseText = responseText;
            const sourceListFormatted = [];
            if (sources && sources.length > 0) {
                sources.forEach((source, index) => {
                    const title = source.web?.title || 'Untitled';
                    const uri = source.web?.uri || 'No URI';
                    sourceListFormatted.push(`[${index + 1}] ${title} (${uri})`);
                });
                if (groundingSupports && groundingSupports.length > 0) {
                    const insertions = [];
                    groundingSupports.forEach((support) => {
                        if (support.segment && support.groundingChunkIndices) {
                            const citationMarker = support.groundingChunkIndices
                                .map((chunkIndex) => `[${chunkIndex + 1}]`)
                                .join('');
                            insertions.push({
                                index: support.segment.endIndex,
                                marker: citationMarker,
                            });
                        }
                    });
                    // Sort insertions by index in descending order to avoid shifting subsequent indices
                    insertions.sort((a, b) => b.index - a.index);
                    const responseChars = modifiedResponseText.split(''); // Use new variable
                    insertions.forEach((insertion) => {
                        responseChars.splice(insertion.index, 0, insertion.marker);
                    });
                    modifiedResponseText = responseChars.join(''); // Assign back to modifiedResponseText
                }
                if (sourceListFormatted.length > 0) {
                    modifiedResponseText +=
                        '\n\nSources:\n' + sourceListFormatted.join('\n');
                }
            }
            return {
                llmContent: `Web search results for "${this.params.query}":\n\n${modifiedResponseText}`,
                returnDisplay: `Search results for "${this.params.query}" returned.`,
                sources,
            };
        }
        catch (error) {
            const errorMessage = `Error during web search for query "${this.params.query}": ${getErrorMessage(error)}`;
            console.error(errorMessage, error);
            return {
                llmContent: `Error: ${errorMessage}`,
                returnDisplay: `Error performing web search.`,
            };
        }
    }
}
/**
 * A tool to perform web searches using Google Search via the Gemini API.
 */
export class WebSearchTool extends BaseDeclarativeTool {
    config;
    static Name = 'google_web_search';
    constructor(config) {
        super(WebSearchTool.Name, 'GoogleSearch', 'Performs a web search using Google Search (via the Gemini API) and returns the results. This tool is useful for finding information on the internet based on a query.', Kind.Search, {
            type: 'object',
            properties: {
                query: {
                    type: 'string',
                    description: 'The search query to find information on the web.',
                },
            },
            required: ['query'],
        });
        this.config = config;
    }
    /**
     * Validates the parameters for the WebSearchTool.
     * @param params The parameters to validate
     * @returns An error message string if validation fails, null if valid
     */
    validateToolParamValues(params) {
        if (!params.query || params.query.trim() === '') {
            return "The 'query' parameter cannot be empty.";
        }
        return null;
    }
    createInvocation(params) {
        return new WebSearchToolInvocation(this.config, params);
    }
}
//# sourceMappingURL=web-search.js.map