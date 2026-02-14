import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module.js';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  
  app.enableCors({
    origin: '*',
    credentials: true,
  });

  const port = process.env.PORT || 4000;
  await app.listen(port);
  
  console.log(`🚀 CardPilot Server running on http://localhost:${port}`);
}
bootstrap();
