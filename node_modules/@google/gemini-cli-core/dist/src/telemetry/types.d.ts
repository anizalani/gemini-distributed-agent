/**
 * @license
 * Copyright 2025 Google LLC
 * SPDX-License-Identifier: Apache-2.0
 */
import { GenerateContentResponseUsageMetadata } from '@google/genai';
import { Config } from '../config/config.js';
import { CompletedToolCall } from '../core/coreToolScheduler.js';
import { ToolCallDecision } from './tool-call-decision.js';
export interface BaseTelemetryEvent {
    'event.name': string;
    /** Current timestamp in ISO 8601 format */
    'event.timestamp': string;
}
type CommonFields = keyof BaseTelemetryEvent;
export declare class StartSessionEvent implements BaseTelemetryEvent {
    'event.name': 'cli_config';
    'event.timestamp': string;
    model: string;
    embedding_model: string;
    sandbox_enabled: boolean;
    core_tools_enabled: string;
    approval_mode: string;
    api_key_enabled: boolean;
    vertex_ai_enabled: boolean;
    debug_enabled: boolean;
    mcp_servers: string;
    telemetry_enabled: boolean;
    telemetry_log_user_prompts_enabled: boolean;
    file_filtering_respect_git_ignore: boolean;
    constructor(config: Config);
}
export declare class EndSessionEvent implements BaseTelemetryEvent {
    'event.name': 'end_session';
    'event.timestamp': string;
    session_id?: string;
    constructor(config?: Config);
}
export declare class UserPromptEvent implements BaseTelemetryEvent {
    'event.name': 'user_prompt';
    'event.timestamp': string;
    prompt_length: number;
    prompt_id: string;
    auth_type?: string;
    prompt?: string;
    constructor(prompt_length: number, prompt_Id: string, auth_type?: string, prompt?: string);
}
export declare class ToolCallEvent implements BaseTelemetryEvent {
    'event.name': 'tool_call';
    'event.timestamp': string;
    function_name: string;
    function_args: Record<string, unknown>;
    duration_ms: number;
    success: boolean;
    decision?: ToolCallDecision;
    error?: string;
    error_type?: string;
    prompt_id: string;
    tool_type: 'native' | 'mcp';
    metadata?: {
        [key: string]: any;
    };
    constructor(call: CompletedToolCall);
}
export declare class ApiRequestEvent implements BaseTelemetryEvent {
    'event.name': 'api_request';
    'event.timestamp': string;
    model: string;
    prompt_id: string;
    request_text?: string;
    constructor(model: string, prompt_id: string, request_text?: string);
}
export declare class ApiErrorEvent implements BaseTelemetryEvent {
    'event.name': 'api_error';
    'event.timestamp': string;
    model: string;
    error: string;
    error_type?: string;
    status_code?: number | string;
    duration_ms: number;
    prompt_id: string;
    auth_type?: string;
    constructor(model: string, error: string, duration_ms: number, prompt_id: string, auth_type?: string, error_type?: string, status_code?: number | string);
}
export declare class ApiResponseEvent implements BaseTelemetryEvent {
    'event.name': 'api_response';
    'event.timestamp': string;
    model: string;
    status_code?: number | string;
    duration_ms: number;
    error?: string;
    input_token_count: number;
    output_token_count: number;
    cached_content_token_count: number;
    thoughts_token_count: number;
    tool_token_count: number;
    total_token_count: number;
    response_text?: string;
    prompt_id: string;
    auth_type?: string;
    constructor(model: string, duration_ms: number, prompt_id: string, auth_type?: string, usage_data?: GenerateContentResponseUsageMetadata, response_text?: string, error?: string);
}
export declare class FlashFallbackEvent implements BaseTelemetryEvent {
    'event.name': 'flash_fallback';
    'event.timestamp': string;
    auth_type: string;
    constructor(auth_type: string);
}
export declare enum LoopType {
    CONSECUTIVE_IDENTICAL_TOOL_CALLS = "consecutive_identical_tool_calls",
    CHANTING_IDENTICAL_SENTENCES = "chanting_identical_sentences",
    LLM_DETECTED_LOOP = "llm_detected_loop"
}
export declare class LoopDetectedEvent implements BaseTelemetryEvent {
    'event.name': 'loop_detected';
    'event.timestamp': string;
    loop_type: LoopType;
    prompt_id: string;
    constructor(loop_type: LoopType, prompt_id: string);
}
export declare class NextSpeakerCheckEvent implements BaseTelemetryEvent {
    'event.name': 'next_speaker_check';
    'event.timestamp': string;
    prompt_id: string;
    finish_reason: string;
    result: string;
    constructor(prompt_id: string, finish_reason: string, result: string);
}
export interface SlashCommandEvent extends BaseTelemetryEvent {
    'event.name': 'slash_command';
    'event.timestamp': string;
    command: string;
    subcommand?: string;
    status?: SlashCommandStatus;
}
export declare function makeSlashCommandEvent({ command, subcommand, status, }: Omit<SlashCommandEvent, CommonFields>): SlashCommandEvent;
export declare enum SlashCommandStatus {
    SUCCESS = "success",
    ERROR = "error"
}
export interface ChatCompressionEvent extends BaseTelemetryEvent {
    'event.name': 'chat_compression';
    'event.timestamp': string;
    tokens_before: number;
    tokens_after: number;
}
export declare function makeChatCompressionEvent({ tokens_before, tokens_after, }: Omit<ChatCompressionEvent, CommonFields>): ChatCompressionEvent;
export declare class MalformedJsonResponseEvent implements BaseTelemetryEvent {
    'event.name': 'malformed_json_response';
    'event.timestamp': string;
    model: string;
    constructor(model: string);
}
export declare enum IdeConnectionType {
    START = "start",
    SESSION = "session"
}
export declare class IdeConnectionEvent {
    'event.name': 'ide_connection';
    'event.timestamp': string;
    connection_type: IdeConnectionType;
    constructor(connection_type: IdeConnectionType);
}
export declare class KittySequenceOverflowEvent {
    'event.name': 'kitty_sequence_overflow';
    'event.timestamp': string;
    sequence_length: number;
    truncated_sequence: string;
    constructor(sequence_length: number, truncated_sequence: string);
}
export type TelemetryEvent = StartSessionEvent | EndSessionEvent | UserPromptEvent | ToolCallEvent | ApiRequestEvent | ApiErrorEvent | ApiResponseEvent | FlashFallbackEvent | LoopDetectedEvent | NextSpeakerCheckEvent | KittySequenceOverflowEvent | MalformedJsonResponseEvent | IdeConnectionEvent | SlashCommandEvent;
export {};
