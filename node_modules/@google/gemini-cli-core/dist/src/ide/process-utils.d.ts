/**
 * @license
 * Copyright 2025 Google LLC
 * SPDX-License-Identifier: Apache-2.0
 */
/**
 * Traverses up the process tree to find the process ID of the IDE.
 *
 * This function uses different strategies depending on the operating system
 * to identify the main application process (e.g., the main VS Code window
 * process).
 *
 * If the IDE process cannot be reliably identified, it will return the
 * top-level ancestor process ID as a fallback.
 *
 * @returns A promise that resolves to the numeric PID of the IDE process.
 * @throws Will throw an error if the underlying shell commands fail.
 */
export declare function getIdeProcessId(): Promise<number>;
