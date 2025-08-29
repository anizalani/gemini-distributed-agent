/**
 * @license
 * Copyright 2025 Google LLC
 * SPDX-License-Identifier: Apache-2.0
 */
import { ToolCallRequestInfo, ToolCallResponseInfo } from '../index.js';
import { Config } from '../config/config.js';
/**
 * Executes a single tool call non-interactively.
 * It does not handle confirmations, multiple calls, or live updates.
 */
export declare function executeToolCall(config: Config, toolCallRequest: ToolCallRequestInfo, abortSignal?: AbortSignal): Promise<ToolCallResponseInfo>;
