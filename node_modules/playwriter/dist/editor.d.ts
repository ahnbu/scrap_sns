import type { ICDPSession } from './cdp-session.js';
export interface ReadResult {
    content: string;
    totalLines: number;
    startLine: number;
    endLine: number;
}
export interface SearchMatch {
    url: string;
    lineNumber: number;
    lineContent: string;
}
export interface EditResult {
    success: boolean;
    stackChanged?: boolean;
}
/**
 * A class for viewing and editing web page scripts via Chrome DevTools Protocol.
 * Provides a Claude Code-like interface: list, read, edit, grep.
 *
 * Edits are in-memory only and persist until page reload. They modify the running
 * V8 instance but are not saved to disk or server.
 *
 * @example
 * ```ts
 * const cdp = await getCDPSession({ page })
 * const editor = new Editor({ cdp })
 * await editor.enable()
 *
 * // List available scripts
 * const scripts = editor.list({ search: 'app' })
 *
 * // Read a script
 * const { content } = await editor.read({ url: 'https://example.com/app.js' })
 *
 * // Edit a script
 * await editor.edit({
 *   url: 'https://example.com/app.js',
 *   oldString: 'console.log("old")',
 *   newString: 'console.log("new")'
 * })
 * ```
 */
export declare class Editor {
    private cdp;
    private enabled;
    private scripts;
    private stylesheets;
    private sourceCache;
    constructor({ cdp }: {
        cdp: ICDPSession;
    });
    private setupEventListeners;
    /**
     * Enables the editor. Must be called before other methods.
     * Scripts are collected from Debugger.scriptParsed events.
     * Reload the page after enabling to capture all scripts.
     */
    enable(): Promise<void>;
    private getIdByUrl;
    /**
     * Lists available script and stylesheet URLs. Use pattern to filter by regex.
     * Automatically enables the editor if not already enabled.
     *
     * @param options - Options
     * @param options.pattern - Optional regex to filter URLs
     * @returns Array of URLs
     *
     * @example
     * ```ts
     * // List all scripts and stylesheets
     * const urls = await editor.list()
     *
     * // List only JS files
     * const jsFiles = await editor.list({ pattern: /\.js/ })
     *
     * // List only CSS files
     * const cssFiles = await editor.list({ pattern: /\.css/ })
     *
     * // Search for specific scripts
     * const appScripts = await editor.list({ pattern: /app/ })
     * ```
     */
    list({ pattern }?: {
        pattern?: RegExp;
    }): Promise<string[]>;
    /**
     * Reads a script or stylesheet's source code by URL.
     * Returns line-numbered content like Claude Code's Read tool.
     * For inline scripts, use the `inline://` URL from list() or grep().
     *
     * @param options - Options
     * @param options.url - Script or stylesheet URL (inline scripts have `inline://{id}` URLs)
     * @param options.offset - Line number to start from (0-based, default 0)
     * @param options.limit - Number of lines to return (default 2000)
     * @returns Content with line numbers, total lines, and range info
     *
     * @example
     * ```ts
     * // Read by URL
     * const { content, totalLines } = await editor.read({
     *   url: 'https://example.com/app.js'
     * })
     *
     * // Read a CSS file
     * const { content } = await editor.read({ url: 'https://example.com/styles.css' })
     *
     * // Read lines 100-200
     * const { content } = await editor.read({
     *   url: 'https://example.com/app.js',
     *   offset: 100,
     *   limit: 100
     * })
     * ```
     */
    read({ url, offset, limit }: {
        url: string;
        offset?: number;
        limit?: number;
    }): Promise<ReadResult>;
    private getSource;
    /**
     * Edits a script or stylesheet by replacing oldString with newString.
     * Like Claude Code's Edit tool - performs exact string replacement.
     *
     * @param options - Options
     * @param options.url - Script or stylesheet URL (inline scripts have `inline://{id}` URLs)
     * @param options.oldString - Exact string to find and replace
     * @param options.newString - Replacement string
     * @param options.dryRun - If true, validate without applying (default false)
     * @returns Result with success status
     *
     * @example
     * ```ts
     * // Replace a string in JS
     * await editor.edit({
     *   url: 'https://example.com/app.js',
     *   oldString: 'const DEBUG = false',
     *   newString: 'const DEBUG = true'
     * })
     *
     * // Edit CSS
     * await editor.edit({
     *   url: 'https://example.com/styles.css',
     *   oldString: 'color: red',
     *   newString: 'color: blue'
     * })
     * ```
     */
    edit({ url, oldString, newString, dryRun, }: {
        url: string;
        oldString: string;
        newString: string;
        dryRun?: boolean;
    }): Promise<EditResult>;
    private setSource;
    /**
     * Searches for a regex across all scripts and stylesheets.
     * Like Claude Code's Grep tool - returns matching lines with context.
     *
     * @param options - Options
     * @param options.regex - Regular expression to search for in file contents
     * @param options.pattern - Optional regex to filter which URLs to search
     * @returns Array of matches with url, line number, and line content
     *
     * @example
     * ```ts
     * // Search all scripts and stylesheets for "color"
     * const matches = await editor.grep({ regex: /color/ })
     *
     * // Search only CSS files
     * const matches = await editor.grep({
     *   regex: /background-color/,
     *   pattern: /\.css/
     * })
     *
     * // Regex search for console methods in JS
     * const matches = await editor.grep({
     *   regex: /console\.(log|error|warn)/,
     *   pattern: /\.js/
     * })
     * ```
     */
    grep({ regex, pattern }: {
        regex: RegExp;
        pattern?: RegExp;
    }): Promise<SearchMatch[]>;
    /**
     * Writes entire content to a script or stylesheet, replacing all existing code.
     * Use with caution - prefer edit() for targeted changes.
     *
     * @param options - Options
     * @param options.url - Script or stylesheet URL (inline scripts have `inline://{id}` URLs)
     * @param options.content - New content
     * @param options.dryRun - If true, validate without applying (default false, only works for JS)
     */
    write({ url, content, dryRun }: {
        url: string;
        content: string;
        dryRun?: boolean;
    }): Promise<EditResult>;
}
//# sourceMappingURL=editor.d.ts.map