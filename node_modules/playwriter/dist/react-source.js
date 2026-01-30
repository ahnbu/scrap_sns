import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
let bippyCode = null;
function getBippyCode() {
    if (bippyCode) {
        return bippyCode;
    }
    const currentDir = path.dirname(fileURLToPath(import.meta.url));
    const bippyPath = path.join(currentDir, '..', 'dist', 'bippy.js');
    bippyCode = fs.readFileSync(bippyPath, 'utf-8');
    return bippyCode;
}
export async function getReactSource({ locator, cdp: cdpSession, }) {
    // Cast to CDPSession for internal type safety - at runtime both are compatible
    const cdp = cdpSession;
    const page = 'page' in locator && typeof locator.page === 'function' ? locator.page() : locator._page;
    if (!page) {
        throw new Error('Could not get page from locator');
    }
    const hasBippy = await page.evaluate(() => !!globalThis.__bippy);
    if (!hasBippy) {
        const code = getBippyCode();
        await cdp.send('Runtime.evaluate', { expression: code });
    }
    const result = await locator.evaluate(async (el) => {
        const bippy = globalThis.__bippy;
        if (!bippy) {
            throw new Error('bippy not loaded');
        }
        const fiber = bippy.getFiberFromHostInstance(el);
        if (!fiber) {
            return { _notFound: 'fiber' };
        }
        const source = await bippy.getSource(fiber);
        if (source) {
            return {
                fileName: source.fileName ? bippy.normalizeFileName(source.fileName) : null,
                lineNumber: source.lineNumber ?? null,
                columnNumber: source.columnNumber ?? null,
                componentName: source.functionName ?? bippy.getDisplayName(fiber.type) ?? null,
            };
        }
        const ownerStack = await bippy.getOwnerStack(fiber);
        for (const frame of ownerStack) {
            if (frame.fileName && bippy.isSourceFile(frame.fileName)) {
                return {
                    fileName: bippy.normalizeFileName(frame.fileName),
                    lineNumber: frame.lineNumber ?? null,
                    columnNumber: frame.columnNumber ?? null,
                    componentName: frame.functionName ?? null,
                };
            }
        }
        return { _notFound: 'source' };
    });
    if (result && '_notFound' in result) {
        if (result._notFound === 'fiber') {
            console.warn('[getReactSource] no fiber found - is this a React element?');
        }
        else {
            console.warn('[getReactSource] no source location found - is this a React dev build?');
        }
        return null;
    }
    return result;
}
//# sourceMappingURL=react-source.js.map