import type { ICDPSession } from './cdp-session.js';
import type { Locator } from 'playwright-core';
export interface StyleSource {
    url: string;
    line: number;
    column: number;
}
export type StyleDeclarations = Record<string, string>;
export interface StyleRule {
    selector: string;
    source: StyleSource | null;
    origin: 'regular' | 'user-agent' | 'injected' | 'inspector';
    declarations: StyleDeclarations;
    inheritedFrom: string | null;
}
export interface StylesResult {
    element: string;
    inlineStyle: StyleDeclarations | null;
    rules: StyleRule[];
}
export declare function getStylesForLocator({ locator, cdp: cdpSession, includeUserAgentStyles, }: {
    locator: Locator;
    cdp: ICDPSession;
    includeUserAgentStyles?: boolean;
}): Promise<StylesResult>;
export declare function formatStylesAsText(styles: StylesResult): string;
//# sourceMappingURL=styles.d.ts.map