// types tests. to see if types are right with some simple examples
if (false) {
    const browserVersionCommand = {
        id: 1,
        method: 'Browser.getVersion',
    };
    const browserVersionResponse = {
        id: 1,
        result: {
            protocolVersion: '1.3',
            product: 'Chrome',
            revision: '123',
            userAgent: 'Mozilla/5.0',
            jsVersion: 'V8',
        }
    };
    const targetAttachCommand = {
        id: 2,
        method: 'Target.setAutoAttach',
        params: {
            autoAttach: true,
            waitForDebuggerOnStart: false,
        }
    };
    const targetAttachResponse = {
        id: 2,
        result: undefined,
    };
    const attachedToTargetEvent = {
        method: 'Target.attachedToTarget',
        params: {
            sessionId: 'session-1',
            targetInfo: {
                targetId: 'target-1',
                type: 'page',
                title: 'Example',
                url: 'https://example.com',
                attached: true,
                canAccessOpener: false,
            },
            waitingForDebugger: false,
        }
    };
    const consoleMessageEvent = {
        method: 'Runtime.consoleAPICalled',
        params: {
            type: 'log',
            args: [],
            executionContextId: 1,
            timestamp: 123456789,
        }
    };
    const pageNavigateCommand = {
        id: 3,
        method: 'Page.navigate',
        params: {
            url: 'https://example.com',
        }
    };
    const pageNavigateResponse = {
        id: 3,
        result: {
            frameId: 'frame-1',
        }
    };
    const networkRequestEvent = {
        method: 'Network.requestWillBeSent',
        sessionId: 'session-1',
        params: {
            requestId: 'req-1',
            loaderId: 'loader-1',
            documentURL: 'https://example.com',
            request: {
                url: 'https://example.com/api',
                method: 'GET',
                headers: {},
                initialPriority: 'High',
                referrerPolicy: 'no-referrer',
            },
            timestamp: 123456789,
            wallTime: 123456789,
            initiator: {
                type: 'other',
            },
            redirectHasExtraInfo: false,
            type: 'XHR',
        }
    };
}
export {};
//# sourceMappingURL=cdp-types.js.map