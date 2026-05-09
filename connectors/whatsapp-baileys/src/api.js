import axios from 'axios';
import { config } from './config.js';

export const api = axios.create({
  baseURL: config.PIPELINE_API_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    'X-Connector-Secret': config.CONNECTOR_SECRET,
  },
});
