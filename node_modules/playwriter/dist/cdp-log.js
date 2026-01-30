import fs from 'node:fs';
import path from 'node:path';
import { LOG_CDP_FILE_PATH } from './utils.js';
const DEFAULT_MAX_STRING_LENGTH = Number(process.env.PLAYWRITER_CDP_LOG_MAX_STRING_LENGTH || 2000);
function truncateString(value, maxLength) {
    if (value.length <= maxLength) {
        return value;
    }
    const truncatedCount = value.length - maxLength;
    return `${value.slice(0, maxLength)}…[truncated ${truncatedCount} chars]`;
}
function createTruncatingReplacer({ maxStringLength }) {
    const seen = new WeakSet();
    return (_key, value) => {
        if (typeof value === 'string') {
            return truncateString(value, maxStringLength);
        }
        if (typeof value === 'object' && value !== null) {
            if (seen.has(value)) {
                return '[Circular]';
            }
            seen.add(value);
        }
        return value;
    };
}
export function createCdpLogger({ logFilePath, maxStringLength } = {}) {
    const resolvedLogFilePath = logFilePath || LOG_CDP_FILE_PATH;
    const logDir = path.dirname(resolvedLogFilePath);
    if (!fs.existsSync(logDir)) {
        fs.mkdirSync(logDir, { recursive: true });
    }
    fs.writeFileSync(resolvedLogFilePath, '');
    let queue = Promise.resolve();
    const maxLength = maxStringLength ?? DEFAULT_MAX_STRING_LENGTH;
    const log = (entry) => {
        const replacer = createTruncatingReplacer({ maxStringLength: maxLength });
        const line = JSON.stringify(entry, replacer);
        queue = queue.then(() => fs.promises.appendFile(resolvedLogFilePath, `${line}\n`));
    };
    return {
        log,
        logFilePath: resolvedLogFilePath,
    };
}
//# sourceMappingURL=cdp-log.js.map