export type CdpLogEntry = {
    timestamp: string;
    direction: 'from-playwright' | 'to-playwright' | 'from-extension' | 'to-extension';
    clientId?: string;
    source?: 'extension' | 'server';
    message: unknown;
};
export type CdpLogger = {
    log(entry: CdpLogEntry): void;
    logFilePath: string;
};
export declare function createCdpLogger({ logFilePath, maxStringLength }?: {
    logFilePath?: string;
    maxStringLength?: number;
}): CdpLogger;
//# sourceMappingURL=cdp-log.d.ts.map