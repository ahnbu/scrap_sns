export async function getStylesForLocator({ locator, cdp: cdpSession, includeUserAgentStyles = false, }) {
    // Cast to CDPSession for internal type safety - at runtime both are compatible
    const cdp = cdpSession;
    await cdp.send('DOM.enable');
    await cdp.send('CSS.enable');
    const elementHandle = await locator.elementHandle();
    if (!elementHandle) {
        throw new Error('Could not get element handle from locator');
    }
    const remoteObject = elementHandle._channel?.objectId
        ? { objectId: elementHandle._channel.objectId }
        : null;
    let backendNodeId;
    if (remoteObject?.objectId) {
        const nodeInfo = await cdp.send('DOM.describeNode', {
            objectId: remoteObject.objectId,
        });
        backendNodeId = nodeInfo.node.backendNodeId;
    }
    else {
        const box = await elementHandle.boundingBox();
        if (!box) {
            throw new Error('Element has no bounding box');
        }
        const docResult = await cdp.send('DOM.getDocument', { depth: 0 });
        const nodeAtPoint = await cdp.send('DOM.getNodeForLocation', {
            x: Math.round(box.x + box.width / 2),
            y: Math.round(box.y + box.height / 2),
        });
        backendNodeId = nodeAtPoint.backendNodeId;
    }
    const pushResult = await cdp.send('DOM.pushNodesByBackendIdsToFrontend', {
        backendNodeIds: [backendNodeId],
    });
    const nodeId = pushResult.nodeIds[0];
    if (!nodeId) {
        throw new Error('Could not get nodeId for element');
    }
    const nodeInfo = await cdp.send('DOM.describeNode', { nodeId });
    const elementDescription = formatElementDescription(nodeInfo.node);
    const matchedStyles = await cdp.send('CSS.getMatchedStylesForNode', { nodeId });
    const stylesheetUrls = new Map();
    const processStyleSheetId = async (styleSheetId) => {
        if (!styleSheetId) {
            return null;
        }
        if (!stylesheetUrls.has(styleSheetId)) {
            try {
                const header = await cdp.send('CSS.getStyleSheetText', { styleSheetId });
                stylesheetUrls.set(styleSheetId, '');
            }
            catch {
                stylesheetUrls.set(styleSheetId, '');
            }
        }
        return null;
    };
    const rules = [];
    if (matchedStyles.matchedCSSRules) {
        for (const ruleMatch of matchedStyles.matchedCSSRules) {
            const rule = ruleMatch.rule;
            const sourceRange = rule.selectorList?.range;
            const styleSheetId = rule.styleSheetId;
            let source = null;
            if (styleSheetId && sourceRange) {
                const styleSheet = matchedStyles.cssStyleSheetHeaders?.find((h) => h.styleSheetId === styleSheetId);
                const url = styleSheet?.sourceURL || rule.origin === 'user-agent' ? 'user-agent' : `stylesheet:${styleSheetId}`;
                source = {
                    url: rule.styleSheetId ? await getStylesheetUrl(cdp, styleSheetId) : 'user-agent',
                    line: sourceRange.startLine + 1,
                    column: sourceRange.startColumn,
                };
            }
            rules.push({
                selector: rule.selectorList.text,
                source,
                origin: rule.origin,
                declarations: extractDeclarations(rule.style),
                inheritedFrom: null,
            });
        }
    }
    if (matchedStyles.inherited) {
        for (let i = 0; i < matchedStyles.inherited.length; i++) {
            const inheritedEntry = matchedStyles.inherited[i];
            const ancestorDesc = `ancestor[${i + 1}]`;
            if (inheritedEntry.inlineStyle) {
                const declarations = extractDeclarations(inheritedEntry.inlineStyle);
                if (Object.keys(declarations).length > 0) {
                    rules.push({
                        selector: 'element.style',
                        source: null,
                        origin: 'regular',
                        declarations,
                        inheritedFrom: ancestorDesc,
                    });
                }
            }
            for (const ruleMatch of inheritedEntry.matchedCSSRules) {
                const rule = ruleMatch.rule;
                const sourceRange = rule.selectorList?.range;
                const styleSheetId = rule.styleSheetId;
                let source = null;
                if (styleSheetId && sourceRange) {
                    source = {
                        url: await getStylesheetUrl(cdp, styleSheetId),
                        line: sourceRange.startLine + 1,
                        column: sourceRange.startColumn,
                    };
                }
                const declarations = extractDeclarations(rule.style);
                if (Object.keys(declarations).length > 0) {
                    rules.push({
                        selector: rule.selectorList.text,
                        source,
                        origin: rule.origin,
                        declarations,
                        inheritedFrom: ancestorDesc,
                    });
                }
            }
        }
    }
    let inlineStyle = null;
    if (matchedStyles.inlineStyle) {
        const declarations = extractDeclarations(matchedStyles.inlineStyle);
        if (Object.keys(declarations).length > 0) {
            inlineStyle = declarations;
        }
    }
    const filteredRules = includeUserAgentStyles
        ? rules
        : rules.filter((r) => r.origin !== 'user-agent');
    return {
        element: elementDescription,
        inlineStyle,
        rules: filteredRules,
    };
}
function extractDeclarations(style) {
    if (!style?.cssProperties) {
        return {};
    }
    const result = {};
    for (const prop of style.cssProperties) {
        if (!prop.value || prop.value === 'initial' || prop.name.startsWith('-webkit-')) {
            continue;
        }
        const value = prop.important ? `${prop.value} !important` : prop.value;
        result[prop.name] = value;
    }
    return result;
}
function formatElementDescription(node) {
    let desc = node.localName || node.nodeName?.toLowerCase() || 'element';
    if (node.attributes) {
        const attrs = {};
        for (let i = 0; i < node.attributes.length; i += 2) {
            attrs[node.attributes[i]] = node.attributes[i + 1];
        }
        if (attrs.id) {
            desc += `#${attrs.id}`;
        }
        if (attrs.class) {
            desc += `.${attrs.class.split(' ').join('.')}`;
        }
    }
    return desc;
}
async function getStylesheetUrl(cdp, styleSheetId) {
    try {
        await cdp.send('CSS.getStyleSheetText', { styleSheetId });
        return `stylesheet:${styleSheetId}`;
    }
    catch {
        return `stylesheet:${styleSheetId}`;
    }
}
export function formatStylesAsText(styles) {
    const lines = [];
    lines.push(`Element: ${styles.element}`);
    lines.push('');
    if (styles.inlineStyle) {
        lines.push('Inline styles:');
        for (const [prop, value] of Object.entries(styles.inlineStyle)) {
            lines.push(`  ${prop}: ${value}`);
        }
        lines.push('');
    }
    const directRules = styles.rules.filter((r) => !r.inheritedFrom);
    const inheritedRules = styles.rules.filter((r) => r.inheritedFrom);
    if (directRules.length > 0) {
        lines.push('Matched rules:');
        for (const rule of directRules) {
            lines.push(`  ${rule.selector} {`);
            const sourceInfo = rule.source ? ` /* ${rule.source.url}:${rule.source.line}:${rule.source.column} */` : '';
            if (sourceInfo) {
                lines.push(`   ${sourceInfo}`);
            }
            for (const [prop, value] of Object.entries(rule.declarations)) {
                lines.push(`    ${prop}: ${value};`);
            }
            lines.push('  }');
        }
        lines.push('');
    }
    if (inheritedRules.length > 0) {
        const byAncestor = new Map();
        for (const rule of inheritedRules) {
            const key = rule.inheritedFrom;
            if (!byAncestor.has(key)) {
                byAncestor.set(key, []);
            }
            byAncestor.get(key).push(rule);
        }
        for (const [ancestor, rules] of byAncestor) {
            lines.push(`Inherited from ${ancestor}:`);
            for (const rule of rules) {
                lines.push(`  ${rule.selector} {`);
                const sourceInfo = rule.source ? ` /* ${rule.source.url}:${rule.source.line}:${rule.source.column} */` : '';
                if (sourceInfo) {
                    lines.push(`   ${sourceInfo}`);
                }
                for (const [prop, value] of Object.entries(rule.declarations)) {
                    lines.push(`    ${prop}: ${value};`);
                }
                lines.push('  }');
            }
            lines.push('');
        }
    }
    return lines.join('\n');
}
//# sourceMappingURL=styles.js.map