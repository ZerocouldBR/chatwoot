// Proxy HTTPS local do e2e (o nó Zendesk do n8n sempre monta https://<subdominio>.zendesk.com/...).
// Escuta em 127.0.0.1:${PORT} com certificado autoassinado e repassa para o Rails do DEV em ${TARGET}.
const fs = require('fs');
const https = require('https');
const http = require('http');

const port = Number(process.env.PORT || 8443);
const target = new URL(process.env.TARGET || 'http://127.0.0.1:3530');
const options = { key: fs.readFileSync(process.env.KEY), cert: fs.readFileSync(process.env.CERT) };

https.createServer(options, (req, res) => {
  const headers = { ...req.headers, 'x-forwarded-proto': 'https', 'x-forwarded-host': req.headers.host };
  const upstream = http.request({ host: target.hostname, port: target.port, method: req.method, path: req.url, headers }, (up) => {
    res.writeHead(up.statusCode, up.headers);
    up.pipe(res);
  });
  upstream.on('error', (err) => { res.writeHead(502); res.end(String(err)); });
  req.pipe(upstream);
}).listen(port, '127.0.0.1', () => console.log(`tls_proxy ${port} -> ${target.href}`));
