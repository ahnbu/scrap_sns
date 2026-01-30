import type { Page } from 'playwright-core';
export interface WaitForPageLoadOptions {
    page: Page;
    timeout?: number;
    pollInterval?: number;
    minWait?: number;
}
export interface WaitForPageLoadResult {
    success: boolean;
    readyState: string;
    pendingRequests: string[];
    waitTimeMs: number;
    timedOut: boolean;
}
export declare function waitForPageLoad(options: WaitForPageLoadOptions): Promise<WaitForPageLoadResult>;
//# sourceMappingURL=wait-for-page-load.d.ts.map