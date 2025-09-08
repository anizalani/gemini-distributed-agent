/**
 * @license
 * Copyright 2025 Google LLC
 * SPDX-License-Identifier: Apache-2.0
 */
import { SandboxConfig } from '@google/gemini-cli-core';
import { Settings } from './settings.js';
interface SandboxCliArgs {
    sandbox?: boolean | string;
    sandboxImage?: string;
}
export declare function loadSandboxConfig(settings: Settings, argv: SandboxCliArgs): Promise<SandboxConfig | undefined>;
export {};
