/**
 * @license
 * Copyright 2025 Google LLC
 * SPDX-License-Identifier: Apache-2.0
 */
import { Config } from '@google/gemini-cli-core';
import { LoadedSettings } from '../config/settings.js';
import { Extension } from '../config/extension.js';
import { CliArgs } from '../config/config.js';
export declare function runZedIntegration(config: Config, settings: LoadedSettings, extensions: Extension[], argv: CliArgs): Promise<void>;
