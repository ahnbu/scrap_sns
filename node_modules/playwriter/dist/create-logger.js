import fs from 'node:fs';
import path from 'node:path';
import util from 'node:util';
import stripAnsi from 'strip-ansi';
import { LOG_FILE_PATH } from './utils.js';
export function createFileLogger({ logFilePath } = {}) {
    const resolvedLogFilePath = logFilePath || LOG_FILE_PATH;
    const logDir = path.dirname(resolvedLogFilePath);
    if (!fs.existsSync(logDir)) {
        fs.mkdirSync(logDir, { recursive: true });
    }
    fs.writeFileSync(resolvedLogFilePath, '');
    let queue = Promise.resolve();
    const log = (...args) => {
        const message = args.map(arg => typeof arg === 'string' ? arg : util.inspect(arg, { depth: null, colors: false })).join(' ');
        queue = queue.then(() => fs.promises.appendFile(resolvedLogFilePath, stripAnsi(message) + '\n'));
        return queue;
    };
    return {
        log,
        error: log,
        logFilePath: resolvedLogFilePath,
    };
}
//# sourceMappingURL=create-logger.js.map