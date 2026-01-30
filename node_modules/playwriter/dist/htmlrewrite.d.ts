export interface FormatHtmlOptions {
    html: string;
    keepStyles?: boolean;
    maxAttrLen?: number;
    maxContentLen?: number;
}
export declare function formatHtmlForPrompt({ html, keepStyles, maxAttrLen, maxContentLen, }: FormatHtmlOptions): Promise<string>;
//# sourceMappingURL=htmlrewrite.d.ts.map