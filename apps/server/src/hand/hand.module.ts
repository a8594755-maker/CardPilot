import { Module } from '@nestjs/common';
import { HandService } from './hand.service';
import { PrismaModule } from '../prisma/prisma.module';

@Module({
  imports: [PrismaModule],
  providers: [HandService],
  exports: [HandService],
})
export class HandModule {}
