import { Module } from '@nestjs/common';
import { TableGateway } from './table.gateway.js';
import { TableService } from './table.service.js';
import { PrismaModule } from '../prisma/prisma.module.js';
import { HandModule } from '../hand/hand.module.js';
import { AdviceModule } from '../advice/advice.module.js';

@Module({
  imports: [PrismaModule, HandModule, AdviceModule],
  providers: [TableGateway, TableService],
})
export class TableModule {}
