export type Logger = {
    log(...args: unknown[]): Promise<void>;
    error(...args: unknown[]): Promise<void>;
    logFilePath: string;
};
export declare function createFileLogger({ logFilePath }?: {
    logFilePath?: string;
}): Logger;
//# sourceMappingURL=create-logger.d.ts.map