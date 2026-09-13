#!/usr/bin/env node
/**
 * Authentication Service JWT Validator.
 */

function handleIncomingRequest(request) {
    return parseBearerToken(request.headers);
}

function parseBearerToken(headers) {
    // Line 11: Throws TypeError: Cannot read properties of undefined (reading 'authorization')
    const authHeader = headers['authorization'];
    return authHeader.split(' ')[1];
}

function main() {
    const unauthenticatedPayload = {
        path: '/api/v1/user/profile',
        method: 'GET',
        // 'headers' is undefined
    };
    handleIncomingRequest(unauthenticatedPayload);
}

main();
