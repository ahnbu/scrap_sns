import { Page, Locator } from 'playwright-core';
export interface GetCleanHTMLOptions {
    locator: Locator | Page;
    search?: string | RegExp;
    showDiffSinceLastCall?: boolean;
    includeStyles?: boolean;
    maxAttrLen?: number;
    maxContentLen?: number;
}
export declare function getCleanHTML(options: GetCleanHTMLOptions): Promise<string>;
//# sourceMappingURL=clean-html.d.ts.map