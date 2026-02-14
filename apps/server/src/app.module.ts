import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { PrismaModule } from './prisma/prisma.module.js';
import { TableModule } from './table/table.module.js';
import { HandModule } from './hand/hand.module.js';
import { AdviceModule } from './advice/advice.module.js';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
    }),
    PrismaModule,
    TableModule,
    HandModule,
    AdviceModule,
  ],
})
export class AppModule {}
