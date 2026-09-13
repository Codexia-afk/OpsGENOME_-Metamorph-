/**
 * API Gateway - Payment Proxy Route
 */
const express = require('express');
const app = express();

app.post('/pay', async (req, res) => {
    // Inbound request forwarded to internal payment engine
    const resp = await fetch('http://payment:8080/charge');
    const data = resp.json(); // Missing await on promise
    res.send(data.status);
});

module.exports = app;
