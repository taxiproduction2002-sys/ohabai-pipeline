import pino from 'pino';

const isProduction = process.env.NODE_ENV === 'production';

export const log = pino({
  level: process.env.LOG_LEVEL || 'info',
  base: {
    service: 'ohabai-whatsapp-baileys',
  },
  ...(isProduction
    ? {
        formatters: {
          level: (label) => ({ level: label }),
        },
        timestamp: pino.stdTimeFunctions.isoTime,
      }
    : {
        transport: {
          target: 'pino-pretty',
          options: {
            colorize: true,
            translateTime: 'HH:MM:ss',
            ignore: 'pid,hostname',
          },
        },
      }),
});
