import http from 'http';

const port = process.env.HEALTH_PORT || '3000';

const req = http.get(`http://localhost:${port}/health`, (res) => {
  process.exit(res.statusCode === 200 ? 0 : 1);
});
req.on('error', () => process.exit(1));
req.end();
