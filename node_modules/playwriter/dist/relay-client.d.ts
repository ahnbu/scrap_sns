/**
 * Shared utilities for connecting to the relay server.
 * Used by both MCP and CLI.
 */
export declare const RELAY_PORT: number;
export declare function getRelayServerVersion(port?: number): Promise<string | null>;
export declare function getExtensionStatus(port?: number): Promise<{
    connected: boolean;
    activeTargets: number;
} | null>;
/**
 * Wait for the extension to connect to the relay server.
 * Returns true if connected within timeout, false otherwise.
 */
export declare function waitForExtension(options?: {
    port?: number;
    timeoutMs?: number;
    logger?: {
        log: (...args: any[]) => void;
    };
}): Promise<boolean>;
export interface EnsureRelayServerOptions {
    logger?: {
        log: (...args: any[]) => void;
    };
    /** If true, will kill and restart server on version mismatch. Default: true */
    restartOnVersionMismatch?: boolean;
    /** Pass additional environment variables to the relay server process */
    env?: Record<string, string>;
}
/**
 * Ensures the relay server is running. Starts it if not running.
 * Optionally restarts on version mismatch.
 */
export declare function ensureRelayServer(options?: EnsureRelayServerOptions): Promise<true | undefined>;
//# sourceMappingURL=relay-client.d.ts.map