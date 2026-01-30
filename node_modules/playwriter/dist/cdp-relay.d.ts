import type { RelayServerEvents } from './cdp-types.js';
import { type CdpLogger } from './cdp-log.js';
export type RelayServer = {
    close(): void;
    on<K extends keyof RelayServerEvents>(event: K, listener: RelayServerEvents[K]): void;
    off<K extends keyof RelayServerEvents>(event: K, listener: RelayServerEvents[K]): void;
};
export declare function startPlayWriterCDPRelayServer({ port, host, token, logger, cdpLogger, }?: {
    port?: number;
    host?: string;
    token?: string;
    logger?: {
        log(...args: any[]): void;
        error(...args: any[]): void;
    };
    cdpLogger?: CdpLogger;
}): Promise<RelayServer>;
//# sourceMappingURL=cdp-relay.d.ts.map