import type { Locator, ElementHandle } from 'playwright-core';
import type { ICDPSession } from './cdp-session.js';
export interface ReactSourceLocation {
    fileName: string | null;
    lineNumber: number | null;
    columnNumber: number | null;
    componentName: string | null;
}
export declare function getReactSource({ locator, cdp: cdpSession, }: {
    locator: Locator | ElementHandle;
    cdp: ICDPSession;
}): Promise<ReactSourceLocation | null>;
//# sourceMappingURL=react-source.d.ts.map